import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MultiSelectModule } from 'primeng/multiselect';

/**
 * Drafting-team filter: a checkbox multi-select of the teams that have made a
 * pick in this class (the `draftTeams` facet). Emits the flat list of selected
 * team names (`[]` = no constraint); values pass straight through to the
 * backend filter. Used in the "Filters" popover and the Team column's
 * quick-filter panel.
 */
@Component({
  selector: 'app-team-filter',
  imports: [FormsModule, MultiSelectModule],
  template: `
    @if (label()) {
      <span class="lbl">{{ label() }}</span>
    }
    <p-multiselect
      [options]="teams()"
      [ngModel]="value()"
      (ngModelChange)="valueChange.emit($event ?? [])"
      [filter]="true"
      [showToggleAll]="true"
      display="chip"
      placeholder="Any team"
      appendTo="body"
      [style]="{ minWidth: '13rem', maxWidth: '18rem' }"
    />
  `,
  styles: [
    `
      :host { display: inline-flex; align-items: center; gap: 6px; }
      .lbl { color: var(--text-dim); font-size: 12px; min-width: 3rem; }
    `,
  ],
})
export class TeamFilterComponent {
  /** Optional label shown before the control ("Team"). */
  readonly label = input<string>('');
  /** All selectable teams (the `draftTeams` facet for the class). */
  readonly teams = input<string[]>([]);
  readonly value = input<string[]>([]);
  readonly valueChange = output<string[]>();
}
