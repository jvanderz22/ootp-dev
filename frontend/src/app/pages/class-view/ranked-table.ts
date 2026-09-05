import {
  Component,
  computed,
  DestroyRef,
  effect,
  ElementRef,
  inject,
  input,
  NgZone,
  output,
  signal,
  untracked,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TagModule } from 'primeng/tag';
import { TableModule } from 'primeng/table';
import { SelectButtonModule } from 'primeng/selectbutton';

import { ClassView, NumericFilter, RankedPlayerRow, RankedQuery } from '../../core/api.types';
import {
  ColumnDef,
  DEFAULT_SORT,
  FILTERABLE_FIELDS,
  VIEW_COLUMNS,
  VIEW_OPTIONS,
  groupSpans,
} from '../../core/ranked-columns';
import { typeSeverity } from '../../core/player-stats';
import { PlayerDetailCardComponent } from './player-detail-card';
import { PositionFilterComponent } from './position-filter';
import { HandednessFilterComponent } from './handedness-filter';
import { TeamFilterComponent } from './team-filter';
import { NumericFiltersComponent } from './numeric-filters';
import { PlayerCompareComponent } from '../player-compare';

const SEARCH_DEBOUNCE_MS = 300;

/** How close to the bottom of the loaded rows (in px) triggers the next
 *  infinite-scroll batch fetch. */
const SCROLL_LOAD_THRESHOLD_PX = 300;

/** Hover-intent before the column-header quick filter opens. */
const COL_POP_DELAY_MS = 400;
/** Grace period after the pointer leaves the header / panel. */
const COL_POP_CLOSE_MS = 220;
/** Gap between the header edge and the panel, and min viewport margin. */
const COL_POP_GAP = 8;
const COL_POP_MARGIN = 8;

@Component({
  selector: 'app-ranked-table',
  imports: [
    FormsModule,
    TableModule,
    TagModule,
    SelectButtonModule,
    PlayerDetailCardComponent,
    PositionFilterComponent,
    HandednessFilterComponent,
    TeamFilterComponent,
    NumericFiltersComponent,
    PlayerCompareComponent,
  ],
  templateUrl: './ranked-table.html',
  styleUrl: './ranked-table.scss',
})
export class RankedTableComponent {
  /** Rows loaded so far (already filtered/sorted by the backend) — grows as
   *  the table scrolls, via `loadMore`. */
  readonly rows = input.required<RankedPlayerRow[]>();
  readonly totalRecords = input.required<number>();
  readonly positions = input.required<string[]>();
  /** Teams that drafted someone in this class — the Team filter's option set. */
  readonly teams = input<string[]>([]);
  /** A from-scratch fetch (filter/sort/view/class change) is in flight. */
  readonly loading = input(false);
  /** An infinite-scroll append (the next batch) is in flight. */
  readonly loadingMore = input(false);
  /** Whether another batch remains to be fetched. */
  readonly hasMore = input(true);
  /** Class name — changing it re-seeds all table state from `initialQuery`. */
  readonly classKey = input.required<string>();
  /** Seed state (parsed from the URL by the container). Applied on first render
   *  and whenever `classKey` changes; `null` falls back to plain defaults. */
  readonly initialQuery = input<RankedQuery | null>(null);
  /** Bumped by the container whenever `rows` was replaced from scratch rather
   *  than appended to — collapses expanded rows and scrolls back to the top. */
  readonly resetToken = input(0);

  readonly queryChange = output<RankedQuery>();
  readonly loadMore = output<void>();
  readonly setRankChange = output<{ id: string; rank: number }>();

  protected readonly typeSeverity = typeSeverity;
  protected readonly viewOptions = VIEW_OPTIONS;

  // ------------------------------------------------------------- table state
  protected readonly view = signal<ClassView>('modeled');
  protected readonly search = signal('');
  protected readonly positionSel = signal<string[]>([]);
  protected readonly batHandSel = signal<string[]>([]);
  protected readonly throwHandSel = signal<string[]>([]);
  protected readonly teamSel = signal<string[]>([]);
  protected readonly hideDrafted = signal(false);
  protected readonly numericFilters = signal<NumericFilter[]>([]);
  protected readonly sortField = signal<string>(DEFAULT_SORT.modeled.field);
  protected readonly sortOrder = signal<1 | -1>(DEFAULT_SORT.modeled.order);

  protected readonly expandAll = signal(false);
  protected readonly expandedKeys = signal<Record<string, boolean>>({});

  protected readonly compareSel = signal<RankedPlayerRow[]>([]);
  protected readonly compareOpen = signal(false);

  // -------------------------------------------------- column-header quick filter
  private readonly filterableFields = new Set(FILTERABLE_FIELDS.map((f) => f.field));
  protected readonly hoverCol = signal<ColumnDef | null>(null);
  protected readonly hoverMin = signal<number | null>(null);
  protected readonly hoverMax = signal<number | null>(null);
  /** Fixed-position coords for the quick-filter panel + which side of the
   *  header it sits on (prefers above, flips below when there's no room). */
  protected readonly colPopStyle = signal<{ top: string; left: string }>({ top: '0', left: '0' });
  protected readonly colPopPlacement = signal<'above' | 'below'>('above');
  /** Held hidden until measured so it never flashes at the corner. */
  protected readonly colPopReady = signal(false);
  private colPopTargetEl: HTMLElement | null = null;
  private colShowTimer: ReturnType<typeof setTimeout> | undefined;
  private colHideTimer: ReturnType<typeof setTimeout> | undefined;
  private readonly dismissColPop = () => this.closeColPop();

  protected readonly columns = computed<ColumnDef[]>(() => VIEW_COLUMNS[this.view()]);
  protected readonly headerGroups = computed(() => groupSpans(this.columns()));

  /** Visible width of the horizontal-scroll viewport, so an expanded row can be
   *  pinned to it instead of stretching the full (overflowing) table width. */
  protected readonly viewportWidth = signal<number | null>(null);

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly zone = inject(NgZone);
  private searchTimer: ReturnType<typeof setTimeout> | undefined;
  private scrollEl: HTMLElement | null = null;

  constructor() {
    // Rows grew — an infinite-scroll append. Under "expand all" the new rows
    // should join the expanded set too; otherwise leave existing expansion
    // (and scroll position) alone. A from-scratch replacement is handled by
    // the `resetToken` effect below, which always wins since it runs after.
    effect(() => {
      const rs = this.rows();
      untracked(() => {
        if (!this.expandAll()) return;
        this.expandedKeys.update((m) => {
          const next = { ...m };
          for (const r of rs) next[r.id] = true;
          return next;
        });
      });
    });

    // The container replaced the row list from scratch (filter/sort/view
    // change, or a mutation that re-fetched everything) — collapse rows (or
    // re-expand under "expand all") and scroll back to the top.
    effect(() => {
      this.resetToken();
      untracked(() => {
        this.applyExpansion();
        this.scrollToTop();
      });
    });

    // Class switched — re-seed from the URL-derived `initialQuery` (the
    // container already fetched that page, so no emit).
    effect(() => {
      this.classKey();
      untracked(() => this.hydrate());
    });

    // Track the scroll viewport width for the pinned detail row, and bind the
    // infinite-scroll listener once the scrollable body exists.
    const measure = () => {
      const el =
        this.host.nativeElement.querySelector<HTMLElement>('.p-datatable-table-container') ??
        this.host.nativeElement;
      const w = el.clientWidth;
      if (w > 0 && w !== this.viewportWidth()) {
        this.zone.run(() => this.viewportWidth.set(w));
      }
      if (el !== this.host.nativeElement && el !== this.scrollEl) {
        this.scrollEl?.removeEventListener('scroll', this.onScroll);
        this.scrollEl = el;
        el.addEventListener('scroll', this.onScroll, { passive: true });
      }
    };
    const ro = new ResizeObserver(measure);
    ro.observe(this.host.nativeElement);
    inject(DestroyRef).onDestroy(() => {
      ro.disconnect();
      this.scrollEl?.removeEventListener('scroll', this.onScroll);
      clearTimeout(this.colShowTimer);
      clearTimeout(this.colHideTimer);
      this.unbindColPopDismiss();
    });
  }

  /** Fires as the table's scroll body moves — asks the container for the next
   *  batch once the loaded rows are nearly scrolled through. */
  private readonly onScroll = (ev: Event): void => {
    const el = ev.target as HTMLElement;
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (remaining > SCROLL_LOAD_THRESHOLD_PX) return;
    if (!this.hasMore() || this.loading() || this.loadingMore()) return;
    this.zone.run(() => this.loadMore.emit());
  };

  private scrollToTop(): void {
    this.scrollEl?.scrollTo({ top: 0 });
  }

  // ----------------------------------------------------------------- columns
  protected sortCaret(c: ColumnDef): string {
    if (this.sortField() !== c.field) return '';
    return this.sortOrder() === 1 ? '▲' : '▼';
  }

  /** Three-click cycle on a header: default direction → inverse → clear (fall
   *  back to the view's default sort). Clicking a different column starts the
   *  cycle at that column's default direction. */
  protected onSort(c: ColumnDef): void {
    const defaultDir: 1 | -1 = c.descFirst ? -1 : 1;
    if (this.sortField() !== c.field) {
      this.sortField.set(c.field);
      this.sortOrder.set(defaultDir);
    } else if (this.sortOrder() === defaultDir) {
      this.sortOrder.set(defaultDir === 1 ? -1 : 1);
    } else {
      const d = DEFAULT_SORT[this.view()];
      this.sortField.set(d.field);
      this.sortOrder.set(d.order);
    }
    this.emitQuery();
  }

  // ------------------------------------------------------------------ filters
  protected onSearch(value: string): void {
    this.search.set(value);
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.emitQuery(), SEARCH_DEBOUNCE_MS);
  }

  protected onPositions(value: string[]): void {
    this.positionSel.set(value);
    this.emitQuery();
  }

  protected onBatHands(value: string[]): void {
    this.batHandSel.set(value);
    this.emitQuery();
  }

  protected onThrowHands(value: string[]): void {
    this.throwHandSel.set(value);
    this.emitQuery();
  }

  protected onTeams(value: string[]): void {
    this.teamSel.set(value);
    this.emitQuery();
  }

  protected onHideDrafted(value: boolean): void {
    this.hideDrafted.set(value);
    this.emitQuery();
  }

  protected onNumericFilters(value: NumericFilter[]): void {
    this.numericFilters.set(value);
    this.emitQuery();
  }

  protected onSetRank(p: RankedPlayerRow, rank: number): void {
    this.setRankChange.emit({ id: p.id, rank });
  }

  protected onView(value: ClassView): void {
    this.view.set(value);
    const d = DEFAULT_SORT[value];
    this.sortField.set(d.field);
    this.sortOrder.set(d.order);
    this.emitQuery();
  }

  // ---------------------------------------------------------------- expansion
  protected toggleAllExpansion(): void {
    this.expandAll.update((v) => !v);
    this.applyExpansion();
  }

  protected toggleRow(p: RankedPlayerRow, event: Event): void {
    if ((event.target as HTMLElement).closest('a, button, input, label, .p-checkbox')) {
      return;
    }
    this.expandedKeys.update((m) => {
      const next = { ...m };
      if (next[p.id]) delete next[p.id];
      else next[p.id] = true;
      return next;
    });
  }

  protected isExpanded(p: RankedPlayerRow): boolean {
    return !!this.expandedKeys()[p.id];
  }

  private applyExpansion(): void {
    this.expandedKeys.set(
      this.expandAll()
        ? Object.fromEntries(this.rows().map((r) => [r.id, true]))
        : {},
    );
  }

  // ------------------------------------------------------------------ compare
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

  // ---------------------------------------------------- column-header quick filter
  /** The categorical identity columns get a checkbox quick filter instead of a
   *  numeric bound: L/R/S for Bats & Throws, a team list for Team. */
  protected isHandCol(c: ColumnDef): boolean {
    return c.field === 'batHand' || c.field === 'throwHand';
  }

  protected isTeamCol(c: ColumnDef): boolean {
    return c.field === 'draftedTeam';
  }

  protected isColFilterable(c: ColumnDef): boolean {
    return this.filterableFields.has(c.field) || this.isHandCol(c) || this.isTeamCol(c);
  }

  /** Existing numeric bound (if any) on a column, for the hover panel prefill. */
  protected colFilter(c: ColumnDef): NumericFilter | undefined {
    return this.numericFilters().find((f) => f.field === c.field);
  }

  /** Whether a column currently constrains the table — a numeric bound for a
   *  rating column, a non-empty selection for Bats / Throws / Team. Drives the
   *  header tint + dot and the hover panel's Clear button. */
  protected isColFiltered(c: ColumnDef): boolean {
    if (c.field === 'batHand') return this.batHandSel().length > 0;
    if (c.field === 'throwHand') return this.throwHandSel().length > 0;
    if (c.field === 'draftedTeam') return this.teamSel().length > 0;
    return !!this.colFilter(c);
  }

  /** Hand quick-filter toggled from a column header — apply immediately and
   *  leave the panel open so more toggles land in the same pass. */
  protected onHoverHands(c: ColumnDef, value: string[]): void {
    if (c.field === 'batHand') this.onBatHands(value);
    else this.onThrowHands(value);
  }

  protected onColEnter(c: ColumnDef, ev: MouseEvent): void {
    if (!this.isColFilterable(c)) return;
    const el = ev.currentTarget as HTMLElement;
    clearTimeout(this.colHideTimer);
    if (el === this.colPopTargetEl) return; // already open / pending on this header
    clearTimeout(this.colShowTimer);
    this.colShowTimer = setTimeout(() => this.openColPop(c, el), COL_POP_DELAY_MS);
  }

  protected onColLeave(): void {
    clearTimeout(this.colShowTimer);
    this.colHideTimer = setTimeout(() => this.closeColPop(), COL_POP_CLOSE_MS);
  }

  protected keepColPop(): void {
    clearTimeout(this.colHideTimer);
  }

  private openColPop(c: ColumnDef, el: HTMLElement): void {
    this.colPopTargetEl = el;
    this.colPopReady.set(false);
    const existing = this.colFilter(c);
    this.hoverMin.set(existing?.min ?? null);
    this.hoverMax.set(existing?.max ?? null);
    this.hoverCol.set(c); // renders the panel (hidden until measured)
    // measure once it's in the DOM, then anchor it to this header
    requestAnimationFrame(() => this.positionColPop(el));
    this.bindColPopDismiss();
  }

  private positionColPop(el: HTMLElement): void {
    const panel = this.host.nativeElement.querySelector<HTMLElement>('.col-quick-filter');
    if (!panel || this.colPopTargetEl !== el) return;
    const r = el.getBoundingClientRect();
    const pw = panel.offsetWidth;
    const ph = panel.offsetHeight;
    const above = r.top >= ph + COL_POP_GAP + COL_POP_MARGIN;
    const top = above ? r.top - ph - COL_POP_GAP : r.bottom + COL_POP_GAP;
    const left = Math.max(
      COL_POP_MARGIN,
      Math.min(r.left, window.innerWidth - pw - COL_POP_MARGIN),
    );
    this.zone.run(() => {
      this.colPopPlacement.set(above ? 'above' : 'below');
      this.colPopStyle.set({ top: `${Math.round(top)}px`, left: `${Math.round(left)}px` });
      this.colPopReady.set(true);
    });
  }

  protected closeColPop(): void {
    clearTimeout(this.colShowTimer);
    clearTimeout(this.colHideTimer);
    this.colPopTargetEl = null;
    this.colPopReady.set(false);
    this.hoverCol.set(null);
    this.unbindColPopDismiss();
  }

  private bindColPopDismiss(): void {
    // any scroll (page or the table's own body) or resize drops the panel
    // rather than letting it drift away from its header
    window.addEventListener('scroll', this.dismissColPop, true);
    window.addEventListener('resize', this.dismissColPop);
  }

  private unbindColPopDismiss(): void {
    window.removeEventListener('scroll', this.dismissColPop, true);
    window.removeEventListener('resize', this.dismissColPop);
  }

  protected numOrNull(v: unknown): number | null {
    const n = Number(v);
    return v === '' || v == null || !Number.isFinite(n) ? null : n;
  }

  protected applyColFilter(): void {
    const c = this.hoverCol();
    if (!c) {
      this.closeColPop();
      return;
    }
    const min = this.hoverMin();
    const max = this.hoverMax();
    const meta = FILTERABLE_FIELDS.find((f) => f.field === c.field);
    const rest = this.numericFilters().filter((f) => f.field !== c.field);
    this.numericFilters.set(
      min == null && max == null
        ? rest
        : [...rest, { field: c.field, label: meta?.label ?? c.field, min, max }],
    );
    this.emitQuery();
    this.closeColPop();
  }

  protected clearColFilter(): void {
    const c = this.hoverCol();
    if (c?.field === 'batHand') {
      this.onBatHands([]);
    } else if (c?.field === 'throwHand') {
      this.onThrowHands([]);
    } else if (c?.field === 'draftedTeam') {
      this.onTeams([]);
    } else if (c && this.colFilter(c)) {
      this.numericFilters.set(this.numericFilters().filter((f) => f.field !== c.field));
      this.emitQuery();
    }
    this.closeColPop();
  }

  // -------------------------------------------------------------------- emit
  private emitQuery(): void {
    this.queryChange.emit({
      view: this.view(),
      search: this.search(),
      positions: this.positionSel(),
      batHands: this.batHandSel(),
      throwHands: this.throwHandSel(),
      teams: this.teamSel(),
      hideDrafted: this.hideDrafted(),
      numericFilters: this.numericFilters(),
      sortField: this.sortField(),
      sortOrder: this.sortOrder(),
    });
  }

  /** Seed every filter/sort signal from `initialQuery` (URL state) on a class
   *  switch; fall back to plain defaults when none was supplied. */
  private hydrate(): void {
    clearTimeout(this.searchTimer);
    const q = this.initialQuery();
    if (!q) {
      this.resetState();
      return;
    }
    this.view.set(q.view);
    this.search.set(q.search);
    this.positionSel.set(q.positions);
    this.batHandSel.set(q.batHands);
    this.throwHandSel.set(q.throwHands);
    this.teamSel.set(q.teams);
    this.hideDrafted.set(q.hideDrafted);
    this.numericFilters.set(q.numericFilters);
    this.sortField.set(q.sortField ?? DEFAULT_SORT[q.view].field);
    this.sortOrder.set(q.sortOrder);
    this.expandAll.set(false);
    this.expandedKeys.set({});
    this.clearCompare();
  }

  private resetState(): void {
    clearTimeout(this.searchTimer);
    this.view.set('modeled');
    this.search.set('');
    this.positionSel.set([]);
    this.batHandSel.set([]);
    this.throwHandSel.set([]);
    this.teamSel.set([]);
    this.hideDrafted.set(false);
    this.numericFilters.set([]);
    this.sortField.set(DEFAULT_SORT.modeled.field);
    this.sortOrder.set(DEFAULT_SORT.modeled.order);
    this.expandAll.set(false);
    this.expandedKeys.set({});
    this.clearCompare();
  }
}
