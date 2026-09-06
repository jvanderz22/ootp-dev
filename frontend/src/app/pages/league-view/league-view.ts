import {
  Component,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ApiService } from '../../core/api';
import { LeagueSnapshotStore } from '../../core/league-snapshot-store';
import {
  LeagueGroupBy,
  LeagueTeam,
  RANKED_PAGE_SIZE,
  RankedPlayer,
  RankedQuery,
} from '../../core/api.types';
import { DEFAULT_SORT, POSITION_ORDER } from '../../core/ranked-columns';
import { paramsToQuery, queryToParams } from '../../core/table-url';
import { RankedTableComponent } from '../class-view/ranked-table';

type Method = 'overall' | 'potential';

const METHODS: { label: string; value: Method }[] = [
  { label: 'Current', value: 'overall' },
  { label: 'Potential', value: 'potential' },
];

/** Top-level grouping. "By org" carries a second dropdown (Full org / one of the
 *  org's clubs); picking a club there fetches with `groupBy: TEAM` under the
 *  hood, so there is no separate "By team" button. */
const GROUPINGS: { label: string; value: 'LEAGUE' | 'ORG' }[] = [
  { label: 'Whole league', value: 'LEAGUE' },
  { label: 'By org', value: 'ORG' },
];

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
    numericFilters: [],
    sortField: DEFAULT_SORT.modeled.field,
    sortOrder: DEFAULT_SORT.modeled.order,
  };
}

/**
 * Live league snapshot view: the whole player pool pulled from StatsPlus, ranked
 * by the "current" or "potential" model, optionally narrowed to one org or one
 * roster team. Fetch/filter/sort/infinite-scroll mirror `class-view.ts`, against
 * `leagueSnapshotPlayers` instead of `rankedPlayers`, and it reuses the
 * class-view ranked table unchanged.
 *
 * Snapshot freshness, the manual refresh, and the progress panel live on the
 * shared `LeagueSnapshotStore` (rendered by `league-shell`); this page just
 * reads `store.snapshot()` / `store.refreshing()` and reloads when the snapshot
 * changes under it (e.g. after a refresh).
 */
@Component({
  selector: 'app-league-view',
  imports: [RankedTableComponent],
  template: `
    @if (methodNotReady() && !store.refreshing()) {
      <p class="notice">
        The {{ methodLabel() }} model hasn't been run for this snapshot yet — it'll
        compute the first time you open it (about a minute).
      </p>
    }
    @if (error()) { <p class="error">{{ error() }}</p> }

    @if (store.snapshot() && !store.refreshing()) {
      <div class="controls">
        <div class="seg">
          @for (m of methods; track m.value) {
            <button
              type="button"
              [class.active]="method() === m.value"
              [disabled]="loading()"
              (click)="setMethod(m.value)"
            >{{ m.label }}</button>
          }
        </div>

        <div class="seg">
          @for (g of groupings; track g.value) {
            <button
              type="button"
              [class.active]="groupBy() === g.value"
              [disabled]="loading()"
              (click)="setGroupBy(g.value)"
            >{{ g.label }}</button>
          }
        </div>

        @if (groupBy() === 'ORG') {
          <select [value]="orgId() ?? ''" [disabled]="loading()"
            (change)="setOrg($any($event.target).value)">
            <option value="">Pick an org…</option>
            @for (o of orgs(); track o.id) {
              <option [value]="o.id">{{ o.name }}</option>
            }
          </select>
        }
        @if (groupBy() === 'ORG' && orgId()) {
          <select [value]="teamId() ?? ''" [disabled]="loading()"
            (change)="setTeam($any($event.target).value)">
            <option value="">Full org</option>
            @for (t of orgTeams(); track t.id) {
              <option [value]="t.id">
                {{ t.name }}@if (t.level) { · {{ t.level }} }
              </option>
            }
          </select>
        }
      </div>

      @if (groupBy() === 'ORG' && !orgId()) {
        <p class="muted">Choose an org to see its players.</p>
      } @else {
        <app-ranked-table
          [rows]="rows()"
          [totalRecords]="totalRecords()"
          [positions]="positionOptions"
          [teams]="[]"
          [levels]="levels()"
          [context]="'league'"
          [loading]="loading()"
          [loadingMore]="loadingMore()"
          [hasMore]="hasMore()"
          [resetToken]="resetToken()"
          [classKey]="tableKey()"
          [initialQuery]="queryState()"
          (queryChange)="onQueryChange($event)"
          (loadMore)="onLoadMore()"
        />
      }
    }
  `,
  styles: `
    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      margin: 14px 0 10px;
    }
    .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    .seg button {
      background: none;
      border: none;
      border-right: 1px solid var(--border);
      padding: 6px 12px;
      cursor: pointer;
      font: inherit;
      color: var(--muted, #666);
    }
    .seg button:last-child { border-right: none; }
    .seg button.active { background: var(--accent); color: #fff; font-weight: 600; }
    .notice { color: var(--ok); }
  `,
})
export class LeagueViewPage {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly store = inject(LeagueSnapshotStore);

  protected readonly methods = METHODS;
  protected readonly groupings = GROUPINGS;
  protected readonly positionOptions = POSITION_ORDER;

  protected readonly leagueId = toSignal(
    (this.route.parent ?? this.route).paramMap.pipe(map((p) => p.get('id') ?? '')),
    { initialValue: (this.route.parent ?? this.route).snapshot.paramMap.get('id') ?? '' },
  );

  protected readonly method = signal<Method>('potential');
  /** Top-level grouping the user picked: whole league, or by org. */
  protected readonly groupBy = signal<'LEAGUE' | 'ORG'>('ORG');
  protected readonly orgId = signal<string | null>(null);
  /** ORG mode only: a specific club within the org, or null for "Full org". */
  protected readonly teamId = signal<string | null>(null);

  /** What the API is actually asked for. Picking a club inside an org fetches
   *  with `groupBy: TEAM`; "Full org" stays `ORG`; whole-league is `LEAGUE`. */
  protected readonly apiGroupBy = computed<LeagueGroupBy>(() =>
    this.groupBy() === 'LEAGUE' ? 'LEAGUE' : this.teamId() ? 'TEAM' : 'ORG',
  );
  protected readonly apiGroupId = computed(() => {
    if (this.groupBy() === 'LEAGUE') return null;
    return this.teamId() ?? this.orgId();
  });
  /** Whether enough is selected to show a table (whole-league, or an org chosen). */
  protected readonly hasSelection = computed(
    () => this.groupBy() === 'LEAGUE' || !!this.orgId(),
  );

  protected readonly orgs = signal<LeagueTeam[]>([]);
  protected readonly teams = signal<LeagueTeam[]>([]);
  protected readonly levels = signal<string[]>([]);

  /** Teams under the selected org. Affiliates carry their parent club directly
   *  as `parentTeamId`, so no extra request is needed to scope the picker. */
  protected readonly orgTeams = computed(() => {
    const oid = this.orgId();
    if (!oid) return [];
    return this.teams().filter((t) => t.id === oid || t.parentTeamId === oid);
  });

  /** The chosen ranking's model hasn't been scored for this snapshot yet — the
   *  first open will compute it (a minute or so). */
  protected readonly methodNotReady = computed(
    () => !this.store.methodReady(this.method()),
  );
  protected readonly methodLabel = computed(
    () => METHODS.find((m) => m.value === this.method())?.label ?? '',
  );

  protected readonly rows = signal<RankedPlayer[]>([]);
  protected readonly totalRecords = signal(0);
  protected readonly loading = signal(false);
  protected readonly loadingMore = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly queryState = signal<RankedQuery>(defaultQuery());
  protected readonly resetToken = signal(0);

  protected readonly hasMore = computed(() => this.rows().length < this.totalRecords());
  protected readonly tableKey = computed(
    () =>
      `${this.leagueId()}:${this.method()}:${this.apiGroupBy()}:${this.apiGroupId() ?? ''}`,
  );

  private hydrated = false;
  /** `fetchedAt` of the snapshot the current rows were loaded against — so a
   *  refresh landing under us triggers exactly one reload, not a loop. */
  private loadedFetchedAt: string | null | undefined = undefined;

  constructor() {
    effect(() => {
      const id = this.leagueId();
      if (id) untracked(() => void this.load(id));
    });
    // Reload when the shared snapshot changes under us (manual/auto refresh
    // finished). The first settle from `store.init()` matches what `load()`
    // already fetched, so it no-ops on the `loadedFetchedAt` guard.
    effect(() => {
      const snap = this.store.snapshot();
      const refreshing = this.store.refreshing();
      if (refreshing) return;
      const id = untracked(() => this.leagueId());
      if (!id || untracked(() => this.loading())) return;
      if ((snap?.fetchedAt ?? null) === (this.loadedFetchedAt ?? null)) return;
      untracked(() => void this.load(id));
    });
  }

  private hydrateFromUrl(): void {
    const p = this.route.snapshot.queryParamMap;
    this.method.set(p.get('method') === 'overall' ? 'overall' : 'potential');
    this.groupBy.set(p.get('group') === 'LEAGUE' ? 'LEAGUE' : 'ORG');
    this.orgId.set(p.get('org') || null);
    this.teamId.set(p.get('team') || null);
    this.queryState.set(paramsToQuery(p));
    this.hydrated = true;
  }

  private syncUrl(replace = true): void {
    const params: Record<string, string | null> = {
      ...queryToParams(this.queryState()),
      method: this.method() === 'potential' ? null : 'overall',
      group: this.groupBy() === 'ORG' ? null : this.groupBy(),
      org: this.groupBy() === 'ORG' ? this.orgId() || null : null,
      team: this.groupBy() === 'ORG' ? this.teamId() || null : null,
    };
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: params,
      replaceUrl: replace,
    });
  }

  /** Full load for a league (route change or after a refresh): org/team facets
   *  and the first batch for the current method/grouping. Snapshot freshness /
   *  re-attach is the shell's `LeagueSnapshotStore`, not this. */
  private async load(id: string): Promise<void> {
    if (!this.hydrated) this.hydrateFromUrl();
    this.loading.set(true);
    this.error.set(null);
    try {
      const d = await this.api.leagueViewDetail(
        id,
        this.method(),
        this.apiGroupBy(),
        this.apiGroupId(),
        this.queryState(),
      );
      // The server served this against the on-disk snapshot; record its
      // `fetchedAt` so `store.init()`'s priming set no-ops but a later refresh
      // (new `fetchedAt`) triggers exactly one reload.
      this.loadedFetchedAt = d.snapshot?.fetchedAt ?? null;
      this.orgs.set([...d.orgs].sort((a, b) => a.name.localeCompare(b.name)));
      // teams arrive already ordered by level (MLB → AAA → …) — keep that order.
      this.teams.set(d.teams);
      this.levels.set(d.levels);
      this.rows.set(d.page.rows);
      this.totalRecords.set(d.page.totalRecords);
      this.resetToken.update((v) => v + 1);
      // that fetch may have lazily computed the model — refresh the ready flags
      if (d.snapshot && !d.snapshot.rankedMethods.includes(this.method())) {
        void this.store.refreshSnapshotMeta();
      }
    } catch (e) {
      this.error.set((e as Error).message);
      this.rows.set([]);
      this.totalRecords.set(0);
    } finally {
      this.loading.set(false);
    }
  }

  private async resetAndFetch(): Promise<void> {
    if (!this.store.snapshot()) return;
    this.loading.set(true);
    this.error.set(null);
    try {
      const wasNotReady = this.methodNotReady();
      const batch = await this.api.leagueSnapshotPlayersPage(
        this.leagueId(),
        this.method(),
        this.apiGroupBy(),
        this.apiGroupId(),
        this.queryState(),
        0,
      );
      this.rows.set(batch.rows);
      this.totalRecords.set(batch.totalRecords);
      this.resetToken.update((v) => v + 1);
      if (wasNotReady) {
        // that fetch just computed the model — refresh the "ready" flags
        await this.store.refreshSnapshotMeta();
      }
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }

  protected async onLoadMore(): Promise<void> {
    if (this.loading() || this.loadingMore() || !this.hasMore()) return;
    this.loadingMore.set(true);
    this.error.set(null);
    try {
      const nextPage = Math.floor(this.rows().length / RANKED_PAGE_SIZE);
      const batch = await this.api.leagueSnapshotPlayersPage(
        this.leagueId(),
        this.method(),
        this.apiGroupBy(),
        this.apiGroupId(),
        this.queryState(),
        nextPage,
      );
      this.rows.update((rs) => [...rs, ...batch.rows]);
      this.totalRecords.set(batch.totalRecords);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loadingMore.set(false);
    }
  }

  protected async onQueryChange(q: RankedQuery): Promise<void> {
    this.queryState.set(q);
    this.syncUrl();
    await this.resetAndFetch();
  }

  protected async setMethod(m: Method): Promise<void> {
    if (m === this.method()) return;
    this.method.set(m);
    this.syncUrl();
    await this.resetAndFetch();
  }

  private clearRows(): void {
    this.rows.set([]);
    this.totalRecords.set(0);
  }

  protected async setGroupBy(g: 'LEAGUE' | 'ORG'): Promise<void> {
    if (g === this.groupBy()) return;
    this.groupBy.set(g);
    this.syncUrl();
    // LEAGUE needs no pick; ORG waits for an org before refetching
    if (this.hasSelection()) await this.resetAndFetch();
    else this.clearRows();
  }

  protected async setOrg(id: string): Promise<void> {
    this.orgId.set(id || null);
    this.teamId.set(null); // the org's club list just changed — back to "Full org"
    this.syncUrl();
    if (this.hasSelection()) await this.resetAndFetch();
    else this.clearRows();
  }

  protected async setTeam(id: string): Promise<void> {
    this.teamId.set(id || null);
    this.syncUrl();
    if (this.hasSelection()) await this.resetAndFetch();
    else this.clearRows();
  }
}
