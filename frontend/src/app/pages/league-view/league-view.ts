import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { DatePipe } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ApiService } from '../../core/api';
import { LeagueSnapshot } from '../../core/api.types';

/**
 * Live league snapshot view. This is the milestone-4 shell: it shows the stored
 * snapshot's status and the manual "Refresh from StatsPlus" action. The grouped,
 * filterable player table (reusing the class-view ranked table) lands in
 * milestone 5.
 */
@Component({
  selector: 'app-league-view',
  imports: [DatePipe],
  template: `
    <div class="bar">
      <div>
        @if (snapshot(); as s) {
          <span>{{ s.playerCount }} players</span>
          @if (s.fetchedAt) {
            <span class="muted"> · refreshed {{ s.fetchedAt | date: 'medium' }}</span>
          }
        } @else if (!loading()) {
          <span class="muted">No snapshot yet — pull one from StatsPlus.</span>
        }
      </div>
      <button class="primary" [disabled]="busy()" (click)="refresh()">
        {{ busy() ? 'Refreshing…' : 'Refresh from StatsPlus' }}
      </button>
    </div>

    @if (error()) { <p class="error">{{ error() }}</p> }
    @if (busy()) {
      <p class="muted">
        Pulling the whole player pool and ranking it — this takes a minute or two.
      </p>
    }

    <p class="muted todo">Player table coming in the next step.</p>
  `,
  styles: `
    .bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .todo { margin-top: 24px; font-style: italic; }
  `,
})
export class LeagueViewPage {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ApiService);

  protected readonly leagueId = toSignal(
    (this.route.parent ?? this.route).paramMap.pipe(map((p) => p.get('id') ?? '')),
    { initialValue: (this.route.parent ?? this.route).snapshot.paramMap.get('id') ?? '' },
  );

  protected readonly snapshot = signal<LeagueSnapshot | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly ready = computed(() => !this.loading());

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    const id = this.leagueId();
    if (!id) return;
    this.loading.set(true);
    this.error.set(null);
    try {
      this.snapshot.set(await this.api.leagueSnapshot(id));
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }

  protected async refresh(): Promise<void> {
    const id = this.leagueId();
    if (!id || this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      this.snapshot.set(await this.api.refreshLeagueSnapshot(id));
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.busy.set(false);
    }
  }
}
