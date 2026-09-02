import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { HttpClient } from '@angular/common/http';

import { AuthService } from '../core/auth';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  template: `
    <div class="wrap">
      <form class="card" (submit)="submit($event)">
        <h2>Sign in</h2>
        <label>
          Username
          <input name="username" [(ngModel)]="username" autocomplete="username" />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            [(ngModel)]="password"
            autocomplete="current-password"
          />
        </label>
        @if (error()) { <p class="error">{{ error() }}</p> }
        <button class="primary" type="submit" [disabled]="busy()">
          {{ busy() ? 'Checking…' : 'Sign in' }}
        </button>
      </form>
    </div>
  `,
  styles: `
    .wrap { display: grid; place-items: center; min-height: 70vh; }
    form { display: flex; flex-direction: column; gap: 12px; width: 280px; }
    label { display: flex; flex-direction: column; gap: 4px; }
  `,
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly http = inject(HttpClient);

  protected username = 'admin';
  protected password = '';
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  async submit(ev: Event): Promise<void> {
    ev.preventDefault();
    this.busy.set(true);
    this.error.set(null);
    this.auth.login(this.username, this.password);
    try {
      await firstValueFrom(this.http.get('/healthz'));
      await this.router.navigate(['/']);
    } catch {
      this.auth.logout();
      this.error.set('Incorrect username or password.');
    } finally {
      this.busy.set(false);
    }
  }
}
