import { Component, computed, effect, inject } from '@angular/core';
import {
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map } from 'rxjs';

import { AuthService } from './core/auth';
import { ClassStore } from './core/class-store';
import { LeagueStore } from './core/league-store';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  protected readonly store = inject(ClassStore);
  private readonly leagueStore = inject(LeagueStore);

  protected readonly authorized = this.auth.authorized;

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
      map((e) => e.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly showChrome = computed(() => !this.url()?.startsWith('/login'));

  /** Up to four leagues for the top-bar shortcuts: most-recently-refreshed
   *  first, falling back to name order for leagues never refreshed. */
  protected readonly recentLeagues = computed(() =>
    [...this.leagueStore.leagues()]
      .sort((a, b) => {
        if (a.updatedAt && b.updatedAt) return b.updatedAt.localeCompare(a.updatedAt);
        if (a.updatedAt) return -1;
        if (b.updatedAt) return 1;
        return a.name.localeCompare(b.name);
      })
      .slice(0, 4),
  );

  constructor() {
    effect(() => {
      if (this.authorized()) {
        this.store.reload();
        this.leagueStore.reload();
      }
    });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
