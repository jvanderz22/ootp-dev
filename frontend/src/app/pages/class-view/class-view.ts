import { Component, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ApiService } from '../../core/api';
import { ClassStore } from '../../core/class-store';
import { DraftClass, RankedPlayerPage, RankedQuery } from '../../core/api.types';
import { DEFAULT_SORT } from '../../core/ranked-columns';
import { ClassToolbarComponent } from './class-toolbar';
import { RankedTableComponent } from './ranked-table';
import { ReorderPanelComponent, ReorderRow } from './reorder-panel';

const EMPTY_PAGE: RankedPlayerPage = { rows: [], totalRecords: 0 };

function defaultQuery(): RankedQuery {
  return {
    search: '',
    positions: [],
    hideDrafted: false,
    numericFilters: [],
    sortField: DEFAULT_SORT.modeled.field,
    sortOrder: DEFAULT_SORT.modeled.order,
    page: 0,
    pageSize: 50,
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
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly name = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('name') ?? '')),
    { initialValue: '' },
  );

  protected readonly detail = signal<DraftClass | null>(null);
  protected readonly positions = signal<string[]>([]);
  protected readonly page = signal<RankedPlayerPage>(EMPTY_PAGE);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);

  protected readonly mode = signal<'table' | 'reorder'>('table');
  protected readonly reorderRows = signal<ReorderRow[]>([]);

  /** Plain field (no signal): only the table drives it, via `queryChange`. */
  private query: RankedQuery = defaultQuery();

  protected readonly rows = computed(() => this.page().rows);
  protected readonly totalRecords = computed(() => this.page().totalRecords);
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
    this.query = defaultQuery();
    try {
      const d = await this.api.classDetail(name, this.query);
      this.detail.set(d.draftClass);
      this.positions.set(d.positions);
      this.page.set(d.page);
    } catch (e) {
      this.error.set((e as Error).message);
      this.detail.set(null);
      this.positions.set([]);
      this.page.set(EMPTY_PAGE);
    } finally {
      this.loading.set(false);
    }
  }

  protected async onQueryChange(q: RankedQuery): Promise<void> {
    this.query = q;
    await this.refetch();
  }

  protected async onSetRank(e: { id: string; rank: number }): Promise<void> {
    await this.run('Updating rank…', async () => {
      this.detail.set(await this.api.setPlayerRank(this.name(), e.id, e.rank));
      await this.refetch();
      await this.store.reload();
    });
  }

  private async refetch(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.page.set(await this.api.rankedPlayersPage(this.name(), this.query));
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }

  /** Refresh metadata + current page after a mutation, keeping active filters. */
  private async reloadAfterMutation(): Promise<void> {
    const d = await this.api.classDetail(this.name(), this.query);
    this.detail.set(d.draftClass);
    this.positions.set(d.positions);
    this.page.set(d.page);
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
