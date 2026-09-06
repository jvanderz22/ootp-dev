import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { DatePipe } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ApiService } from '../../core/api';
import {
  LeagueGroupBy,
  LeagueRefreshStatus,
  LeagueSnapshot,
  LeagueTeam,
  RANKED_PAGE_SIZE,
  RankedPlayer,
  RankedQuery,
} from '../../core/api.types';
import { DEFAULT_SORT, POSITION_ORDER } from '../../core/ranked-columns';
import { paramsToQuery, queryToParams } from '../../core/table-url';
import { RankedTableComponent } from '../class-view/ranked-table';

type Method = 'overall' | 'potential';

const METHODS: { label: string; value: Method }[] = [
  { label: 'Current', value: 'overall' },
  { label: 'Potential', value: 'potential' },
];

/** Top-level grouping. "By org" carries a second dropdown (Full org / one of the
 *  org's clubs); picking a club there fetches with `groupBy: TEAM` under the
 *  hood, so there is no separate "By team" button. */
const GROUPINGS: { label: string; value: 'LEAGUE' | 'ORG' }[] = [
  { label: 'Whole league', value: 'LEAGUE' },
  { label: 'By org', value: 'ORG' },
];

function defaultQuery(): RankedQuery {
  return {
    view: 'modeled',
    search: '',
    positions: [],
    bestPositions: [],
    batHands: [],
    throwHands: [],
    teams: [],
    levels: [],
    hideDrafted: false,
    numericFilters: [],
    sortField: DEFAULT_SORT.modeled.field,
    sortOrder: DEFAULT_SORT.modeled.order,
  };
}

/**
 * Live league snapshot view: the whole player pool pulled from StatsPlus, ranked
 * by the "current" or "potential" model, optionally narrowed to one org or one
 * roster team. Fetch/filter/sort/infinite-scroll mirror `class-view.ts`, against
 * `leagueSnapshotPlayers` instead of `rankedPlayers`, and it reuses the
 * class-view ranked table unchanged.
 */
@Component({
  selector: 'app-league-view',
  imports: [DatePipe, RankedTableComponent],
  template: `
    <div class="bar">
      @if (snapshot(); as s) {
        @if (s.fetchedAt) {
          <span class="muted" [title]="s.playerCount + ' players'"
            >Refreshed {{ s.fetchedAt | date: 'medium' }}</span
          >
        }
      } @else if (!loading() && !refreshing()) {
        <span class="muted">No snapshot yet — pull one from StatsPlus.</span>
      }
      <button class="primary" [disabled]="refreshing()" (click)="refresh()">
        {{ refreshing() ? 'Refreshing…' : 'Refresh from StatsPlus' }}
      </button>
    </div>

    @if (notice()) { <p class="notice">{{ notice() }}</p> }

    @if (refreshing()) {
      <section class="refresh">
        <span class="spin" aria-hidden="true"></span>
        <div>
          <p class="phase">{{ phase() ?? 'Refreshing from StatsPlus…' }}</p>
          <p class="muted">
            Pulling the whole player pool and ranking it — a minute or two. This
            keeps running if you leave the page.
          </p>
        </div>
      </section>
    }

    @if (methodNotReady() && !refreshing()) {
      <p class="notice">
        The {{ methodLabel() }} model hasn't been run for this snapshot yet — it'll
        compute the first time you open it (about a minute).
      </p>
    }
    @if (error()) { <p class="error">{{ error() }}</p> }

    @if (snapshot() && !refreshing()) {
      <div class="controls">
        <div class="seg">
          @for (m of methods; track m.value) {
            <button
              type="button"
              [class.active]="method() === m.value"
              [disabled]="loading()"
              (click)="setMethod(m.value)"
            >{{ m.label }}</button>
          }
        </div>

        <div class="seg">
          @for (g of groupings; track g.value) {
            <button
              type="button"
              [class.active]="groupBy() === g.value"
              [disabled]="loading()"
              (click)="setGroupBy(g.value)"
            >{{ g.label }}</button>
          }
        </div>

        @if (groupBy() === 'ORG') {
          <select [value]="orgId() ?? ''" [disabled]="loading()"
            (change)="setOrg($any($event.target).value)">
            <option value="">Pick an org…</option>
            @for (o of orgs(); track o.id) {
              <option [value]="o.id">{{ o.name }}</option>
            }
          </select>
        }
        @if (groupBy() === 'ORG' && orgId()) {
          <select [value]="teamId() ?? ''" [disabled]="loading()"
            (change)="setTeam($any($event.target).value)">
            <option value="">Full org</option>
            @for (t of orgTeams(); track t.id) {
              <option [value]="t.id">
                {{ t.name }}@if (t.level) { · {{ t.level }} }
              </option>
            }
          </select>
        }
      </div>

      @if (groupBy() === 'ORG' && !orgId()) {
        <p class="muted">Choose an org to see its players.</p>
      } @else {
        <app-ranked-table
          [rows]="rows()"
          [totalRecords]="totalRecords()"
          [positions]="positionOptions"
          [teams]="[]"
          [levels]="levels()"
          [context]="'league'"
          [loading]="loading()"
          [loadingMore]="loadingMore()"
          [hasMore]="hasMore()"
          [resetToken]="resetToken()"
          [classKey]="tableKey()"
          [initialQuery]="queryState()"
          (queryChange)="onQueryChange($event)"
          (loadMore)="onLoadMore()"
        />
      }
    }
  `,
  styles: `
    .bar {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      margin: 14px 0 10px;
    }
    .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    .seg button {
      background: none;
      border: none;
      border-right: 1px solid var(--border);
      padding: 6px 12px;
      cursor: pointer;
      font: inherit;
      color: var(--muted, #666);
    }
    .seg button:last-child { border-right: none; }
    .seg button.active { background: var(--accent); color: #fff; font-weight: 600; }
    .refresh {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      padding: 14px 16px;
      margin: 12px 0;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--bg-elev, #f6f6f6);
    }
    .refresh .phase { margin: 0 0 4px; font-weight: 600; }
    .refresh .muted { margin: 0; }
    .spin {
      flex: none;
      width: 16px;
      height: 16px;
      margin-top: 2px;
      border: 2px solid var(--border);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  `,
})
export class LeagueViewPage {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly methods = METHODS;
  protected readonly groupings = GROUPINGS;
  protected readonly positionOptions = POSITION_ORDER;

  protected readonly leagueId = toSignal(
    (this.route.parent ?? this.route).paramMap.pipe(map((p) => p.get('id') ?? '')),
    { initialValue: (this.route.parent ?? this.route).snapshot.paramMap.get('id') ?? '' },
  );

  protected readonly method = signal<Method>('potential');
  /** Top-level grouping the user picked: whole league, or by org. */
  protected readonly groupBy = signal<'LEAGUE' | 'ORG'>('ORG');
  protected readonly orgId = signal<string | null>(null);
  /** ORG mode only: a specific club within the org, or null for "Full org". */
  protected readonly teamId = signal<string | null>(null);

  /** What the API is actually asked for. Picking a club inside an org fetches
   *  with `groupBy: TEAM`; "Full org" stays `ORG`; whole-league is `LEAGUE`. */
  protected readonly apiGroupBy = computed<LeagueGroupBy>(() =>
    this.groupBy() === 'LEAGUE' ? 'LEAGUE' : this.teamId() ? 'TEAM' : 'ORG',
  );
  protected readonly apiGroupId = computed(() => {
    if (this.groupBy() === 'LEAGUE') return null;
    return this.teamId() ?? this.orgId();
  });
  /** Whether enough is selected to show a table (whole-league, or an org chosen). */
  protected readonly hasSelection = computed(
    () => this.groupBy() === 'LEAGUE' || !!this.orgId(),
  );

  protected readonly snapshot = signal<LeagueSnapshot | null>(null);
  protected readonly orgs = signal<LeagueTeam[]>([]);
  protected readonly teams = signal<LeagueTeam[]>([]);
  protected readonly levels = signal<string[]>([]);

  /** Teams under the selected org. Affiliates carry their parent club directly
   *  as `parentTeamId`, so no extra request is needed to scope the picker. */
  protected readonly orgTeams = computed(() => {
    const oid = this.orgId();
    if (!oid) return [];
    return this.teams().filter((t) => t.id === oid || t.parentTeamId === oid);
  });

  /** The chosen ranking's model hasn't been scored for this snapshot yet — the
   *  first open will compute it (a minute or so). */
  protected readonly methodNotReady = computed(() => {
    const s = this.snapshot();
    return !!s && !s.rankedMethods.includes(this.method());
  });
  protected readonly methodLabel = computed(
    () => METHODS.find((m) => m.value === this.method())?.label ?? '',
  );

  protected readonly rows = signal<RankedPlayer[]>([]);
  protected readonly totalRecords = signal(0);
  protected readonly loading = signal(false);
  protected readonly loadingMore = signal(false);
  /** A full snapshot refresh (manual or auto) is in flight. Distinct from
   *  `loading`, which is just a ranked-player fetch (seconds). While this is set
   *  the controls/table are hidden in favour of the progress panel. */
  protected readonly refreshing = signal(false);
  /** Live phase line for the in-flight refresh — the server's `progress` string
   *  ("Reading ratings…", "Scoring the potential model — 1,200 of 5,400…"). */
  protected readonly phase = signal<string | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);

  protected readonly queryState = signal<RankedQuery>(defaultQuery());
  protected readonly resetToken = signal(0);

  protected readonly hasMore = computed(() => this.rows().length < this.totalRecords());
  protected readonly tableKey = computed(
    () =>
      `${this.leagueId()}:${this.method()}:${this.apiGroupBy()}:${this.apiGroupId() ?? ''}`,
  );

  private hydrated = false;
  private destroyed = false;
  /** guards against two poll loops running at once (manual refresh + re-attach) */
  private polling = false;

  constructor() {
    this.destroyRef.onDestroy(() => (this.destroyed = true));
    effect(() => {
      const id = this.leagueId();
      if (id) untracked(() => void this.load(id));
    });
  }

  /** Follow a background refresh to completion: show the progress state, poll
   *  `leagueRefreshStatus` every few seconds, and settle `snapshot` / `error`
   *  when it finishes. Safe to call from a fresh navigation (re-attach) or right
   *  after kicking one off. Returns the terminal status. */
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
    } finally {
      this.polling = false;
      this.phase.set(null);
      if (!this.destroyed) this.refreshing.set(false);
    }
  }

  private hydrateFromUrl(): void {
    const p = this.route.snapshot.queryParamMap;
    this.method.set(p.get('method') === 'overall' ? 'overall' : 'potential');
    this.groupBy.set(p.get('group') === 'LEAGUE' ? 'LEAGUE' : 'ORG');
    this.orgId.set(p.get('org') || null);
    this.teamId.set(p.get('team') || null);
    this.queryState.set(paramsToQuery(p));
    this.hydrated = true;
  }

  private syncUrl(replace = true): void {
    const params: Record<string, string | null> = {
      ...queryToParams(this.queryState()),
      method: this.method() === 'potential' ? null : 'overall',
      group: this.groupBy() === 'ORG' ? null : this.groupBy(),
      org: this.groupBy() === 'ORG' ? this.orgId() || null : null,
      team: this.groupBy() === 'ORG' ? this.teamId() || null : null,
    };
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: params,
      replaceUrl: replace,
    });
  }

  /** Freshness gate: if the stored snapshot is over a day old and the sim has
   *  advanced past its date, pull a fresh one before showing the page. */
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

  /** Full load for a league (route change or after a refresh): snapshot meta,
   *  org/team facets, and the first batch for the current method/grouping. */
  private async load(id: string): Promise<void> {
    if (!this.hydrated) this.hydrateFromUrl();
    this.loading.set(true);
    this.error.set(null);
    this.notice.set(null);

    // Re-attach to a refresh kicked off before we navigated here; otherwise do
    // the once-a-day freshness check (which may start one of its own).
    const inflight = await this.api.leagueRefreshStatus(id).catch(() => null);
    if (inflight?.state === 'running') {
      await this.trackRefresh(id, inflight);
    } else {
      await this.gateOnFreshness(id);
    }
    try {
      const d = await this.api.leagueViewDetail(
        id,
        this.method(),
        this.apiGroupBy(),
        this.apiGroupId(),
        this.queryState(),
      );
      this.snapshot.set(d.snapshot);
      this.orgs.set([...d.orgs].sort((a, b) => a.name.localeCompare(b.name)));
      // teams arrive already ordered by level (MLB → AAA → …) — keep that order.
      this.teams.set(d.teams);
      this.levels.set(d.levels);
      this.rows.set(d.page.rows);
      this.totalRecords.set(d.page.totalRecords);
      this.resetToken.update((v) => v + 1);
    } catch (e) {
      this.error.set((e as Error).message);
      this.rows.set([]);
      this.totalRecords.set(0);
    } finally {
      this.loading.set(false);
    }
  }

  private async resetAndFetch(): Promise<void> {
    if (!this.snapshot()) return;
    this.loading.set(true);
    this.error.set(null);
    try {
      const wasNotReady = this.methodNotReady();
      const batch = await this.api.leagueSnapshotPlayersPage(
        this.leagueId(),
        this.method(),
        this.apiGroupBy(),
        this.apiGroupId(),
        this.queryState(),
        0,
      );
      this.rows.set(batch.rows);
      this.totalRecords.set(batch.totalRecords);
      this.resetToken.update((v) => v + 1);
      if (wasNotReady) {
        // that fetch just computed the model — refresh the "ready" flags
        const s = await this.api.leagueSnapshot(this.leagueId()).catch(() => null);
        if (s) this.snapshot.set(s);
      }
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }

  protected async onLoadMore(): Promise<void> {
    if (this.loading() || this.loadingMore() || !this.hasMore()) return;
    this.loadingMore.set(true);
    this.error.set(null);
    try {
      const nextPage = Math.floor(this.rows().length / RANKED_PAGE_SIZE);
      const batch = await this.api.leagueSnapshotPlayersPage(
        this.leagueId(),
        this.method(),
        this.apiGroupBy(),
        this.apiGroupId(),
        this.queryState(),
        nextPage,
      );
      this.rows.update((rs) => [...rs, ...batch.rows]);
      this.totalRecords.set(batch.totalRecords);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loadingMore.set(false);
    }
  }

  protected async onQueryChange(q: RankedQuery): Promise<void> {
    this.queryState.set(q);
    this.syncUrl();
    await this.resetAndFetch();
  }

  protected async setMethod(m: Method): Promise<void> {
    if (m === this.method()) return;
    this.method.set(m);
    this.syncUrl();
    await this.resetAndFetch();
  }

  private clearRows(): void {
    this.rows.set([]);
    this.totalRecords.set(0);
  }

  protected async setGroupBy(g: 'LEAGUE' | 'ORG'): Promise<void> {
    if (g === this.groupBy()) return;
    this.groupBy.set(g);
    this.syncUrl();
    // LEAGUE needs no pick; ORG waits for an org before refetching
    if (this.hasSelection()) await this.resetAndFetch();
    else this.clearRows();
  }

  protected async setOrg(id: string): Promise<void> {
    this.orgId.set(id || null);
    this.teamId.set(null); // the org's club list just changed — back to "Full org"
    this.syncUrl();
    if (this.hasSelection()) await this.resetAndFetch();
    else this.clearRows();
  }

  protected async setTeam(id: string): Promise<void> {
    this.teamId.set(id || null);
    this.syncUrl();
    if (this.hasSelection()) await this.resetAndFetch();
    else this.clearRows();
  }

  protected async refresh(): Promise<void> {
    const id = this.leagueId();
    if (!id || this.refreshing()) return;
    // Flip the UI into the progress state immediately, before the mutation
    // round-trips — `trackRefresh` then keeps it set and clears it when done.
    this.refreshing.set(true);
    this.phase.set('Contacting StatsPlus…');
    this.error.set(null);
    this.notice.set(null);
    try {
      const started = await this.api.refreshLeagueSnapshot(id);
      const term = await this.trackRefresh(id, started);
      if (term.state === 'done') await this.load(id);
    } catch (e) {
      this.error.set((e as Error).message);
      this.phase.set(null);
      this.refreshing.set(false);
    }
  }
}
