import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { ApiService } from '../core/api';
import { ClassStore } from '../core/class-store';
import { RANKING_METHODS } from '../core/api.types';

@Component({
  selector: 'app-upload',
  imports: [FormsModule],
  template: `
    <h1>Upload a draft class</h1>
    <form class="card" (submit)="submit($event)">
      <label>
        Class name
        <input name="name" [(ngModel)]="name" placeholder="yfmlb-2042-draft" required autocomplete="off" />
      </label>

      <label>
        Ranking method
        <select name="method" [(ngModel)]="method">
          @for (m of methods; track m) { <option [value]="m">{{ m }}</option> }
        </select>
      </label>

      <label>
        File (OOTP HTML scouting export or a converted CSV)
        <input
          type="file"
          accept=".html,.htm,.csv"
          (change)="onFile($any($event.target).files)"
          required
        />
      </label>

      @if (error()) { <p class="error">{{ error() }}</p> }
      <button class="primary" type="submit" [disabled]="busy() || !file() || !name.trim()">
        {{ busy() ? 'Processing… (trains models, ~10s)' : 'Upload & process' }}
      </button>
    </form>
  `,
  styles: `
    form { display: flex; flex-direction: column; gap: 14px; max-width: 480px; }
    label { display: flex; flex-direction: column; gap: 5px; }
  `,
})
export class UploadPage {
  private readonly api = inject(ApiService);
  private readonly store = inject(ClassStore);
  private readonly router = inject(Router);

  protected readonly methods = RANKING_METHODS;
  protected name = '';
  protected method = 'draft_class';
  protected readonly file = signal<File | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  onFile(files: FileList | null): void {
    this.file.set(files?.[0] ?? null);
    if (files?.[0] && !this.name.trim()) {
      this.name = files[0].name.replace(/\.(html?|csv)$/i, '');
    }
  }

  async submit(ev: Event): Promise<void> {
    ev.preventDefault();
    const f = this.file();
    if (!f) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const cls = await this.api.uploadDraftClass(this.name.trim(), this.method, f);
      await this.store.reload();
      await this.router.navigate(['/class', cls.name]);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.busy.set(false);
    }
  }
}
