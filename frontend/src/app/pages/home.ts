import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';

import { ClassStore } from '../core/class-store';

@Component({
  selector: 'app-home',
  imports: [RouterLink, DatePipe],
  template: `
    <div class="head">
      <h1>Draft classes</h1>
      <a routerLink="/upload"><button class="primary">Upload a class</button></a>
    </div>

    @if (store.classes().length === 0 && !store.loading()) {
      <p class="muted">No classes yet. Upload an OOTP scouting export or a converted CSV to get started.</p>
    }

    <div class="grid">
      @for (c of store.classes(); track c.name) {
        <a class="card cls" [routerLink]="['/class', c.name]">
          <div class="name">{{ c.name }}</div>
          <div class="meta muted">
            {{ c.playerCount }} players · {{ c.rankingMethod }}
            @if (c.hasCustomOrder) { · <span class="tag">custom order</span> }
          </div>
          <div class="meta muted">
            @if (c.leagueName) { {{ c.leagueName }} } @else {
              <span class="tag">no league</span>
            }
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
export class HomePage {
  protected readonly store = inject(ClassStore);
}
