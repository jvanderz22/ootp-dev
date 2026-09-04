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
import { PopoverModule } from 'primeng/popover';

import { NumericFilter } from '../../core/api.types';
import { FILTERABLE_FIELDS, FilterableField } from '../../core/ranked-columns';
import { HandednessFilterComponent } from './handedness-filter';
import { TeamFilterComponent } from './team-filter';

const EMIT_DEBOUNCE_MS = 300;

/**
 * "Filters" dropdown: batting / throwing handedness and drafting team, plus any
 * number of greater-than / less-than bounds on the table's sortable columns
 * (numeric ratings & scores, plus the graded-text and demand columns, compared
 * on their tier ordinal). Everything is AND-combined; the button shows how many
 * groups are actually constraining. Emits the full numeric-row list so
 * half-typed rows survive a refetch — `api.ts` drops the non-constraining ones.
 */
@Component({
  selector: 'app-numeric-filters',
  imports: [FormsModule, PopoverModule, HandednessFilterComponent, TeamFilterComponent],
  template: `
    <button type="button" class="filter-btn" [class.active]="activeCount()" (click)="op.toggle($event)">
      Filters@if (activeCount()) { <span class="badge">{{ activeCount() }}</span> }
    </button>

    <p-popover #op appendTo="body">
      <div class="panel">
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
          @if (showTeams() && teams().length) {
            <app-team-filter
              label="Team"
              [teams]="teams()"
              [value]="teamSel()"
              (valueChange)="teamsChange.emit($event)"
            />
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
    </p-popover>
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
      .panel { display: flex; flex-direction: column; gap: 8px; min-width: 22rem; }
      .facets { display: flex; flex-direction: column; gap: 8px; }
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

  readonly batHands = input<string[]>([]);
  readonly throwHands = input<string[]>([]);
  readonly batHandsChange = output<string[]>();
  readonly throwHandsChange = output<string[]>();

  /** Drafting-team facet + selection. `showTeams` gates the row to the view
   *  that actually has a Team column (modeled). */
  readonly teams = input<string[]>([]);
  readonly teamSel = input<string[]>([]);
  readonly showTeams = input(false);
  readonly teamsChange = output<string[]>();

  protected readonly rows = signal<NumericFilter[]>([]);

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
      (this.teamSel().length ? 1 : 0),
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
