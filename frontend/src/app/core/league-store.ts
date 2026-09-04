import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from './api';
import { League } from './api.types';

@Injectable({ providedIn: 'root' })
export class LeagueStore {
  private readonly api = inject(ApiService);
  readonly leagues = signal<League[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async reload(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.leagues.set(await this.api.leagues());
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }
}
