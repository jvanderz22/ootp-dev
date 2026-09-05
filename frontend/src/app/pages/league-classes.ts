import { Component, computed, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ClassStore } from '../core/class-store';

@Component({
  selector: 'app-league-classes',
  imports: [RouterLink, DatePipe],
  template: `
    <div class="head">
      <h2>Draft classes</h2>
      <a routerLink="/upload"><button class="primary">Upload a class</button></a>
    </div>

    @if (classes().length === 0) {
      <p class="muted">
        No draft classes in this league yet. Upload one and assign it to this
        league from the class menu or the Settings page.
      </p>
    }

    <div class="grid">
      @for (c of classes(); track c.name) {
        <a class="card cls" [routerLink]="['/class', c.name]">
          <div class="name">{{ c.name }}</div>
          <div class="meta muted">
            {{ c.playerCount }} players · {{ c.rankingMethod }}
            @if (c.hasCustomOrder) { · <span class="tag">custom order</span> }
          </div>
          <div class="meta muted">
            {{ c.draftedCount }} drafted ·
            @if (c.lastProcessed) {
              processed {{ c.lastProcessed | date: 'short' }}
            } @else {
              not processed
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
    .cls .name { font-weight: 600; margin-bottom: 6px; }
    .cls .meta { font-size: 12px; }
    .cls:hover { border-color: var(--accent); }
    .tag { color: var(--accent); }
  `,
})
export class LeagueClassesPage {
  private readonly route = inject(ActivatedRoute);
  private readonly store = inject(ClassStore);

  private readonly leagueId = toSignal(
    (this.route.parent ?? this.route).paramMap.pipe(map((p) => p.get('id') ?? '')),
    { initialValue: (this.route.parent ?? this.route).snapshot.paramMap.get('id') ?? '' },
  );

  protected readonly classes = computed(() =>
    this.store
      .classes()
      .filter((c) => c.leagueId === this.leagueId())
      .sort((a, b) => (b.lastProcessed ?? '').localeCompare(a.lastProcessed ?? '')),
  );
}
