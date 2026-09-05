import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { LeagueStore } from '../core/league-store';

@Component({
  selector: 'app-leagues-home',
  imports: [RouterLink],
  template: `
    <div class="head">
      <h1>Leagues</h1>
      <a routerLink="/upload"><button class="primary">Upload a draft class</button></a>
    </div>

    @if (store.leagues().length === 0 && !store.loading()) {
      <p class="muted">
        No leagues yet. Add one on the
        <a routerLink="/settings">Settings</a> page.
      </p>
    }

    <div class="grid">
      @for (lg of store.leagues(); track lg.id) {
        <a class="card lg" [routerLink]="['/league', lg.id]">
          <div class="name">{{ lg.name }}</div>
          <div class="meta muted">
            {{ lg.classNames.length }}
            {{ lg.classNames.length === 1 ? 'draft class' : 'draft classes' }}
          </div>
          <div class="meta muted">
            @if (lg.leagueUrl) { {{ lg.leagueUrl }} } @else {
              <span class="tag">no StatsPlus URL</span>
            }
          </div>
        </a>
      }
    </div>
  `,
  styles: `
    .head { display: flex; align-items: center; justify-content: space-between; }
    a { text-decoration: none; color: inherit; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }
    .lg .name { font-weight: 600; margin-bottom: 6px; }
    .lg .meta { font-size: 12px; }
    .lg:hover { border-color: var(--accent); }
    .tag { color: var(--accent); }
  `,
})
export class LeaguesHomePage {
  protected readonly store = inject(LeagueStore);
}
