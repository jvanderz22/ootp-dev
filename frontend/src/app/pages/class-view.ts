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
import { Table, TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { SelectModule } from 'primeng/select';
import { MultiSelectModule } from 'primeng/multiselect';
import { PanelModule } from 'primeng/panel';

import { ApiService } from '../core/api';
import { ClassStore } from '../core/class-store';
import {
  DraftClass,
  RankedPlayer,
  RankedPlayerRow,
  RANKING_METHODS,
} from '../core/api.types';
import {
  battingComponents,
  battingSkillRows,
  classify,
  demandSortKey,
  fieldingRows,
  hasModifiers,
  makeupRows,
  modifierGroup,
  otherComponents,
  pitchArsenal,
  pitchingComponents,
  pitchingMiscRows,
  pitchingSkillRows,
  showBatting,
  showPitching,
  speedRows,
  typeSeverity,
} from '../core/player-stats';
import { PlayerCompareComponent } from './player-compare';

/** Pitchers first, then scorekeeping order for position players. */
const POSITION_ORDER = [
  'P', 'SP', 'RP', 'CL',
  'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'OF', 'IF', 'DH',
];

interface ModelColumn {
  field: keyof RankedPlayer;
  header: string;
  group: 'In-Game' | 'Model';
}

const MODEL_COLUMNS: ModelColumn[] = [
  { field: 'inGameOverall', header: 'OVR', group: 'In-Game' },
  { field: 'inGamePotential', header: 'POT', group: 'In-Game' },
  { field: 'modelScore', header: 'Overall', group: 'Model' },
  { field: 'positionPlayerScore', header: 'Batter', group: 'Model' },
  { field: 'pitcherScore', header: 'Pitcher', group: 'Model' },
  { field: 'battingScoreComponent', header: 'Batting', group: 'Model' },
  { field: 'fieldingScoreComponent', header: 'Fielding', group: 'Model' },
  { field: 'runningScoreComponent', header: 'Running', group: 'Model' },
  { field: 'starterComponent', header: 'SP', group: 'Model' },
  { field: 'relieverComponent', header: 'RP', group: 'Model' },
];

@Component({
  selector: 'app-class-view',
  imports: [
    FormsModule,
    DecimalPipe,
    CdkDropList,
    CdkDrag,
    TableModule,
    TagModule,
    SelectModule,
    MultiSelectModule,
    PanelModule,
    PlayerCompareComponent,
  ],
  templateUrl: './class-view.html',
  styleUrl: './class-view.scss',
})
export class ClassViewPage {
  private readonly api = inject(ApiService);
  private readonly store = inject(ClassStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly methodOptions = [...RANKING_METHODS];
  protected readonly modelColumns = MODEL_COLUMNS;
  protected readonly inGameCount = MODEL_COLUMNS.filter((c) => c.group === 'In-Game').length;
  protected readonly modelCount = MODEL_COLUMNS.filter((c) => c.group === 'Model').length;

  // Scouting-row builders shared with the compare view (see core/player-stats).
  protected readonly showBatting = showBatting;
  protected readonly showPitching = showPitching;
  protected readonly typeSeverity = typeSeverity;
  protected readonly makeupRows = makeupRows;
  protected readonly battingSkillRows = battingSkillRows;
  protected readonly speedRows = speedRows;
  protected readonly fieldingRows = fieldingRows;
  protected readonly pitchingSkillRows = pitchingSkillRows;
  protected readonly pitchingMiscRows = pitchingMiscRows;
  protected readonly pitchArsenal = pitchArsenal;
  protected readonly battingComponents = battingComponents;
  protected readonly pitchingComponents = pitchingComponents;
  protected readonly hasModifiers = hasModifiers;
  protected readonly modifierGroup = modifierGroup;
  protected readonly otherComponents = otherComponents;

  protected readonly name = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('name') ?? '')),
    { initialValue: '' },
  );

  protected readonly detail = signal<DraftClass | null>(null);
  protected readonly players = signal<RankedPlayerRow[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);

  protected readonly mode = signal<'table' | 'reorder'>('table');
  protected readonly draft = signal<RankedPlayerRow[]>([]);

  protected readonly search = signal('');
  protected readonly positionFilter = signal<string[]>([]);
  protected readonly hideDrafted = signal(false);

  /** Up to two players picked for the side-by-side compare dialog. */
  protected readonly compareSel = signal<RankedPlayerRow[]>([]);
  protected readonly compareOpen = signal(false);

  protected readonly positions = computed(() => {
    const uniq = [...new Set(this.players().map((p) => p.position))];
    return uniq.sort((a, b) => {
      const ia = POSITION_ORDER.indexOf(a);
      const ib = POSITION_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    });
  });

  protected readonly draftedCount = computed(
    () => this.players().filter((p) => p.drafted).length,
  );

  protected readonly notProcessed = computed(
    () => !!this.detail() && this.players().length === 0 && !this.detail()!.lastProcessed,
  );

  /** Filtered rows; sorting + pagination are handled by p-table. */
  protected readonly view = computed(() => {
    const q = this.search().trim().toLowerCase();
    const pos = this.positionFilter();
    const hide = this.hideDrafted();
    return this.players().filter(
      (p) =>
        (!q || p.name.toLowerCase().includes(q)) &&
        (pos.length === 0 || pos.includes(p.position)) &&
        (!hide || !p.drafted),
    );
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
    this.clearCompare();
    try {
      const d = await this.api.classDetail(name);
      this.detail.set(d.draftClass);
      this.players.set(this.decorate(d.rankedPlayers));
    } catch (e) {
      this.error.set((e as Error).message);
      this.players.set([]);
      this.detail.set(null);
    } finally {
      this.loading.set(false);
    }
  }

  // ---------------------------------------------------------- player typing
  private decorate(rows: RankedPlayer[]): RankedPlayerRow[] {
    return rows.map((p) => ({ ...p, type: classify(p), demandKey: demandSortKey(p.demand) }));
  }

  /**
   * Model / in-game value columns sort high→low on the first click, then toggle.
   * (PrimeNG only has a single global `defaultSortOrder`, so we drive these
   * columns manually while the identity columns keep the default asc-first.)
   */
  protected sortModelCol(dt: Table, field: keyof RankedPlayer): void {
    if (dt.sortField !== field) {
      dt.sortField = field as string;
      dt.sortOrder = 1; // so the flip in dt.sort() lands on -1 (desc)
    }
    dt.sort({ field: field as string });
  }

  protected toggleRow(dt: Table, row: RankedPlayerRow, event: Event): void {
    // Ignore clicks that originate on interactive controls inside the row.
    if ((event.target as HTMLElement).closest('a, button, input, label')) return;
    dt.toggleRow(row, event);
  }

  /** Cell text for a dynamic model column: ints for the in-game ratings, 2dp otherwise. */
  protected fmt(value: unknown, field: keyof RankedPlayer): string {
    if (value == null || value === '') return '—';
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    if (field === 'inGameOverall' || field === 'inGamePotential') {
      return String(Math.round(n));
    }
    return n.toFixed(2);
  }

  // ------------------------------------------------------------- compare
  protected isSelected(p: RankedPlayerRow): boolean {
    return this.compareSel().some((x) => x.id === p.id);
  }

  protected toggleCompare(p: RankedPlayerRow): void {
    const cur = this.compareSel();
    if (cur.some((x) => x.id === p.id)) {
      this.compareSel.set(cur.filter((x) => x.id !== p.id));
    } else {
      this.compareSel.set([...cur, p].slice(-2));
    }
  }

  protected openCompare(): void {
    if (this.compareSel().length === 2) this.compareOpen.set(true);
  }

  protected clearCompare(): void {
    this.compareSel.set([]);
    this.compareOpen.set(false);
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
    this.players.set(this.decorate(d.rankedPlayers));
    this.clearCompare();
  }

  // ---------------------------------------------------------- custom order
  protected startReorder(): void {
    this.draft.set([...this.players()]);
    this.mode.set('reorder');
  }

  protected cancelReorder(): void {
    this.mode.set('table');
  }

  protected drop(ev: CdkDragDrop<RankedPlayerRow[]>): void {
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
      this.players.set(this.decorate(rows));
      this.mode.set('table');
      await this.store.reload();
      const d = this.detail();
      if (d) this.detail.set({ ...d, hasCustomOrder: true });
    });
  }

  protected async revertOrder(): Promise<void> {
    await this.run('Reverting…', async () => {
      const rows = await this.api.clearCustomOrder(this.name());
      this.players.set(this.decorate(rows));
      this.mode.set('table');
      await this.store.reload();
      const d = this.detail();
      if (d) this.detail.set({ ...d, hasCustomOrder: false });
    });
  }
}
