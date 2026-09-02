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
  PlayerType,
  RANKING_METHODS,
  RankedPlayer,
  RankedPlayerRow,
} from '../core/api.types';

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

/** Nicer labels for the noisier `components` keys shown in the detail view. */
const KEY_LABELS: Record<string, string> = {
  'Pos - Batting Model': 'Batting model (raw)',
  'Pos - Running Model': 'Running model (raw)',
  'Pos - Overall Model Score': 'Position model (raw)',
  'Pos - Utility Bonus': 'Utility bonus',
  'SP Model Score': 'SP model (raw)',
  'RP Model Score': 'RP model (raw)',
  'SP Base Modifier': 'SP modifiers ×',
  'RP Base Modifier': 'RP modifiers ×',
  'SP Pitcher Pitch Component': 'SP pitch-mix ×',
  'SP HR component': 'SP HR-risk ×',
  'Starter Score w/Modifiers': 'SP score w/ mods',
  'Reliever Score w/Modifiers': 'RP score w/ mods',
  'Pre Rank-adj Rank': 'Pre rank-adjust rank',
  'Pre Rank-adj Score': 'Pre rank-adjust score',
};

interface RatingRow {
  label: string;
  potential: number | null;
  current: number | null;
}

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
  protected classify(p: RankedPlayer): PlayerType {
    const pp = p.positionPlayerScore ?? 0;
    const pit = p.pitcherScore ?? 0;
    const hi = Math.max(pp, pit);
    const lo = Math.min(pp, pit);
    if (hi > 0 && lo * 2 > hi) return 'Two-way';
    return pit >= pp ? 'Pitcher' : 'Hitter';
  }

  private decorate(rows: RankedPlayer[]): RankedPlayerRow[] {
    return rows.map((p) => ({ ...p, type: this.classify(p) }));
  }

  protected typeSeverity(t: PlayerType): 'info' | 'warn' | 'success' {
    return t === 'Two-way' ? 'warn' : t === 'Pitcher' ? 'info' : 'success';
  }

  protected showBatting(t: PlayerType): boolean {
    return t === 'Hitter' || t === 'Two-way';
  }

  protected showPitching(t: PlayerType): boolean {
    return t === 'Pitcher' || t === 'Two-way';
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
    if ((event.target as HTMLElement).closest('a, button, input')) return;
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

  // --------------------------------------------------- scouting attributes
  protected makeupRows(p: RankedPlayer): [string, string][] {
    const r = p.ratings;
    if (!r) return [];
    const rows: [string, string | null][] = [
      ['Bats / Throws', [r.batHand, r.throwHand].filter(Boolean).join(' / ') || null],
      ['Durability', r.injuryProne],
      ['Work ethic', r.workEthic],
      ['Intelligence', r.intelligence],
      ['Leadership', r.leadership],
    ];
    return rows.filter(([, v]) => !!v) as [string, string][];
  }

  protected battingSkillRows(p: RankedPlayer): RatingRow[] {
    const b = p.ratings?.batting;
    if (!b) return [];
    return [
      { label: 'Contact', potential: b['contact'], current: b['contactCur'] },
      { label: 'Gap', potential: b['gap'], current: b['gapCur'] },
      { label: 'Power', potential: b['power'], current: b['powerCur'] },
      { label: 'Eye', potential: b['eye'], current: b['eyeCur'] },
      { label: 'Avoid K', potential: b['avoidK'], current: b['avoidKCur'] },
    ];
  }

  protected speedRows(p: RankedPlayer): [string, number | null][] {
    const b = p.ratings?.batting;
    if (!b) return [];
    return [
      ['Speed', b['speed']],
      ['Steal', b['steal']],
      ['Baserunning', b['running']],
    ];
  }

  protected fieldingRows(p: RankedPlayer): [string, number][] {
    const f = p.ratings?.fielding;
    if (!f) return [];
    const spec: [string, string][] = [
      ['IF range', 'ifRange'], ['IF arm', 'ifArm'], ['IF error', 'ifError'], ['Turn DP', 'turnDp'],
      ['OF range', 'ofRange'], ['OF arm', 'ofArm'], ['OF error', 'ofError'],
      ['C framing', 'cFraming'], ['C blocking', 'cBlocking'], ['C arm', 'cArm'],
    ];
    return spec
      .map(([label, key]) => [label, f[key] ?? 0] as [string, number])
      .filter(([, v]) => v > 0);
  }

  protected pitchingSkillRows(p: RankedPlayer): RatingRow[] {
    const pt = p.ratings?.pitching;
    if (!pt) return [];
    return [
      { label: 'Stuff', potential: pt.stuff, current: pt.stuffCur },
      { label: 'Movement', potential: pt.movement, current: pt.movementCur },
      { label: 'Control', potential: pt.control, current: pt.controlCur },
    ];
  }

  protected pitchingMiscRows(p: RankedPlayer): [string, string][] {
    const pt = p.ratings?.pitching;
    if (!pt) return [];
    const rows: [string, string | number | null][] = [
      ['Stamina', pt.stamina],
      ['Velocity', pt.velocity],
      ['GB type', pt.groundballType],
    ];
    return rows.filter(([, v]) => v != null && v !== 0).map(([k, v]) => [k, String(v)]);
  }

  protected pitchArsenal(p: RankedPlayer) {
    return p.ratings?.pitching.pitches ?? [];
  }

  // ------------------------------------------------------ component grouping
  private pick(p: RankedPlayer, prefixes: string[]): [string, number][] {
    const c = p.components;
    if (!c) return [];
    return Object.entries(c)
      .filter(([k]) => prefixes.some((pre) => k.startsWith(pre)))
      .map(([k, v]) => [k, Number(v)] as [string, number]);
  }

  protected label(key: string): string {
    const mapped = KEY_LABELS[key];
    if (mapped) return mapped;
    const best = key.match(/^Pos - Best Pos Score \((\w+)\)$/);
    if (best) return `Best position (${best[1]})`;
    const rankAdj = key.match(/^Rank-adj Modifier (.+)$/);
    if (rankAdj) return `${this.prettyModifier(rankAdj[1])} (rank-adj)`;
    return key;
  }

  /** "DraftSecondaryPersonalityModifier" -> "Draft secondary personality" */
  private prettyModifier(raw: string): string {
    const s = raw
      .replace(/Modifier$/, '')
      .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
      .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
      .trim();
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : raw;
  }

  protected battingComponents(p: RankedPlayer): [string, number][] {
    return this.pick(p, ['Pos - ']).map(([k, v]) => [this.label(k), v]);
  }

  protected pitchingComponents(p: RankedPlayer): [string, number][] {
    return this.pick(p, ['SP ', 'RP ', 'Starter Score', 'Reliever Score']).map(
      ([k, v]) => [this.label(k), v],
    );
  }

  protected modifierGroup(
    p: RankedPlayer,
    kind: 'pos' | 'pitcher',
  ): { rows: { label: string; value: number }[]; total: number | null } | null {
    const c = p.components;
    if (!c) return null;
    const prefix = kind === 'pos' ? 'Pos Modifier ' : 'Pitcher Modifier ';
    const totalKey = kind === 'pos' ? 'Total Pos Modifier' : 'Total Pitcher Modifier';
    const rows = Object.entries(c)
      .filter(([k]) => k.startsWith(prefix))
      .map(([k, v]) => ({ label: this.prettyModifier(k.slice(prefix.length)), value: Number(v) }));
    if (!rows.length) return null;
    return { rows, total: c[totalKey] != null ? Number(c[totalKey]) : null };
  }

  /** Whether the player has a relevant modifier group to show (type-scoped). */
  protected hasModifiers(p: RankedPlayerRow): boolean {
    return (
      (this.showBatting(p.type) && !!this.modifierGroup(p, 'pos')) ||
      (this.showPitching(p.type) && !!this.modifierGroup(p, 'pitcher'))
    );
  }

  protected otherComponents(p: RankedPlayer): [string, unknown][] {
    const c = p.components;
    if (!c) return [];
    const skip = [
      'Pos - ', 'SP ', 'RP ', 'Starter Score', 'Reliever Score',
      'Pos Modifier ', 'Pitcher Modifier ', 'Total Pos Modifier', 'Total Pitcher Modifier',
    ];
    return Object.entries(c)
      .filter(([k]) => !skip.some((pre) => k.startsWith(pre)))
      .map(([k, v]) => [this.label(k), v] as [string, unknown]);
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
