import { Component, computed, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SelectButtonModule } from 'primeng/selectbutton';

/**
 * Batting- or throwing-hand filter: a small R / L (/ S) multi-select. Emits the
 * flat list of selected hand values (`[]` = no constraint); the values match
 * the raw payload (`Right` / `Left` / `Switch`) so they pass straight through
 * to the backend filter. Used inside the "Filters" popover and the
 * column-header quick-filter panel. `switch` is off for throwing hand — the
 * data only ever has R / L there.
 */
@Component({
  selector: 'app-handedness-filter',
  imports: [FormsModule, SelectButtonModule],
  template: `
    @if (label()) {
      <span class="lbl">{{ label() }}</span>
    }
    <p-selectbutton
      [options]="options()"
      optionLabel="label"
      optionValue="value"
      [multiple]="true"
      [allowEmpty]="true"
      [ngModel]="value()"
      (ngModelChange)="valueChange.emit($event ?? [])"
    />
  `,
  styles: [
    `
      :host { display: inline-flex; align-items: center; gap: 6px; }
      .lbl { color: var(--text-dim); font-size: 12px; min-width: 3rem; }
    `,
  ],
})
export class HandednessFilterComponent {
  /** Field label shown before the toggle group ("Bats" / "Throws"); optional. */
  readonly label = input<string>('');
  readonly value = input<string[]>([]);
  /** Offer the "S" (Switch) toggle — true for batting hand, false for throwing. */
  readonly switch = input(true);
  readonly valueChange = output<string[]>();

  protected readonly options = computed(() => {
    const opts = [
      { label: 'R', value: 'Right' },
      { label: 'L', value: 'Left' },
    ];
    if (this.switch()) opts.push({ label: 'S', value: 'Switch' });
    return opts;
  });
}
