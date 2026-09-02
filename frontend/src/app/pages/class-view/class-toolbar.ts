import { Component, ElementRef, computed, input, output, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MenuModule } from 'primeng/menu';
import { MenuItem } from 'primeng/api';
import { SelectModule } from 'primeng/select';

import { DraftClass, RANKING_METHODS } from '../../core/api.types';

/** Class heading + summary counts + the class-level action buttons. */
@Component({
  selector: 'app-class-toolbar',
  imports: [FormsModule, SelectModule, MenuModule],
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

          <button
            class="icon-btn"
            type="button"
            aria-label="Class settings"
            [disabled]="busy()"
            (click)="settingsMenu.toggle($event)"
          >
            <i class="pi pi-cog"></i>
          </button>
          <p-menu #settingsMenu [model]="settingsItems()" [popup]="true" appendTo="body" />
          <input
            #fileInput
            type="file"
            accept=".html,.htm,.csv"
            hidden
            (change)="onPick($any($event.target))"
          />
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
      .icon-btn { display: inline-flex; align-items: center; justify-content: center; }
      .icon-btn i { font-size: 1rem; }
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
  readonly replaceFile = output<File>();
  readonly refreshDrafted = output<void>();
  readonly download = output<void>();
  readonly startReorder = output<void>();
  readonly deleteClass = output<void>();

  protected readonly methodOptions = [...RANKING_METHODS];

  private readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');

  protected readonly settingsItems = computed<MenuItem[]>(() => [
    {
      label: 'Replace file…',
      icon: 'pi pi-upload',
      disabled: this.busy(),
      command: () => this.fileInput()?.nativeElement.click(),
    },
  ]);

  protected onPick(input: HTMLInputElement): void {
    const file = input.files?.[0];
    input.value = '';
    if (file) this.replaceFile.emit(file);
  }
}
