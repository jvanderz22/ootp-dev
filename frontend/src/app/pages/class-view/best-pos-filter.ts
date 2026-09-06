import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MultiSelectModule } from 'primeng/multiselect';

/**
 * "Best position" filter: a flat checkbox multi-select of the fielding
 * positions (C, 1B, … RF — no Pitchers/Batters grouping). Emits the flat list
 * of selected positions (`[]` = no constraint); values pass straight through to
 * the backend `bestPositions` filter. Lives in the "Filters" popover.
 */
@Component({
  selector: 'app-best-pos-filter',
  imports: [FormsModule, MultiSelectModule],
  template: `
    @if (label()) {
      <span class="lbl">{{ label() }}</span>
    }
    <p-multiselect
      [options]="positions()"
      [ngModel]="value()"
      (ngModelChange)="valueChange.emit($event ?? [])"
      [showToggleAll]="true"
      display="chip"
      placeholder="Any position"
      appendTo="body"
      [style]="{ minWidth: '11rem', maxWidth: '16rem' }"
    />
  `,
  styles: [
    `
      :host { display: inline-flex; align-items: center; gap: 6px; }
      .lbl { color: var(--text-dim); font-size: 12px; min-width: 3rem; }
    `,
  ],
})
export class BestPosFilterComponent {
  /** Optional label shown before the control ("Best pos"). */
  readonly label = input<string>('');
  /** Selectable fielding positions, in display order. */
  readonly positions = input<string[]>([]);
  readonly value = input<string[]>([]);
  readonly valueChange = output<string[]>();
}
