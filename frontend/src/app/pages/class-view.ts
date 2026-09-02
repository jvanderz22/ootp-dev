import { Component, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';
import {
  CdkDrag,
  CdkDragDrop,
  CdkDropList,
  moveItemInArray,
} from '@angular/cdk/drag-drop';

import { ApiService } from '../core/api';
import { ClassStore } from '../core/class-store';
import { DraftClass, RANKING_METHODS, RankedPlayer } from '../core/api.types';

type SortKey = 'rank' | 'name' | 'position' | 'age' | 'modelScore' | 'inGamePotential';

@Component({
  selector: 'app-class-view',
  imports: [FormsModule, DecimalPipe, CdkDropList, CdkDrag],
  templateUrl: './class-view.html',
  styleUrl: './class-view.scss',
})
export class ClassViewPage {
  private readonly api = inject(ApiService);
  private readonly store = inject(ClassStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly methods = RANKING_METHODS;
  protected readonly name = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('name') ?? '')),
    { initialValue: '' },
  );

  protected readonly detail = signal<DraftClass | null>(null);
  protected readonly players = signal<RankedPlayer[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);

  protected readonly mode = signal<'table' | 'reorder'>('table');
  protected readonly draft = signal<RankedPlayer[]>([]);

  protected search = '';
  protected positionFilter = '';
  protected readonly sortKey = signal<SortKey>('rank');
  protected readonly sortDir = signal<1 | -1>(1);
  protected readonly expanded = signal<Set<string>>(new Set());

  protected readonly positions = computed(() =>
    [...new Set(this.players().map((p) => p.position))].sort(),
  );

  protected readonly notProcessed = computed(
    () => !!this.detail() && this.players().length === 0 && !this.detail()!.lastProcessed,
  );

  protected readonly view = computed(() => {
    const q = this.search.trim().toLowerCase();
    const pos = this.positionFilter;
    const key = this.sortKey();
    const dir = this.sortDir();
    let rows = this.players().filter(
      (p) =>
        (!q || p.name.toLowerCase().includes(q)) && (!pos || p.position === pos),
    );
    rows = [...rows].sort((a, b) => {
      const av = a[key] ?? 0;
      const bv = b[key] ?? 0;
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
    return rows;
  });

  constructor() {
    effect(() => {
      const name = this.name();
      if (name) this.load(name);
    });
  }

  private async load(name: string): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    this.mode.set('table');
    try {
      const d = await this.api.classDetail(name);
      this.detail.set(d.draftClass);
      this.players.set(d.rankedPlayers);
    } catch (e) {
      this.error.set((e as Error).message);
      this.players.set([]);
      this.detail.set(null);
    } finally {
      this.loading.set(false);
    }
  }

  protected sortBy(key: SortKey): void {
    if (this.sortKey() === key) {
      this.sortDir.set(this.sortDir() === 1 ? -1 : 1);
    } else {
      this.sortKey.set(key);
      this.sortDir.set(1);
    }
  }

  protected toggleRow(id: string): void {
    const next = new Set(this.expanded());
    next.has(id) ? next.delete(id) : next.add(id);
    this.expanded.set(next);
  }

  protected componentEntries(p: RankedPlayer): [string, unknown][] {
    return p.components ? Object.entries(p.components) : [];
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
      const cls = await this.api.setRankingMethod(this.name(), method);
      this.detail.set(cls);
      await this.reloadPlayers();
      await this.store.reload();
    });
  }

  protected async reprocess(): Promise<void> {
    await this.run('Reprocessing…', async () => {
      const cls = await this.api.reprocess(this.name());
      this.detail.set(cls);
      await this.reloadPlayers();
      await this.store.reload();
    });
  }

  protected async refreshDrafted(): Promise<void> {
    await this.run('Contacting StatsPlus…', async () => {
      const r = await this.api.refreshDrafted(this.name());
      this.notice.set(
        `${r.draftedCount} drafted players matched (${r.unmatched} picks not in this class).`,
      );
      await this.reloadPlayers();
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

  private async reloadPlayers(): Promise<void> {
    const d = await this.api.classDetail(this.name());
    this.detail.set(d.draftClass);
    this.players.set(d.rankedPlayers);
  }

  // ---------------------------------------------------------- custom order
  protected startReorder(): void {
    this.draft.set([...this.players()]);
    this.mode.set('reorder');
  }

  protected cancelReorder(): void {
    this.mode.set('table');
  }

  protected drop(ev: CdkDragDrop<RankedPlayer[]>): void {
    const list = [...this.draft()];
    moveItemInArray(list, ev.previousIndex, ev.currentIndex);
    this.draft.set(list);
  }

  protected async saveOrder(): Promise<void> {
    await this.run('Saving order…', async () => {
      const rows = await this.api.saveCustomOrder(
        this.name(),
        this.draft().map((p) => p.id),
      );
      this.players.set(rows);
      this.mode.set('table');
      await this.store.reload();
      const d = this.detail();
      if (d) this.detail.set({ ...d, hasCustomOrder: true });
    });
  }

  protected async revertOrder(): Promise<void> {
    await this.run('Reverting…', async () => {
      const rows = await this.api.clearCustomOrder(this.name());
      this.players.set(rows);
      this.mode.set('table');
      await this.store.reload();
      const d = this.detail();
      if (d) this.detail.set({ ...d, hasCustomOrder: false });
    });
  }
}
