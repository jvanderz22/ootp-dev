import { Component, computed, effect, inject } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map } from 'rxjs';

import { AuthService } from './core/auth';
import { ClassStore } from './core/class-store';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  protected readonly store = inject(ClassStore);

  protected readonly authorized = this.auth.authorized;

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
      map((e) => e.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly currentClass = computed(() => {
    const m = /^\/class\/([^/?#]+)/.exec(this.url() ?? '');
    return m ? decodeURIComponent(m[1]) : '';
  });

  protected readonly showChrome = computed(() => !this.url()?.startsWith('/login'));

  constructor() {
    effect(() => {
      if (this.authorized()) this.store.reload();
    });
  }

  onPickClass(name: string): void {
    if (name) this.router.navigate(['/class', name]);
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
