import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SelectModule } from 'primeng/select';

import { DraftClass, RANKING_METHODS } from '../../core/api.types';

/** Class heading + summary counts + the class-level action buttons. */
@Component({
  selector: 'app-class-toolbar',
  imports: [FormsModule, SelectModule],
  template: `
    @let d = detail();
    @if (d) {
      <div class="head">
        <div>
          <h1>{{ d.name }}</h1>
          <p class="muted sub">
            {{ d.playerCount }} players ·
            {{ shownCount() }} shown ·
            {{ d.draftedCount }} drafted
            @if (d.hasCustomOrder) { · <span class="tag">custom order</span> }
          </p>
        </div>

        <div class="actions">
          <label class="row">
            <span class="muted">Method</span>
            <p-select
              [ngModel]="d.rankingMethod"
              (onChange)="methodChange.emit($event.value)"
              [options]="methodOptions"
              [disabled]="busy()"
              appendTo="body"
            />
          </label>
          <button (click)="reprocess.emit()" [disabled]="busy()">Reprocess</button>
          @if (!notProcessed()) {
            <button (click)="refreshDrafted.emit()" [disabled]="busy()">Refresh drafted</button>
            <button (click)="download.emit()" [disabled]="busy()">Download C+ CSV</button>
            @if (mode() === 'table') {
              <button class="primary" (click)="startReorder.emit()" [disabled]="busy()">
                Edit custom order
              </button>
            }
          }
          <button class="danger" (click)="deleteClass.emit()" [disabled]="busy()">Delete</button>
        </div>
      </div>
    }
  `,
  styles: [
    `
      :host { display: block; }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 16px;
        flex-wrap: wrap;
      }
      h1 { margin: 0 0 4px; }
      .sub { margin: 0; }
      .muted { color: var(--text-dim); }
      .tag { color: var(--accent); }
      .actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
      .row { display: flex; align-items: center; gap: 8px; }
    `,
  ],
})
export class ClassToolbarComponent {
  readonly detail = input.required<DraftClass | null>();
  readonly busy = input(false);
  readonly notProcessed = input(false);
  readonly mode = input<'table' | 'reorder'>('table');
  readonly shownCount = input(0);

  readonly methodChange = output<string>();
  readonly reprocess = output<void>();
  readonly refreshDrafted = output<void>();
  readonly download = output<void>();
  readonly startReorder = output<void>();
  readonly deleteClass = output<void>();

  protected readonly methodOptions = [...RANKING_METHODS];
}
