import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NgTemplateOutlet } from '@angular/common';
import { PopoverModule } from 'primeng/popover';
import { DrawerModule } from 'primeng/drawer';

import { NumericFilter } from '../../core/api.types';
import { FILTERABLE_FIELDS, FilterableField } from '../../core/ranked-columns';
import { Viewport } from '../../core/viewport';
import { HandednessFilterComponent } from './handedness-filter';
import { TeamFilterComponent } from './team-filter';
import { LevelFilterComponent } from './level-filter';
import { BestPosFilterComponent } from './best-pos-filter';

const EMIT_DEBOUNCE_MS = 300;

/**
 * "Filters" dropdown: batting / throwing handedness, best position, drafting
 * team, playing level (with a "free agents only" shortcut) and Rule 5
 * eligibility, plus any
 * number of greater-than / less-than bounds on the table's sortable columns
 * (numeric ratings & scores, plus the graded-text and demand columns, compared
 * on their tier ordinal). Everything is AND-combined; the button shows how many
 * groups are actually constraining. Emits the full numeric-row list so
 * half-typed rows survive a refetch — `api.ts` drops the non-constraining ones.
 * On a phone the same panel opens as a bottom sheet instead of a popover.
 */
@Component({
  selector: 'app-numeric-filters',
  imports: [
    FormsModule,
    NgTemplateOutlet,
    PopoverModule,
    DrawerModule,
    HandednessFilterComponent,
    TeamFilterComponent,
    LevelFilterComponent,
    BestPosFilterComponent,
  ],
  template: `
    <button
      type="button"
      class="filter-btn"
      [class.active]="activeCount()"
      (click)="narrow() ? sheetOpen.set(true) : op.toggle($event)"
    >
      Filters@if (activeCount()) { <span class="badge">{{ activeCount() }}</span> }
    </button>

    <p-popover #op appendTo="body">
      <ng-container *ngTemplateOutlet="panel" />
    </p-popover>

    <p-drawer
      [visible]="sheetOpen()"
      (visibleChange)="sheetOpen.set($event)"
      position="bottom"
      header="Filters"
      [blockScroll]="true"
      styleClass="filter-sheet"
    >
      <ng-container *ngTemplateOutlet="panel" />
      <ng-template #footer>
        <button type="button" class="primary done" (click)="sheetOpen.set(false)">Done</button>
      </ng-template>
    </p-drawer>

    <ng-template #panel>
      <div class="panel" [class.sheet]="narrow()">
        <!-- caller-projected controls (mobile: view / position / hide-drafted
             fold in here so the sticky filters strip stays a single row) -->
        <div class="slot" [class.on]="extras()"><ng-content /></div>

        <div class="facets">
          <app-handedness-filter
            label="Bats"
            [value]="batHands()"
            (valueChange)="batHandsChange.emit($event)"
          />
          <app-handedness-filter
            label="Throws"
            [switch]="false"
            [value]="throwHands()"
            (valueChange)="throwHandsChange.emit($event)"
          />
          @if (showBestPos()) {
            <app-best-pos-filter
              label="Best pos"
              [positions]="bestPositions()"
              [value]="bestPosSel()"
              (valueChange)="bestPosChange.emit($event)"
            />
          }
          @if (showTeams() && teams().length) {
            <app-team-filter
              label="Team"
              [teams]="teams()"
              [value]="teamSel()"
              (valueChange)="teamsChange.emit($event)"
            />
          }
          @if (levels().length) {
            <app-level-filter
              label="Level"
              [levels]="levels()"
              [value]="levelSel()"
              (valueChange)="levelsChange.emit($event)"
            />
          }
          @if (showRule5()) {
            <label class="chk" title="Off the 40-man and past the Rule 5 protection window">
              <span class="lbl">Rule 5</span>
              <input
                type="checkbox"
                [ngModel]="rule5Only()"
                (ngModelChange)="rule5OnlyChange.emit($event)"
              />
              <span>Eligible only</span>
            </label>
          }
          @if (levels().includes(FREE_AGENT_LEVEL)) {
            <label class="chk" title="Unsigned pros — shorthand for Level = FA">
              <span class="lbl">FA</span>
              <input
                type="checkbox"
                [ngModel]="freeAgentsOnly()"
                (ngModelChange)="levelsChange.emit($event ? [FREE_AGENT_LEVEL] : [])"
              />
              <span>Free agents only</span>
            </label>
          }
        </div>
        <div class="divider"></div>

        @if (!rows().length) {
          <p class="muted empty">No rating filters. Add one to narrow the table by a rating or score.</p>
        }
        @for (r of rows(); track $index) {
          <div class="frow">
            <select
              [ngModel]="r.field"
              (ngModelChange)="patchField($index, $event)"
              class="field-sel"
            >
              <option value="" disabled>Choose a field…</option>
              @for (g of groups(); track g.label) {
                <optgroup [label]="g.label">
                  @for (f of g.items; track f.field) {
                    <option [value]="f.field">{{ f.name }}</option>
                  }
                </optgroup>
              }
            </select>
            <input
              type="number"
              class="bound"
              placeholder="min"
              [ngModel]="r.min"
              (ngModelChange)="patchBound($index, 'min', $event)"
            />
            <span class="dash">–</span>
            <input
              type="number"
              class="bound"
              placeholder="max"
              [ngModel]="r.max"
              (ngModelChange)="patchBound($index, 'max', $event)"
            />
            <button type="button" class="x" title="Remove" (click)="removeRow($index)">×</button>
          </div>
          @if (isGraded(r.field)) {
            <p class="muted hint">tier scale — 0 lowest … 4 highest</p>
          }
        }

        <div class="foot">
          <button type="button" (click)="addRow()">+ Add filter</button>
          @if (rows().length) {
            <button type="button" class="link" (click)="clearAll()">Clear all</button>
          }
        </div>
      </div>
    </ng-template>
  `,
  styles: [
    `
      :host { display: inline-flex; }
      .filter-btn { font-size: 12px; display: inline-flex; align-items: center; gap: 6px; }
      .filter-btn.active { border-color: var(--accent); color: var(--accent); }
      .badge {
        background: var(--accent);
        color: var(--accent-contrast);
        border-radius: 999px;
        font-size: 11px;
        min-width: 16px;
        text-align: center;
        padding: 0 4px;
      }
      .panel { display: flex; flex-direction: column; gap: 8px; min-width: 22rem; max-width: min(92vw, 26rem); }
      .panel.sheet { min-width: 0; max-width: none; gap: 12px; font-size: 14px; }
      .panel.sheet .slot.on, .panel.sheet .facets { gap: 12px; }
      /* sheet: one label column, controls stretched to the right edge (the
         dropdowns cap their own width inline, hence the !important) */
      .panel.sheet .facets > * { display: flex; }
      .panel.sheet ::ng-deep .lbl,
      .panel.sheet ::ng-deep .m-fld > span { min-width: 4.5rem; }
      .panel.sheet ::ng-deep .p-multiselect,
      .panel.sheet ::ng-deep .p-treeselect,
      .panel.sheet ::ng-deep app-position-filter { flex: 1 1 auto; max-width: none !important; }
      .done { width: 100%; min-height: 44px; }
      .slot { display: none; }
      .slot.on {
        display: flex;
        flex-direction: column;
        gap: 10px;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--border);
      }
      .facets { display: flex; flex-direction: column; gap: 8px; }
      .chk { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; }
      .chk .lbl { color: var(--text-dim); min-width: 3rem; }
      .divider { height: 1px; background: var(--border); margin: 2px 0; }
      .empty { margin: 0; font-size: 12px; }
      .frow { display: flex; align-items: center; gap: 6px; }
      .field-sel { flex: 1 1 auto; min-width: 0; }
      .bound { width: 4.5rem; }
      .dash { color: var(--text-dim); }
      .x {
        border: none;
        background: none;
        color: var(--text-dim);
        font-size: 16px;
        line-height: 1;
        padding: 0 4px;
        cursor: pointer;
      }
      .x:hover { color: var(--drafted); }
      .hint { margin: -2px 0 2px; font-size: 11px; }
      .foot { display: flex; align-items: center; gap: 12px; margin-top: 4px; }
      .link {
        border: none;
        background: none;
        color: var(--text-dim);
        text-decoration: underline;
        cursor: pointer;
        font-size: 12px;
        padding: 0;
      }
      .link:hover { color: var(--accent); }
      .muted { color: var(--text-dim); }
    `,
  ],
})
export class NumericFiltersComponent {
  readonly value = input<NumericFilter[]>([]);
  readonly valueChange = output<NumericFilter[]>();

  /** Show the caller-projected controls block at the top of the panel (mobile
   *  folds the view / position / hide-drafted controls in there). */
  readonly extras = input(false);
  /** Count of active constraints living in that projected block, folded into
   *  the button's badge so hidden filters still register. */
  readonly extraActive = input(0);

  readonly batHands = input<string[]>([]);
  readonly throwHands = input<string[]>([]);
  readonly batHandsChange = output<string[]>();
  readonly throwHandsChange = output<string[]>();

  /** Best-position facet + selection. `showBestPos` gates it to the views that
   *  have a Best-pos column (modeled / batting, not pitching). */
  readonly bestPositions = input<string[]>([]);
  readonly bestPosSel = input<string[]>([]);
  readonly showBestPos = input(false);
  readonly bestPosChange = output<string[]>();

  /** Drafting-team facet + selection. `showTeams` gates the row to the view
   *  that actually has a Team column (modeled). */
  readonly teams = input<string[]>([]);
  readonly teamSel = input<string[]>([]);
  readonly showTeams = input(false);
  readonly teamsChange = output<string[]>();

  /** Playing-level facet + selection (live-league view only). An empty
   *  `levels` list hides the control. */
  readonly levels = input<string[]>([]);
  readonly levelSel = input<string[]>([]);
  readonly levelsChange = output<string[]>();

  /** "Free agents only" toggle: a shortcut for a level selection of just `FA`. */
  protected readonly FREE_AGENT_LEVEL = 'FA';
  protected readonly freeAgentsOnly = computed(
    () => this.levelSel().length === 1 && this.levelSel()[0] === this.FREE_AGENT_LEVEL,
  );

  /** Rule 5 "eligible only" toggle (live-league view only). */
  readonly showRule5 = input(false);
  readonly rule5Only = input(false);
  readonly rule5OnlyChange = output<boolean>();

  protected readonly rows = signal<NumericFilter[]>([]);

  protected readonly narrow = inject(Viewport).narrow;
  /** Phones: the panel's bottom sheet is open. */
  protected readonly sheetOpen = signal(false);

  protected readonly groups = computed(() => {
    const m = new Map<string, { field: string; name: string }[]>();
    for (const f of FILTERABLE_FIELDS) {
      const name = f.label.split(' · ').slice(1).join(' · ') || f.label;
      const bucket = m.get(f.group) ?? m.set(f.group, []).get(f.group)!;
      bucket.push({ field: f.field, name });
    }
    return [...m].map(([label, items]) => ({ label, items }));
  });

  protected readonly activeCount = computed(
    () =>
      this.rows().filter((r) => r.field && (r.min != null || r.max != null)).length +
      (this.batHands().length ? 1 : 0) +
      (this.throwHands().length ? 1 : 0) +
      (this.bestPosSel().length ? 1 : 0) +
      (this.teamSel().length ? 1 : 0) +
      (this.levelSel().length ? 1 : 0) +
      (this.rule5Only() ? 1 : 0) +
      this.extraActive(),
  );

  private emitTimer: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    // Re-hydrate local rows from the parent on a class switch / external reset.
    effect(() => {
      const v = this.value();
      untracked(() => {
        if (!sameRows(v, this.rows())) this.rows.set(v.map((x) => ({ ...x })));
      });
    });
    inject(DestroyRef).onDestroy(() => clearTimeout(this.emitTimer));
  }

  protected isGraded(field: string): boolean {
    return !!FILTERABLE_FIELDS.find((f) => f.field === field)?.graded;
  }

  protected addRow(): void {
    this.rows.update((r) => [...r, { field: '', label: '', min: null, max: null }]);
  }

  protected removeRow(i: number): void {
    this.rows.update((r) => r.filter((_, idx) => idx !== i));
    this.emit();
  }

  protected patchField(i: number, field: string): void {
    const meta = FILTERABLE_FIELDS.find((f) => f.field === field);
    this.rows.update((r) =>
      r.map((row, idx) => (idx === i ? { ...row, field, label: meta?.label ?? field } : row)),
    );
    this.emit();
  }

  protected patchBound(i: number, key: 'min' | 'max', raw: unknown): void {
    const num = raw === '' || raw == null ? null : Number(raw);
    const val = Number.isFinite(num as number) ? (num as number) : null;
    this.rows.update((r) => r.map((row, idx) => (idx === i ? { ...row, [key]: val } : row)));
    this.emit();
  }

  protected clearAll(): void {
    this.rows.set([]);
    this.emit();
  }

  private emit(): void {
    clearTimeout(this.emitTimer);
    this.emitTimer = setTimeout(() => this.valueChange.emit(this.rows()), EMIT_DEBOUNCE_MS);
  }
}

function sameRows(a: NumericFilter[], b: NumericFilter[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((x, i) => x.field === b[i].field && x.min === b[i].min && x.max === b[i].max);
}
