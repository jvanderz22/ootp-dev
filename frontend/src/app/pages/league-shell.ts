import { Component, computed, effect, inject, untracked } from '@angular/core';
import {
  ActivatedRoute,
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { DatePipe } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map, startWith } from 'rxjs';

import { LeagueStore } from '../core/league-store';
import { LeagueSnapshotStore } from '../core/league-snapshot-store';

@Component({
  selector: 'app-league-shell',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, DatePipe],
  providers: [LeagueSnapshotStore],
  template: `
    <header class="shell-head">
      <h1>{{ league()?.name ?? id() }}</h1>
      <nav class="seg">
        <a
          [routerLink]="['/league', id()]"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: true }"
        >Current League</a>
        <a [routerLink]="['/league', id(), 'system']" routerLinkActive="active"
          >System</a
        >
        <a [routerLink]="['/league', id(), 'classes']" routerLinkActive="active"
          >Draft Classes</a
        >
      </nav>
    </header>

    @if (snapshotChrome()) {
    <div class="bar">
      @if (store.snapshot(); as s) {
        @if (s.fetchedAt) {
          <span class="muted" [title]="s.playerCount + ' players'"
            >Refreshed {{ s.fetchedAt | date: 'medium' }}</span
          >
        }
      } @else if (!store.refreshing()) {
        <span class="muted">No snapshot yet — pull one from StatsPlus.</span>
      }
      <button class="primary" [disabled]="store.refreshing()" (click)="store.refresh()">
        {{ store.refreshing() ? 'Refreshing…' : 'Refresh from StatsPlus' }}
      </button>
    </div>

    @if (store.notice()) { <p class="notice">{{ store.notice() }}</p> }

    @if (store.refreshing()) {
      <section class="refresh">
        <span class="spin" aria-hidden="true"></span>
        <div>
          <p class="phase">{{ store.phase() ?? 'Refreshing from StatsPlus…' }}</p>
          <p class="muted">
            Pulling the whole player pool and ranking it — a minute or two. This
            keeps running if you leave the page.
          </p>
        </div>
      </section>
    }

    @if (store.error()) { <p class="error">{{ store.error() }}</p> }
    }

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
    .bar {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
    }
    .notice { color: var(--ok); }
    .refresh {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      padding: 14px 16px;
      margin: 12px 0;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--bg-elev, #f6f6f6);
    }
    .refresh .phase { margin: 0 0 4px; font-weight: 600; }
    .refresh .muted { margin: 0; }
    .spin {
      flex: none;
      width: 16px;
      height: 16px;
      margin-top: 2px;
      border: 2px solid var(--border);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  `,
})
export class LeagueShellPage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly leagues = inject(LeagueStore);
  protected readonly store = inject(LeagueSnapshotStore);

  protected readonly id = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('id') ?? '')),
    { initialValue: this.route.snapshot.paramMap.get('id') ?? '' },
  );

  /** The snapshot bar / refresh panel belong to the two snapshot-backed tabs
   *  (Current League, System) — not Draft Classes. */
  private readonly onClassesTab = () =>
    this.router.url.split('?')[0].endsWith('/classes');
  protected readonly snapshotChrome = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      startWith(null),
      map(() => !this.onClassesTab()),
    ),
    { initialValue: !this.onClassesTab() },
  );

  protected readonly league = computed(() =>
    this.leagues.leagues().find((lg) => lg.id === this.id()),
  );

  constructor() {
    effect(() => {
      const id = this.id();
      if (id) untracked(() => void this.store.init(id));
    });
  }
}
