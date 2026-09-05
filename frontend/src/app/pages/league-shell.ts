import { Component, computed, inject } from '@angular/core';
import { ActivatedRoute, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { LeagueStore } from '../core/league-store';

@Component({
  selector: 'app-league-shell',
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <div class="head">
      <a routerLink="/" class="back muted">← Leagues</a>
      <h1>{{ league()?.name ?? id() }}</h1>
    </div>

    <nav class="tabs">
      <a
        [routerLink]="['/league', id()]"
        routerLinkActive="active"
        [routerLinkActiveOptions]="{ exact: true }"
      >Current League</a>
      <a [routerLink]="['/league', id(), 'classes']" routerLinkActive="active"
        >Draft Classes</a
      >
    </nav>

    <router-outlet />
  `,
  styles: `
    a { text-decoration: none; color: inherit; }
    .head { display: flex; align-items: baseline; gap: 12px; }
    .back { font-size: 13px; }
    .tabs {
      display: flex;
      gap: 4px;
      margin: 12px 0 16px;
      border-bottom: 1px solid var(--border, #ddd);
    }
    .tabs a {
      padding: 8px 14px;
      border-bottom: 2px solid transparent;
      color: var(--muted, #666);
    }
    .tabs a.active {
      color: inherit;
      border-bottom-color: var(--accent);
      font-weight: 600;
    }
  `,
})
export class LeagueShellPage {
  private readonly route = inject(ActivatedRoute);
  private readonly store = inject(LeagueStore);

  protected readonly id = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('id') ?? '')),
    { initialValue: this.route.snapshot.paramMap.get('id') ?? '' },
  );

  protected readonly league = computed(() =>
    this.store.leagues().find((lg) => lg.id === this.id()),
  );
}
