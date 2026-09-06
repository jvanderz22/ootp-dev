import { Component, computed, inject } from '@angular/core';
import { ActivatedRoute, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { LeagueStore } from '../core/league-store';

@Component({
  selector: 'app-league-shell',
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <header class="shell-head">
      <h1>{{ league()?.name ?? id() }}</h1>
      <nav class="seg">
        <a
          [routerLink]="['/league', id()]"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: true }"
        >Current League</a>
        <a [routerLink]="['/league', id(), 'classes']" routerLinkActive="active"
          >Draft Classes</a
        >
      </nav>
    </header>

    <router-outlet />
  `,
  styles: `
    a { text-decoration: none; color: inherit; }
    .shell-head {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 16px;
    }
    h1 { margin: 0; font-size: 20px; }
    .seg {
      display: inline-flex;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }
    .seg a {
      padding: 6px 14px;
      color: var(--text-dim);
      border-right: 1px solid var(--border);
    }
    .seg a:last-child { border-right: none; }
    .seg a:hover { background: var(--bg-elev); }
    .seg a.active {
      background: var(--accent);
      color: var(--accent-contrast);
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
