import { Component, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ApiService } from '../../core/api';
import { ClassStore } from '../../core/class-store';
import { LeagueStore } from '../../core/league-store';
import { DraftClass, RANKED_PAGE_SIZE, RankedPlayer, RankedQuery } from '../../core/api.types';
import { DEFAULT_SORT } from '../../core/ranked-columns';
import { paramsToQuery, queryToParams } from '../../core/table-url';
import { ClassToolbarComponent } from './class-toolbar';
import { RankedTableComponent } from './ranked-table';
import { ReorderPanelComponent, ReorderRow } from './reorder-panel';

function defaultQuery(): RankedQuery {
  return {
    view: 'modeled',
    search: '',
    positions: [],
    batHands: [],
    throwHands: [],
    teams: [],
    hideDrafted: false,
    numericFilters: [],
    sortField: DEFAULT_SORT.modeled.field,
    sortOrder: DEFAULT_SORT.modeled.order,
  };
}

@Component({
  selector: 'app-class-view',
  imports: [ClassToolbarComponent, RankedTableComponent, ReorderPanelComponent],
  templateUrl: './class-view.html',
  styleUrl: './class-view.scss',
})
export class ClassViewPage {
  private readonly api = inject(ApiService);
  private readonly store = inject(ClassStore);
  protected readonly leagueStore = inject(LeagueStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly name = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('name') ?? '')),
    { initialValue: '' },
  );

  protected readonly detail = signal<DraftClass | null>(null);
  protected readonly positions = signal<string[]>([]);
  protected readonly teams = signal<string[]>([]);
  /** Rows loaded so far — grows in `RANKED_PAGE_SIZE` batches as the table
   *  scrolls, and is replaced outright on a filter/sort/view reset. */
  protected readonly rows = signal<RankedPlayer[]>([]);
  protected readonly totalRecords = signal(0);
  /** A from-scratch fetch (class switch, filter/sort/view change) is in
   *  flight — as opposed to `loadingMore`, an infinite-scroll append. */
  protected readonly loading = signal(false);
  protected readonly loadingMore = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);

  protected readonly mode = signal<'table' | 'reorder'>('table');
  protected readonly reorderRows = signal<ReorderRow[]>([]);

  /** Active table query. Seeded from the URL on load, then driven by the table
   *  via `queryChange` (which also writes it back to the URL). */
  protected readonly queryState = signal<RankedQuery>(defaultQuery());
  /** Bumped whenever `rows` is replaced from scratch rather than appended to,
   *  so the table knows to collapse expanded rows and scroll back to the top. */
  protected readonly resetToken = signal(0);

  protected readonly hasMore = computed(() => this.rows().length < this.totalRecords());
  protected readonly notProcessed = computed(
    () => !!this.detail() && !this.detail()!.lastProcessed,
  );

  constructor() {
    effect(() => {
      const name = this.name();
      if (name) this.load(name);
    });
  }

  private async load(name: string): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    this.notice.set(null);
    this.mode.set('table');
    this.queryState.set(paramsToQuery(this.route.snapshot.queryParamMap));
    try {
      const d = await this.api.classDetail(name, this.queryState());
      this.detail.set(d.draftClass);
      this.positions.set(d.positions);
      this.teams.set(d.teams);
      this.rows.set(d.page.rows);
      this.totalRecords.set(d.page.totalRecords);
      this.resetToken.update((v) => v + 1);
    } catch (e) {
      this.error.set((e as Error).message);
      this.detail.set(null);
      this.positions.set([]);
      this.teams.set([]);
      this.rows.set([]);
      this.totalRecords.set(0);
    } finally {
      this.loading.set(false);
    }
  }

  /** Sort/filter/view changed — reset to the first batch, per the infinite
   *  scroll contract (URL-shareable state resumes at the top, not mid-scroll). */
  protected async onQueryChange(q: RankedQuery): Promise<void> {
    this.queryState.set(q);
    // replaceUrl: a filter tweak shouldn't stack a history entry per keystroke.
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: queryToParams(q),
      replaceUrl: true,
    });
    await this.resetAndFetch();
  }

  /** Scrolled to the bottom of the loaded rows — fetch the next batch and
   *  append it, leaving what's already on screen untouched. */
  protected async onLoadMore(): Promise<void> {
    if (this.loading() || this.loadingMore() || !this.hasMore()) return;
    this.loadingMore.set(true);
    this.error.set(null);
    try {
      const nextPage = Math.floor(this.rows().length / RANKED_PAGE_SIZE);
      const batch = await this.api.rankedPlayersPage(this.name(), this.queryState(), nextPage);
      this.rows.update((rs) => [...rs, ...batch.rows]);
      this.totalRecords.set(batch.totalRecords);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loadingMore.set(false);
    }
  }

  protected async onSetRank(e: { id: string; rank: number }): Promise<void> {
    await this.run('Updating rank…', async () => {
      this.detail.set(await this.api.setPlayerRank(this.name(), e.id, e.rank));
      await this.reloadRowsKeepingDepth();
      await this.store.reload();
    });
  }

  private async resetAndFetch(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const batch = await this.api.rankedPlayersPage(this.name(), this.queryState(), 0);
      this.rows.set(batch.rows);
      this.totalRecords.set(batch.totalRecords);
      this.resetToken.update((v) => v + 1);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }

  /** Re-fetches as many rows as are currently loaded (at least one batch) —
   *  for a change that can reshuffle the whole ranking without resetting how
   *  far the user has scrolled. */
  private async reloadRowsKeepingDepth(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const count = Math.max(this.rows().length, RANKED_PAGE_SIZE);
      const batch = await this.api.rankedPlayersPage(this.name(), this.queryState(), 0, count);
      this.rows.set(batch.rows);
      this.totalRecords.set(batch.totalRecords);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }

  /** Refresh metadata + loaded rows after a mutation, keeping active filters
   *  and scroll depth (see `reloadRowsKeepingDepth`). */
  private async reloadAfterMutation(): Promise<void> {
    const count = Math.max(this.rows().length, RANKED_PAGE_SIZE);
    const d = await this.api.classDetail(this.name(), this.queryState(), count);
    this.detail.set(d.draftClass);
    this.positions.set(d.positions);
    this.teams.set(d.teams);
    this.rows.set(d.page.rows);
    this.totalRecords.set(d.page.totalRecords);
  }

  // -------------------------------------------------------------- mutations
  private async run(label: string, fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(label);
    this.error.set(null);
    this.notice.set(null);
    try {
      await fn();
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.busy.set(null);
    }
  }

  protected async onMethodChange(method: string): Promise<void> {
    await this.run('Re-ranking…', async () => {
      this.detail.set(await this.api.setRankingMethod(this.name(), method));
      await this.reloadAfterMutation();
      await this.store.reload();
    });
  }

  protected async reprocess(): Promise<void> {
    await this.run('Reprocessing…', async () => {
      this.detail.set(await this.api.reprocess(this.name()));
      await this.reloadAfterMutation();
      await this.store.reload();
    });
  }

  protected async onSetLeague(leagueId: string | null): Promise<void> {
    await this.run('Updating league…', async () => {
      this.detail.set(await this.api.setClassLeague(this.name(), leagueId));
      await this.store.reload();
      await this.leagueStore.reload();
    });
  }

  protected async replaceFile(file: File): Promise<void> {
    if (
      !confirm(
        `Replace the data for "${this.name()}" with "${file.name}"? ` +
          `The custom order and drafted list are kept; rankings are recomputed.`,
      )
    )
      return;
    const method = this.detail()?.rankingMethod ?? 'draft_class';
    await this.run('Uploading new file… (recomputes rankings, ~10s)', async () => {
      this.detail.set(await this.api.uploadDraftClass(this.name(), method, file));
      await this.reloadAfterMutation();
      await this.store.reload();
    });
  }

  protected async refreshDrafted(): Promise<void> {
    await this.run('Contacting StatsPlus…', async () => {
      const r = await this.api.refreshDrafted(this.name());
      this.notice.set(
        `${r.draftedCount} drafted players matched (${r.unmatched} picks not in this class).`,
      );
      await this.reloadAfterMutation();
      await this.store.reload();
    });
  }

  protected download(): void {
    void this.run('Preparing CSV…', () => this.api.downloadUploadCsv(this.name()));
  }

  protected async deleteClass(): Promise<void> {
    if (!confirm(`Delete draft class "${this.name()}"? This removes its data and rankings.`))
      return;
    await this.run('Deleting…', async () => {
      await this.api.deleteClass(this.name());
      await this.store.reload();
      await this.router.navigate(['/']);
    });
  }

  // ---------------------------------------------------------- custom order
  protected async startReorder(): Promise<void> {
    await this.run('Loading order…', async () => {
      this.reorderRows.set(await this.api.reorderPlayers(this.name()));
      this.mode.set('reorder');
    });
  }

  protected cancelReorder(): void {
    this.mode.set('table');
  }

  protected async saveOrder(order: string[]): Promise<void> {
    await this.run('Saving order…', async () => {
      this.detail.set(await this.api.saveCustomOrder(this.name(), order));
      this.mode.set('table');
      await this.reloadAfterMutation();
      await this.store.reload();
    });
  }

  protected async revertOrder(): Promise<void> {
    await this.run('Reverting…', async () => {
      this.detail.set(await this.api.clearCustomOrder(this.name()));
      this.mode.set('table');
      await this.reloadAfterMutation();
      await this.store.reload();
    });
  }
}
