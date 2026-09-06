import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MultiSelectModule } from 'primeng/multiselect';

/**
 * Playing-level filter for the live-league view: a checkbox multi-select of the
 * levels present in the snapshot (`leagueLevels` facet, already ordered
 * MLB → AAA → …). Emits the flat list of selected level strings (`[]` = no
 * constraint); values pass straight through to the backend filter. Used in the
 * "Filters" popover and the Lvl column's quick-filter panel.
 */
@Component({
  selector: 'app-level-filter',
  imports: [FormsModule, MultiSelectModule],
  template: `
    @if (label()) {
      <span class="lbl">{{ label() }}</span>
    }
    <p-multiselect
      [options]="levels()"
      [ngModel]="value()"
      (ngModelChange)="valueChange.emit($event ?? [])"
      [showToggleAll]="true"
      display="chip"
      placeholder="Any level"
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
export class LevelFilterComponent {
  /** Optional label shown before the control ("Level"). */
  readonly label = input<string>('');
  /** All selectable levels (the `leagueLevels` facet), MLB-first. */
  readonly levels = input<string[]>([]);
  readonly value = input<string[]>([]);
  readonly valueChange = output<string[]>();
}
