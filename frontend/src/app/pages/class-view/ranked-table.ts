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

import { ClassView, RankedPlayerRow, RankedQuery } from '../../core/api.types';
import {
  ColumnDef,
  DEFAULT_SORT,
  VIEW_COLUMNS,
  VIEW_OPTIONS,
  groupSpans,
} from '../../core/ranked-columns';
import { typeSeverity } from '../../core/player-stats';
import { PlayerDetailCardComponent } from './player-detail-card';
import { PositionFilterComponent } from './position-filter';
import { PlayerCompareComponent } from '../player-compare';

const SEARCH_DEBOUNCE_MS = 300;

@Component({
  selector: 'app-ranked-table',
  imports: [
    FormsModule,
    TableModule,
    TagModule,
    SelectButtonModule,
    PlayerDetailCardComponent,
    PositionFilterComponent,
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
  /** Class name — changing it resets all table state. */
  readonly classKey = input.required<string>();

  readonly queryChange = output<RankedQuery>();

  protected readonly typeSeverity = typeSeverity;
  protected readonly viewOptions = VIEW_OPTIONS;

  // ------------------------------------------------------------- table state
  protected readonly view = signal<ClassView>('modeled');
  protected readonly search = signal('');
  protected readonly positionSel = signal<string[]>([]);
  protected readonly hideDrafted = signal(false);
  protected readonly sortField = signal<string>(DEFAULT_SORT.modeled.field);
  protected readonly sortOrder = signal<1 | -1>(DEFAULT_SORT.modeled.order);
  protected readonly first = signal(0);
  protected readonly pageSize = signal(50);

  protected readonly expandAll = signal(false);
  protected readonly expandedKeys = signal<Record<string, boolean>>({});

  protected readonly compareSel = signal<RankedPlayerRow[]>([]);
  protected readonly compareOpen = signal(false);

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

    // Class switched — drop back to defaults (the container already fetched
    // a fresh default page, so no emit).
    effect(() => {
      this.classKey();
      untracked(() => this.resetState());
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
    inject(DestroyRef).onDestroy(() => ro.disconnect());
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

  protected onHideDrafted(value: boolean): void {
    this.hideDrafted.set(value);
    this.first.set(0);
    this.emitQuery();
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

  // -------------------------------------------------------------------- emit
  private emitQuery(): void {
    this.queryChange.emit({
      search: this.search(),
      positions: this.positionSel(),
      hideDrafted: this.hideDrafted(),
      sortField: this.sortField(),
      sortOrder: this.sortOrder(),
      page: Math.floor(this.first() / this.pageSize()),
      pageSize: this.pageSize(),
    });
  }

  private resetState(): void {
    clearTimeout(this.searchTimer);
    this.view.set('modeled');
    this.search.set('');
    this.positionSel.set([]);
    this.hideDrafted.set(false);
    this.sortField.set(DEFAULT_SORT.modeled.field);
    this.sortOrder.set(DEFAULT_SORT.modeled.order);
    this.first.set(0);
    this.pageSize.set(50);
    this.expandAll.set(false);
    this.expandedKeys.set({});
    this.clearCompare();
  }
}
