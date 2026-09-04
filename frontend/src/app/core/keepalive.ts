import { DestroyRef, Injectable, effect, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';

import { AuthService } from './auth';

/** How often to ping while the tab is visible. Comfortably inside Fly's idle
 *  auto-stop window so the machine stays warm through a working session. */
const PING_MS = 60_000;

/**
 * Keeps the backend machine from auto-stopping while someone is actively looking
 * at the app. The Fly deployment runs `min_machines_running = 0` with
 * `auto_stop_machines`, so an idle-but-open tab would let the box shut down and
 * eat a cold start on the next click.
 *
 * While the tab is visible *and* the user is logged in, this pings `/healthz`
 * every {@link PING_MS}, plus once immediately whenever the tab regains
 * visibility (the machine may have stopped while it was backgrounded). Hidden
 * tabs send nothing, so a parked tab won't keep a machine alive forever.
 */
@Injectable({ providedIn: 'root' })
export class KeepaliveService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private timer: ReturnType<typeof setInterval> | undefined;
  private readonly onVisibility = () => this.sync();

  constructor() {
    document.addEventListener('visibilitychange', this.onVisibility);
    // Start / stop with login state too.
    effect(() => {
      this.auth.authorized();
      this.sync();
    });
    inject(DestroyRef).onDestroy(() => {
      document.removeEventListener('visibilitychange', this.onVisibility);
      this.stop();
    });
  }

  /** Run the interval only while visible + authorized; otherwise idle. */
  private sync(): void {
    const active =
      this.auth.header() != null && document.visibilityState === 'visible';
    if (active && this.timer == null) {
      this.ping(); // the machine may have stopped while we were away
      this.timer = setInterval(() => this.ping(), PING_MS);
    } else if (!active && this.timer != null) {
      this.stop();
    }
  }

  private stop(): void {
    clearInterval(this.timer);
    this.timer = undefined;
  }

  private ping(): void {
    if (navigator.onLine === false) return;
    // Fire-and-forget: a dropped ping just means the next one retries, and a
    // 401 is already handled by the auth interceptor (logout + redirect).
    this.http.get('/healthz', { responseType: 'text' }).subscribe({
      error: () => {},
    });
  }
}
