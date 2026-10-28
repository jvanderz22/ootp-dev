import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ApiService } from '../../core/api';
import { LeagueSnapshotStore } from '../../core/league-snapshot-store';
import { TradeListStore } from '../../core/trade-list-store';
import { RankedPlayer, RankedQuery } from '../../core/api.types';
import { DEFAULT_SORT, POSITION_ORDER } from '../../core/ranked-columns';
import { RankedTableComponent } from '../class-view/ranked-table';

/** Priority tier → numeric backing, matching `web/trade_lists.priority_rank`. */
const PRIORITY_RANK: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

function defaultQuery(): RankedQuery {
  return {
    view: 'modeled',
    search: '',
    positions: [],
    bestPositions: [],
    batHands: [],
    throwHands: [],
    teams: [],
    levels: [],
    hideDrafted: false,
    rule5Only: false,
    numericFilters: [],
    sortField: DEFAULT_SORT.modeled.field,
    sortOrder: DEFAULT_SORT.modeled.order,
  };
}

/** Read a sort key off a row: a flat payload key, or a dotted rating path
 *  (`batting.power`, `pitching.stuff`). Non-finite / missing sorts last. */
function sortValue(row: RankedPlayer, field: string): number | string | null {
  if (field.includes('.')) {
    let cur: unknown = row.ratings;
    for (const seg of field.split('.')) {
      cur = cur == null ? null : (cur as Record<string, unknown>)[seg];
    }
    return typeof cur === 'number' || typeof cur === 'string' ? cur : null;
  }
  const v = (row as unknown as Record<string, unknown>)[field];
  return typeof v === 'number' || typeof v === 'string' ? v : null;
}

/**
 * Trade Targets: the league's named trade-target lists. A list picker up top
 * (rename / delete / new), then the class-view ranked table fed by
 * `tradeListPlayers` — live model scores / ratings pulled against the current
 * snapshot, priority + note per entry, stale rows for players who have left the
 * snapshot.
 *
 * Lists are small, so all rows are fetched once and the table's column-sort
 * `queryChange` re-sorts them in memory rather than refetching. Priority is the
 * standing primary sort; a column sort layers on top of it.
 */
@Component({
  selector: 'app-trade-targets',
  imports: [FormsModule, RouterLink, RankedTableComponent],
  template: `
    @if (store.error()) { <p class="error">{{ store.error() }}</p> }
    @if (error()) { <p class="error">{{ error() }}</p> }

    @if (!store.lists().length) {
      <div class="empty">
        <p>No trade-target lists yet.</p>
        <form class="new-list" (submit)="$event.preventDefault(); createList()">
          <input type="text" placeholder="List name…" [(ngModel)]="draftName" name="n" />
          <button type="submit" class="primary" [disabled]="!draftName.trim()">
            Create list
          </button>
        </form>
      </div>
    } @else {
      <div class="picker">
        <select [ngModel]="listId()" (ngModelChange)="selectList($event)" name="list">
          @for (l of store.lists(); track l.id) {
            <option [value]="l.id">{{ l.name }} ({{ l.entryCount }})</option>
          }
        </select>

        @if (renaming()) {
          <form class="inline" (submit)="$event.preventDefault(); commitRename()">
            <input type="text" [(ngModel)]="draftName" name="rn" />
            <button type="submit" class="sm primary">Save</button>
            <button type="button" class="sm" (click)="renaming.set(false)">Cancel</button>
          </form>
        } @else {
          <button type="button" class="sm" (click)="startRename()">Rename</button>
          <button type="button" class="sm" (click)="deleteList()">Delete</button>
        }

        <form class="inline new-list" (submit)="$event.preventDefault(); createList()">
          <input type="text" placeholder="New list…" [(ngModel)]="newName" name="nn" />
          <button type="submit" class="sm" [disabled]="!newName.trim()">Add list</button>
        </form>
      </div>

      @if (!activeList()?.entryCount) {
        <p class="muted">
          No players on this list yet — add them with the ☆ button on the
          <a [routerLink]="['/league', leagueId()]">Current League</a> tab.
        </p>
      } @else {
        <app-ranked-table
          [rows]="rows()"
          [totalRecords]="totalRecords()"
          [positions]="positionOptions"
          [teams]="[]"
          [levels]="[]"
          [context]="'league'"
          [loading]="loading()"
          [loadingMore]="false"
          [hasMore]="false"
          [resetToken]="resetToken()"
          [classKey]="tableKey()"
          [initialQuery]="query()"
          [tradeStore]="store"
          [tradeListId]="listId()"
          (queryChange)="onQueryChange($event)"
        />
      }
    }
  `,
  styles: `
    .empty { margin: 24px 0; display: flex; flex-direction: column; gap: 10px; }
    .picker {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin: 14px 0 6px;
    }
    .picker select { min-width: 12rem; }
    .inline { display: inline-flex; align-items: center; gap: 6px; }
    .new-list { display: inline-flex; align-items: center; gap: 6px; }
    button.sm { font-size: 12px; padding: 3px 8px; }
    .muted { color: var(--text-dim); }
    .muted a { color: var(--accent); }
  `,
})
export class TradeTargetsPage {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  protected readonly store = inject(TradeListStore);
  protected readonly snapshot = inject(LeagueSnapshotStore);

  protected readonly positionOptions = POSITION_ORDER;

  protected readonly leagueId = toSignal(
    (this.route.parent ?? this.route).paramMap.pipe(map((p) => p.get('id') ?? '')),
    { initialValue: (this.route.parent ?? this.route).snapshot.paramMap.get('id') ?? '' },
  );

  protected readonly listId = signal<string>('');
  protected draftName = '';
  protected newName = '';
  protected readonly renaming = signal(false);

  /** All rows for the selected list, freshly fetched (unsorted-for-display). */
  private readonly allRows = signal<RankedPlayer[]>([]);
  protected readonly query = signal<RankedQuery>(defaultQuery());
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly resetToken = signal(0);

  protected readonly activeList = computed(() =>
    this.store.lists().find((l) => l.id === this.listId()),
  );
  protected readonly tableKey = computed(() => `${this.leagueId()}:${this.listId()}`);

  /** Priority first (HIGH → LOW), then the table's column sort, stale rows last. */
  protected readonly rows = computed(() => {
    const q = this.query();
    const search = q.search.trim().toLowerCase();
    let rs = this.allRows();
    if (search) rs = rs.filter((r) => r.name.toLowerCase().includes(search));
    if (q.positions.length) rs = rs.filter((r) => q.positions.includes(r.position));

    const field = q.sortField;
    const dir = q.sortOrder;
    return [...rs].sort((a, b) => {
      if (!!a.stale !== !!b.stale) return a.stale ? 1 : -1;
      const pa = PRIORITY_RANK[a.priority ?? ''] ?? 3;
      const pb = PRIORITY_RANK[b.priority ?? ''] ?? 3;
      if (pa !== pb) return pa - pb;
      if (field && field !== 'rank') {
        const va = sortValue(a, field);
        const vb = sortValue(b, field);
        if (va == null && vb != null) return 1;
        if (va != null && vb == null) return -1;
        if (va != null && vb != null) {
          const cmp = va < vb ? -1 : va > vb ? 1 : 0;
          if (cmp) return cmp * dir;
        }
      }
      return (b.modelScore ?? 0) - (a.modelScore ?? 0);
    });
  });
  protected readonly totalRecords = computed(() => this.rows().length);

  private loadedFetchedAt: string | null | undefined = undefined;

  constructor() {
    // Pick a list once the store has loaded (or keep the current pick valid).
    effect(() => {
      const lists = this.store.lists();
      untracked(() => {
        if (!lists.length) {
          this.listId.set('');
          return;
        }
        if (!lists.some((l) => l.id === this.listId())) {
          this.listId.set(lists[0].id);
        }
      });
    });

    // (Re)fetch rows when the list changes or a snapshot refresh lands.
    effect(() => {
      const id = this.listId();
      const lg = this.leagueId();
      const snap = this.snapshot.snapshot();
      if (this.snapshot.refreshing()) return;
      if (!id || !lg) {
        this.allRows.set([]);
        return;
      }
      const fetchedAt = snap?.fetchedAt ?? null;
      untracked(() => {
        if (id === this.lastLoadedListId && fetchedAt === this.loadedFetchedAt) return;
        void this.load(lg, id, fetchedAt);
      });
    });
  }

  private lastLoadedListId = '';

  private async load(
    leagueId: string,
    listId: string,
    fetchedAt: string | null,
  ): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const page = await this.api.tradeListPlayers(leagueId, listId);
      this.allRows.set(page.rows);
      this.lastLoadedListId = listId;
      this.loadedFetchedAt = fetchedAt;
      this.resetToken.update((v) => v + 1);
      if (!this.snapshot.methodReady('potential') || !this.snapshot.methodReady('overall')) {
        void this.snapshot.refreshSnapshotMeta();
      }
    } catch (e) {
      this.error.set((e as Error).message);
      this.allRows.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  protected onQueryChange(q: RankedQuery): void {
    this.query.set(q);
  }

  protected selectList(id: string): void {
    this.renaming.set(false);
    this.listId.set(id);
    this.query.set(defaultQuery());
  }

  protected async createList(): Promise<void> {
    const name = (this.newName || this.draftName).trim();
    if (!name) return;
    try {
      const made = await this.store.create(name);
      this.newName = '';
      this.draftName = '';
      this.selectList(made.id);
    } catch (e) {
      this.error.set((e as Error).message);
    }
  }

  protected startRename(): void {
    this.draftName = this.activeList()?.name ?? '';
    this.renaming.set(true);
  }

  protected async commitRename(): Promise<void> {
    const name = this.draftName.trim();
    if (!name) return;
    try {
      await this.store.rename(this.listId(), name);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.renaming.set(false);
    }
  }

  protected async deleteList(): Promise<void> {
    const l = this.activeList();
    if (!l) return;
    if (!confirm(`Delete trade list "${l.name}"?`)) return;
    try {
      await this.store.remove(l.id);
    } catch (e) {
      this.error.set((e as Error).message);
    }
  }
}
