import { Component, ElementRef, computed, inject, input, output, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MenuModule } from 'primeng/menu';
import { MenuItem } from 'primeng/api';

import { DraftClass, League, RANKING_METHODS } from '../../core/api.types';
import { Viewport } from '../../core/viewport';

/** Class heading + summary counts + the class-level action buttons. On a phone
 *  the secondary actions (refresh drafted, download) fold into the ⚙ menu. */
@Component({
  selector: 'app-class-toolbar',
  imports: [MenuModule, RouterLink],
  template: `
    @let d = detail();
    @if (d) {
      <div class="head">
        <div class="title">
          <h1>{{ d.name }}</h1>
          <div class="meta">
            <span class="stat"><b>{{ d.playerCount }}</b> players</span>
            @if (shownCount() !== d.playerCount) {
              <span class="stat"><b>{{ shownCount() }}</b> shown</span>
            }
            <span class="stat"><b>{{ d.draftedCount }}</b> drafted</span>
            <span class="pill" title="Ranking method">{{ methodLabel(d.rankingMethod) }}</span>
            <span class="pill" [class.none]="!d.leagueName" title="League">
              {{ d.leagueName || 'No league' }}
            </span>
            @if (d.hasCustomOrder) {
              <span class="pill accent">Custom order</span>
            }
          </div>
        </div>

        <div class="actions">
          @if (!notProcessed() && !narrow()) {
            <button (click)="refreshDrafted.emit()" [disabled]="busy()">Refresh drafted</button>
            <button (click)="download.emit()" [disabled]="busy()">Download S+ CSV</button>
          }
          @if (!notProcessed()) {
            @if (mode() === 'table') {
              <button class="primary" (click)="startReorder.emit()" [disabled]="busy()">
                Edit custom order
              </button>
            }
          }

          @if (!notProcessed() && !narrow()) {
            <a class="compare-link" [routerLink]="['/class', d.name, 'compare']">Compare models</a>
          }
          <button
            class="icon-btn"
            type="button"
            aria-label="Class settings"
            title="Class settings"
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
      :host {
        display: block;
      }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 16px;
        flex-wrap: wrap;
      }
      h1 {
        margin: 0 0 8px;
        overflow-wrap: anywhere;
      }
      .meta {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px 12px;
        font-size: 13px;
        color: var(--text-dim);
      }
      .stat b {
        color: var(--text);
        font-variant-numeric: tabular-nums;
      }
      .pill {
        padding: 1px 8px;
        border: 1px solid var(--border);
        border-radius: 999px;
        font-size: 12px;
        background: var(--bg-elev);
        color: var(--text);
      }
      .pill.none {
        color: var(--text-dim);
        border-style: dashed;
        background: none;
      }
      .pill.accent {
        border-color: var(--accent);
        color: var(--accent);
      }
      .actions {
        display: flex;
        gap: 8px;
        align-items: center;
        flex-wrap: wrap;
      }
      .compare-link {
        padding: 6px 12px;
        border: 1px solid var(--border);
        border-radius: 6px;
        color: var(--text);
        text-decoration: none;
        white-space: nowrap;
      }
      .compare-link:hover {
        background: var(--bg-elev);
      }
      .icon-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .icon-btn i {
        font-size: 1rem;
      }
      /* phones: a smaller title, and the actions on one row under the meta */
      @media (max-width: 640px) {
        .head {
          gap: 12px;
        }
        h1 {
          font-size: 22px;
        }
        .actions {
          width: 100%;
        }
        .actions .primary {
          flex: 1 1 auto;
        }
        .icon-btn {
          width: 40px;
          height: 34px;
        }
      }
    `,
  ],
})
export class ClassToolbarComponent {
  readonly detail = input.required<DraftClass | null>();
  readonly busy = input(false);
  readonly notProcessed = input(false);
  readonly mode = input<'table' | 'reorder'>('table');
  readonly shownCount = input(0);
  readonly leagues = input<League[]>([]);

  readonly methodChange = output<string>();
  readonly reprocess = output<void>();
  readonly replaceFile = output<File>();
  readonly refreshDrafted = output<void>();
  readonly download = output<void>();
  readonly startReorder = output<void>();
  readonly deleteClass = output<void>();
  readonly setLeague = output<string | null>();

  private readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');
  protected readonly narrow = inject(Viewport).narrow;

  /** "draft_class" → "Draft class ranking". */
  protected methodLabel(method: string): string {
    const words = method.replace(/_/g, ' ');
    return `${words.charAt(0).toUpperCase()}${words.slice(1)} ranking`;
  }

  protected readonly settingsItems = computed<MenuItem[]>(() => {
    const d = this.detail();
    const busy = this.busy();
    const check = (on: boolean) => (on ? 'pi pi-check' : 'pi pi-fw');

    const methodItems: MenuItem[] = RANKING_METHODS.map((m) => ({
      label: m,
      icon: check(d?.rankingMethod === m),
      disabled: busy || d?.rankingMethod === m,
      command: () => this.methodChange.emit(m),
    }));

    const leagueItems: MenuItem[] = [
      {
        label: 'None',
        icon: check(!d?.leagueId),
        disabled: busy || !d?.leagueId,
        command: () => this.setLeague.emit(null),
      },
      ...this.leagues().map((l) => ({
        label: l.name,
        icon: check(d?.leagueId === l.id),
        disabled: busy || d?.leagueId === l.id,
        command: () => this.setLeague.emit(l.id),
      })),
    ];

    // phones: the toolbar's secondary buttons live here instead
    const classActions: MenuItem[] =
      this.narrow() && !this.notProcessed()
        ? [
            {
              label: 'Refresh drafted',
              icon: 'pi pi-sync',
              disabled: busy,
              command: () => this.refreshDrafted.emit(),
            },
            {
              label: 'Download S+ CSV',
              icon: 'pi pi-download',
              disabled: busy,
              command: () => this.download.emit(),
            },
            { separator: true },
          ]
        : [];

    return [
      ...classActions,
      { label: 'Ranking method', items: methodItems },
      { label: 'Move to league', items: leagueItems },
      { separator: true },
      {
        label: 'Reprocess',
        icon: 'pi pi-refresh',
        disabled: busy,
        command: () => this.reprocess.emit(),
      },
      {
        label: 'Replace file…',
        icon: 'pi pi-upload',
        disabled: busy,
        command: () => this.fileInput()?.nativeElement.click(),
      },
      { separator: true },
      {
        label: 'Delete',
        icon: 'pi pi-trash',
        styleClass: 'danger',
        disabled: busy,
        command: () => this.deleteClass.emit(),
      },
    ];
  });

  protected onPick(input: HTMLInputElement): void {
    const file = input.files?.[0];
    input.value = '';
    if (file) this.replaceFile.emit(file);
  }
}
