import { DestroyRef, Injectable, inject, signal } from '@angular/core';

import { ApiService } from './api';
import { LeagueRefreshStatus, LeagueSnapshot } from './api.types';

/**
 * Snapshot lifecycle for a `league/:id` route: the stored snapshot, an in-flight
 * StatsPlus refresh (with its progress line), and the once-a-day freshness gate.
 *
 * Provided on the `league/:id` shell (`providers: [LeagueSnapshotStore]`) so both
 * child routes — Current League and System — share one instance, and it is torn
 * down / recreated when the league changes. Lifted verbatim out of
 * `league-view.ts`, which now just reads `snapshot()` / `refreshing()` etc.
 */
@Injectable()
export class LeagueSnapshotStore {
  private readonly api = inject(ApiService);

  readonly snapshot = signal<LeagueSnapshot | null>(null);
  /** A full snapshot refresh (manual or the freshness auto-pull) is in flight. */
  readonly refreshing = signal(false);
  /** Live phase line for the in-flight refresh (the server's `progress` string). */
  readonly phase = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  private leagueId = '';
  private destroyed = false;
  /** guards against two poll loops running at once (manual refresh + re-attach) */
  private polling = false;

  constructor() {
    inject(DestroyRef).onDestroy(() => (this.destroyed = true));
  }

  /** True when `method`'s model is already scored for the current snapshot — or
   *  there is no snapshot yet, so there is nothing to warn about. */
  methodReady(method: string): boolean {
    const s = this.snapshot();
    return !s || s.rankedMethods.includes(method);
  }

  /** On entering a league: re-attach to a refresh kicked off before we got here,
   *  otherwise run the once-a-day freshness check (which may start one itself). */
  async init(leagueId: string): Promise<void> {
    this.leagueId = leagueId;
    this.error.set(null);
    this.notice.set(null);
    const inflight = await this.api.leagueRefreshStatus(leagueId).catch(() => null);
    if (inflight?.state === 'running') {
      await this.trackRefresh(leagueId, inflight);
    } else {
      await this.gateOnFreshness(leagueId);
    }
  }

  /** Manual "Refresh from StatsPlus". Flips into the progress state immediately,
   *  before the mutation round-trips; `trackRefresh` clears it when done. */
  async refresh(): Promise<void> {
    const id = this.leagueId;
    if (!id || this.refreshing()) return;
    this.refreshing.set(true);
    this.phase.set('Contacting StatsPlus…');
    this.error.set(null);
    this.notice.set(null);
    try {
      const started = await this.api.refreshLeagueSnapshot(id);
      await this.trackRefresh(id, started);
    } catch (e) {
      this.error.set((e as Error).message);
      this.phase.set(null);
      this.refreshing.set(false);
    }
  }

  /** Re-fetch just the snapshot meta — a child calls this after a player fetch
   *  that lazily computed a model, so the "ready" flags catch up. */
  async refreshSnapshotMeta(): Promise<void> {
    if (!this.leagueId) return;
    const s = await this.api.leagueSnapshot(this.leagueId).catch(() => null);
    if (s) this.snapshot.set(s);
  }

  private async gateOnFreshness(id: string): Promise<void> {
    try {
      const f = await this.api.checkLeagueSnapshotFreshness(id);
      this.snapshot.set(f.snapshot);
      if (f.stale && f.snapshot) {
        this.notice.set(
          `League advanced${f.leagueDate ? ` to ${f.leagueDate}` : ''} — pulling a fresh snapshot…`,
        );
        const started = await this.api.refreshLeagueSnapshot(id);
        const term = await this.trackRefresh(id, started);
        if (term.state === 'done') {
          this.notice.set(`Auto-refreshed to ${f.leagueDate ?? 'the current date'}.`);
        }
      }
    } catch {
      // freshness check failed — carry on with whatever is stored
    }
  }

  /** Follow a background refresh to completion: show the progress state, poll
   *  `leagueRefreshStatus` every few seconds, settle `snapshot` / `error` when
   *  it finishes. Safe from a fresh navigation (re-attach) or right after
   *  kicking one off. Returns the terminal status. */
  private async trackRefresh(
    id: string,
    status: LeagueRefreshStatus,
  ): Promise<LeagueRefreshStatus> {
    if (this.polling) return status;
    this.polling = true;
    if (status.state === 'running') {
      this.refreshing.set(true);
      this.phase.set(status.progress ?? 'Refreshing from StatsPlus…');
    }
    try {
      let failures = 0;
      while (status.state === 'running' && !this.destroyed) {
        await new Promise((r) => setTimeout(r, 2500));
        if (this.destroyed) return status;
        try {
          // Each poll is also what keeps the Fly machine awake during the job.
          status = await this.api.leagueRefreshStatus(id);
          failures = 0;
        } catch (e) {
          // A blip (the machine autostopping/restarting) shouldn't abort the
          // progress view — keep polling for a bit before giving up.
          if (++failures >= 6) throw e;
        }
        if (status.state === 'running') {
          this.phase.set(status.progress ?? this.phase());
        }
      }
      if (this.destroyed) return status;
      if (status.state === 'error') {
        this.error.set(status.error ?? 'Refresh from StatsPlus failed.');
        this.notice.set(null);
      } else if (status.state === 'done') {
        this.snapshot.set(status.snapshot);
        this.notice.set(null);
      }
      return status;
    } catch (e) {
      // The poll itself kept failing (machine down, network) — surface it
      // instead of leaving the page stuck behind a spinner, and hand the
      // (non-terminal) status back so the caller doesn't treat it as done.
      this.error.set((e as Error).message || 'Lost contact with the refresh job.');
      this.notice.set(null);
      return status;
    } finally {
      this.polling = false;
      this.phase.set(null);
      if (!this.destroyed) this.refreshing.set(false);
    }
  }
}
