import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from './api';
import { DraftClass } from './api.types';

@Injectable({ providedIn: 'root' })
export class ClassStore {
  private readonly api = inject(ApiService);
  readonly classes = signal<DraftClass[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async reload(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.classes.set(await this.api.draftClasses());
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }
}
