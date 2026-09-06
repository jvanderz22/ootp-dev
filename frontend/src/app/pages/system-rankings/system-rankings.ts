import {
  Component,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { DecimalPipe } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ApiService } from '../../core/api';
import { LeagueSnapshotStore } from '../../core/league-snapshot-store';
import { OrgProspectSummary, RankedPlayer } from '../../core/api.types';
import { PlayerDetailCardComponent } from '../class-view/player-detail-card';

/**
 * System Rankings: every org's farm system ranked against each other by the
 * potential model — the web equivalent of `print_org_summaries.py`. Each row
 * expands to that org's top prospects (capped at 25 server-side), and each
 * prospect can drill in to the full scouting / model breakdown.
 *
 * Snapshot freshness + refresh live on the shared `LeagueSnapshotStore`
 * (rendered by `league-shell`); this page reads `store.snapshot()` and reloads
 * when it changes under it.
 */
@Component({
  selector: 'app-system-rankings',
  imports: [RouterLink, DecimalPipe, PlayerDetailCardComponent],
  template: `
    @if (!store.refreshing()) {
      @if (!store.methodReady('potential') && loading()) {
        <p class="notice">
          Scoring the potential model for this snapshot — about a minute the first
          time.
        </p>
      }
      @if (error()) { <p class="error">{{ error() }}</p> }

      @if (loading() && !orgs().length) {
        <p class="muted">Loading system rankings…</p>
      } @else if (!orgs().length) {
        <p class="muted">
          No prospects to rank yet — pull a snapshot from StatsPlus.
        </p>
      } @else {
        <ol class="orgs">
          @for (o of orgs(); track o.orgId; let i = $index) {
            <li class="org" [class.open]="isOpen(o.orgId)">
              <button type="button" class="org-head" (click)="toggle(o.orgId)">
                <span class="chev">{{ isOpen(o.orgId) ? '▾' : '▸' }}</span>
                <span class="pos">#{{ i + 1 }}</span>
                <a
                  class="name"
                  [routerLink]="['/league', leagueId()]"
                  [queryParams]="{ org: o.orgId }"
                  (click)="$event.stopPropagation()"
                  >{{ o.orgName }}</a
                >
                <span class="score">score {{ o.orgScore | number: '1.1-1' }}</span>
                <span class="bar" aria-hidden="true">
                  <span class="fill" [style.width.%]="barWidth(o)"></span>
                </span>
                <span class="tiers">
                  {{ o.top10 }} top-10 · {{ o.top50 }} top-50 ·
                  {{ o.top100 }} top-100 · {{ o.top250 }} top-250
                  <span class="muted">({{ o.prospectCount }} tracked)</span>
                </span>
              </button>

              @if (isOpen(o.orgId)) {
                <ol class="prospects">
                  @for (p of o.topProspects; track p.id; let n = $index) {
                    <li class="prospect">
                      <span class="line">
                        <span class="n">{{ n + 1 }}.</span>
                        @if (p.statsPlusUrl) {
                          <a [href]="p.statsPlusUrl" target="_blank" rel="noopener">{{
                            p.name
                          }}</a>
                        } @else {
                          <span>{{ p.name }}</span>
                        }
                        <span class="meta">{{ p.position }}</span>
                        <span class="meta">#{{ p.rank }}</span>
                        @if (p.inGamePotential != null) {
                          <span class="meta"
                            >({{ p.modelScore | number: '1.1-1' }}, {{ p.inGamePotential }} Pot)</span
                          >
                        } @else {
                          <span class="meta">({{ p.modelScore | number: '1.1-1' }})</span>
                        }
                        @if (p.age != null) { <span class="meta">{{ p.age }}</span> }
                        @if (p.level) { <span class="meta">{{ p.level }}</span> }
                        <button
                          type="button"
                          class="detail-toggle"
                          (click)="toggleDetail(p.id)"
                        >
                          {{ showsDetail(p.id) ? 'hide detail' : 'show detail' }}
                        </button>
                      </span>
                      @if (showsDetail(p.id)) {
                        <app-player-detail-card [player]="p" [canEditRank]="false" />
                      }
                    </li>
                  }
                </ol>
              }
            </li>
          }
        </ol>
      }
    }
  `,
  styles: `
    .notice { color: var(--ok); }
    .orgs { list-style: none; margin: 12px 0 0; padding: 0; }
    .org { border-bottom: 1px solid var(--border); }
    .org-head {
      display: grid;
      grid-template-columns: 18px 34px minmax(160px, 1fr) auto 120px minmax(240px, 1.4fr);
      align-items: center;
      gap: 10px;
      width: 100%;
      background: none;
      border: none;
      padding: 10px 4px;
      text-align: left;
      font: inherit;
      cursor: pointer;
      color: inherit;
    }
    .org-head:hover:not(:disabled) { background: var(--bg-elev); }
    .chev { color: var(--text-dim); }
    .pos { color: var(--text-dim); font-variant-numeric: tabular-nums; }
    .name { font-weight: 600; color: var(--accent); text-decoration: none; }
    .name:hover { text-decoration: underline; }
    .score { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .bar {
      display: block;
      height: 8px;
      border-radius: 4px;
      background: var(--bg-elev-2);
      overflow: hidden;
    }
    .fill { display: block; height: 100%; background: var(--accent); }
    .tiers { color: var(--text-dim); font-size: 13px; }
    .prospects {
      list-style: none;
      margin: 0 0 10px;
      padding: 4px 0 4px 34px;
    }
    .prospect { padding: 3px 0; }
    .prospect .line {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 6px;
      font-variant-numeric: tabular-nums;
    }
    .prospect .n { color: var(--text-dim); }
    .prospect .meta { color: var(--text-dim); font-size: 13px; }
    .detail-toggle {
      background: none;
      border: none;
      padding: 0 4px;
      font: inherit;
      font-size: 13px;
      color: var(--accent);
      cursor: pointer;
    }
    app-player-detail-card { display: block; margin: 6px 0 10px; }
    @media (max-width: 720px) {
      .org-head { grid-template-columns: 18px 30px 1fr; }
      .org-head .score, .org-head .bar, .org-head .tiers { grid-column: 3; }
    }
  `,
})
export class SystemRankingsPage {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly store = inject(LeagueSnapshotStore);

  protected readonly leagueId = toSignal(
    (this.route.parent ?? this.route).paramMap.pipe(map((p) => p.get('id') ?? '')),
    {
      initialValue:
        (this.route.parent ?? this.route).snapshot.paramMap.get('id') ?? '',
    },
  );

  protected readonly orgs = signal<OrgProspectSummary[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  /** Expanded org ids and prospect ids showing the detail card — both round-trip
   *  through the URL so back / reload keeps position. */
  protected readonly expanded = signal<Set<string>>(new Set());
  protected readonly detail = signal<Set<string>>(new Set());

  private readonly topScore = computed(() => this.orgs()[0]?.orgScore ?? 0);

  private hydrated = false;
  private loadedFetchedAt: string | null | undefined = undefined;

  constructor() {
    effect(() => {
      const id = this.leagueId();
      if (id) untracked(() => void this.load(id));
    });
    effect(() => {
      const snap = this.store.snapshot();
      const refreshing = this.store.refreshing();
      if (refreshing) return;
      const id = untracked(() => this.leagueId());
      if (!id || untracked(() => this.loading())) return;
      if ((snap?.fetchedAt ?? null) === (this.loadedFetchedAt ?? null)) return;
      untracked(() => void this.load(id));
    });
  }

  protected isOpen(orgId: string): boolean {
    return this.expanded().has(orgId);
  }

  protected showsDetail(playerId: string): boolean {
    return this.detail().has(playerId);
  }

  protected barWidth(o: OrgProspectSummary): number {
    const top = this.topScore();
    return top > 0 ? Math.max(2, (o.orgScore / top) * 100) : 0;
  }

  protected toggle(orgId: string): void {
    this.expanded.update((s) => {
      const next = new Set(s);
      next.has(orgId) ? next.delete(orgId) : next.add(orgId);
      return next;
    });
    this.syncUrl();
  }

  protected toggleDetail(playerId: string): void {
    this.detail.update((s) => {
      const next = new Set(s);
      next.has(playerId) ? next.delete(playerId) : next.add(playerId);
      return next;
    });
    this.syncUrl();
  }

  private hydrateFromUrl(): void {
    const p = this.route.snapshot.queryParamMap;
    const parse = (v: string | null) =>
      new Set((v ?? '').split(',').filter(Boolean));
    this.expanded.set(parse(p.get('expanded')));
    this.detail.set(parse(p.get('detail')));
    this.hydrated = true;
  }

  private syncUrl(): void {
    const join = (s: Set<string>) => (s.size ? [...s].join(',') : null);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { expanded: join(this.expanded()), detail: join(this.detail()) },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  private async load(id: string): Promise<void> {
    if (!this.hydrated) this.hydrateFromUrl();
    this.loading.set(true);
    this.error.set(null);
    try {
      const rows = await this.api.leagueOrgRankings(id);
      this.orgs.set(rows);
      this.loadedFetchedAt = this.store.snapshot()?.fetchedAt ?? null;
      // the fetch may have lazily computed the potential model — refresh flags
      if (!this.store.methodReady('potential')) {
        void this.store.refreshSnapshotMeta();
      }
      // drop expanded/detail ids that are no longer present
      const orgIds = new Set(rows.map((o) => o.orgId));
      const playerIds = new Set(
        rows.flatMap((o) => o.topProspects.map((p: RankedPlayer) => p.id)),
      );
      this.expanded.update((s) => new Set([...s].filter((x) => orgIds.has(x))));
      this.detail.update((s) => new Set([...s].filter((x) => playerIds.has(x))));
    } catch (e) {
      this.error.set((e as Error).message);
      this.orgs.set([]);
    } finally {
      this.loading.set(false);
    }
  }
}
