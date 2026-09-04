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
import { NumericFiltersComponent } from './numeric-filters';
import { PlayerCompareComponent } from '../player-compare';

const SEARCH_DEBOUNCE_MS = 300;

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
    NumericFiltersComponent,
    PlayerCompareComponent,
  ],
  templateUrl: './ranked-table.html',
  styleUrl: './ranked-table.scss',
})
export class RankedTableComponent {
  /** Current page of rows (already filtered/sorted/paginated by the backend). */
  readonly rows = input.required<RankedPlayerRow[]>();
  readonly totalRecords = input.required<number>();
  readonly positions = input.required<string[]>();
  readonly loading = input(false);
  /** Class name — changing it re-seeds all table state from `initialQuery`. */
  readonly classKey = input.required<string>();
  /** Seed state (parsed from the URL by the container). Applied on first render
   *  and whenever `classKey` changes; `null` falls back to plain defaults. */
  readonly initialQuery = input<RankedQuery | null>(null);

  readonly queryChange = output<RankedQuery>();
  readonly setRankChange = output<{ id: string; rank: number }>();

  protected readonly typeSeverity = typeSeverity;
  protected readonly viewOptions = VIEW_OPTIONS;

  // ------------------------------------------------------------- table state
  protected readonly view = signal<ClassView>('modeled');
  protected readonly search = signal('');
  protected readonly positionSel = signal<string[]>([]);
  protected readonly batHandSel = signal<string[]>([]);
  protected readonly throwHandSel = signal<string[]>([]);
  protected readonly hideDrafted = signal(false);
  protected readonly numericFilters = signal<NumericFilter[]>([]);
  protected readonly sortField = signal<string>(DEFAULT_SORT.modeled.field);
  protected readonly sortOrder = signal<1 | -1>(DEFAULT_SORT.modeled.order);
  protected readonly first = signal(0);
  protected readonly pageSize = signal(50);

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

  constructor() {
    // A fresh page arrived — collapse rows, or re-expand them if "expand all"
    // is active. Every sort/filter/page/view change routes through here.
    effect(() => {
      this.rows();
      untracked(() => this.applyExpansion());
    });

    // Class switched — re-seed from the URL-derived `initialQuery` (the
    // container already fetched that page, so no emit).
    effect(() => {
      this.classKey();
      untracked(() => this.hydrate());
    });

    // Track the scroll viewport width for the pinned detail row.
    const measure = () => {
      const el =
        this.host.nativeElement.querySelector<HTMLElement>('.p-datatable-table-container') ??
        this.host.nativeElement;
      const w = el.clientWidth;
      if (w > 0 && w !== this.viewportWidth()) {
        this.zone.run(() => this.viewportWidth.set(w));
      }
    };
    const ro = new ResizeObserver(measure);
    ro.observe(this.host.nativeElement);
    inject(DestroyRef).onDestroy(() => {
      ro.disconnect();
      clearTimeout(this.colShowTimer);
      clearTimeout(this.colHideTimer);
      this.unbindColPopDismiss();
    });
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
    this.first.set(0);
    this.emitQuery();
  }

  // ------------------------------------------------------------------ filters
  protected onSearch(value: string): void {
    this.search.set(value);
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.first.set(0);
      this.emitQuery();
    }, SEARCH_DEBOUNCE_MS);
  }

  protected onPositions(value: string[]): void {
    this.positionSel.set(value);
    this.first.set(0);
    this.emitQuery();
  }

  protected onBatHands(value: string[]): void {
    this.batHandSel.set(value);
    this.first.set(0);
    this.emitQuery();
  }

  protected onThrowHands(value: string[]): void {
    this.throwHandSel.set(value);
    this.first.set(0);
    this.emitQuery();
  }

  protected onHideDrafted(value: boolean): void {
    this.hideDrafted.set(value);
    this.first.set(0);
    this.emitQuery();
  }

  protected onNumericFilters(value: NumericFilter[]): void {
    this.numericFilters.set(value);
    this.first.set(0);
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
    this.first.set(0);
    this.emitQuery();
  }

  /** Paginator / rows-per-page changes. p-table also fires this on init and
   * after we reset `first` ourselves — both are no-ops here (values match). */
  protected onLazyLoad(e: { first?: number | null; rows?: number | null }): void {
    const first = e.first ?? 0;
    const rows = e.rows ?? this.pageSize();
    if (first === this.first() && rows === this.pageSize()) return;
    this.first.set(first);
    this.pageSize.set(rows);
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
  /** The two categorical hand columns get a L/R/S quick filter instead of a
   *  numeric bound. */
  protected isHandCol(c: ColumnDef): boolean {
    return c.field === 'batHand' || c.field === 'throwHand';
  }

  protected isColFilterable(c: ColumnDef): boolean {
    return this.filterableFields.has(c.field) || this.isHandCol(c);
  }

  /** Existing numeric bound (if any) on a column, for the hover panel prefill. */
  protected colFilter(c: ColumnDef): NumericFilter | undefined {
    return this.numericFilters().find((f) => f.field === c.field);
  }

  /** Whether a column currently constrains the table — a numeric bound for a
   *  rating column, a non-empty hand selection for Bats / Throws. Drives the
   *  header tint + dot and the hover panel's Clear button. */
  protected isColFiltered(c: ColumnDef): boolean {
    if (c.field === 'batHand') return this.batHandSel().length > 0;
    if (c.field === 'throwHand') return this.throwHandSel().length > 0;
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
    this.first.set(0);
    this.emitQuery();
    this.closeColPop();
  }

  protected clearColFilter(): void {
    const c = this.hoverCol();
    if (c?.field === 'batHand') {
      this.onBatHands([]);
    } else if (c?.field === 'throwHand') {
      this.onThrowHands([]);
    } else if (c && this.colFilter(c)) {
      this.numericFilters.set(this.numericFilters().filter((f) => f.field !== c.field));
      this.first.set(0);
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
      hideDrafted: this.hideDrafted(),
      numericFilters: this.numericFilters(),
      sortField: this.sortField(),
      sortOrder: this.sortOrder(),
      page: Math.floor(this.first() / this.pageSize()),
      pageSize: this.pageSize(),
    });
  }

  /** Seed every filter/sort/page signal from `initialQuery` (URL state) on a
   *  class switch; fall back to plain defaults when none was supplied. */
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
    this.hideDrafted.set(q.hideDrafted);
    this.numericFilters.set(q.numericFilters);
    this.sortField.set(q.sortField ?? DEFAULT_SORT[q.view].field);
    this.sortOrder.set(q.sortOrder);
    this.pageSize.set(q.pageSize);
    this.first.set(q.page * q.pageSize);
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
    this.hideDrafted.set(false);
    this.numericFilters.set([]);
    this.sortField.set(DEFAULT_SORT.modeled.field);
    this.sortOrder.set(DEFAULT_SORT.modeled.order);
    this.first.set(0);
    this.pageSize.set(50);
    this.expandAll.set(false);
    this.expandedKeys.set({});
    this.clearCompare();
  }
}
