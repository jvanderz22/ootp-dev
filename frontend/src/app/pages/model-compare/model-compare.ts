import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DecimalPipe } from '@angular/common';

import { ApiService } from '../../core/api';
import { ModelComparisonRow } from '../../core/api.types';

const PAGE_SIZE = 100;
const POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH', 'SP', 'RP', 'CL'];

interface Column {
  field: string;
  label: string;
  title?: string;
  /** first click sorts this way: 1 ascending (ranks, names), -1 descending */
  first: 1 | -1;
}

/**
 * Compare models: every player's overall score and rank under the legacy
 * engine and v2 side by side, with the difference in each. For a draft class
 * (`/class/:name/compare`) or a league snapshot (`/league/:id/compare`, with
 * the current / potential switch). Ranks are each engine's own model order.
 */
@Component({
  selector: 'app-model-compare',
  imports: [RouterLink, DecimalPipe],
  template: `
    <div class="head">
      <div>
        <h2>Compare models</h2>
        <p class="muted">
          Overall score and rank under each engine. The scores are in different units (legacy
          points, v2's 50 + 10 × WAR), so read the score diff as a rough guide and the rank diff
          as the real comparison. Rank Δ is legacy rank minus v2 rank: green means v2 ranks him
          higher.
        </p>
      </div>
      @if (className()) {
        <a class="back" [routerLink]="['/class', className()]">← Back to the class</a>
      }
    </div>

    <div class="controls">
      @if (leagueId()) {
        <div class="seg" role="group" aria-label="Ratings">
          <button type="button" [class.active]="method() === 'overall'" (click)="setMethod('overall')">
            Current
          </button>
          <button type="button" [class.active]="method() === 'potential'" (click)="setMethod('potential')">
            Potential
          </button>
        </div>
      }
      <input
        id="compare-search"
        type="search"
        placeholder="Search name or org"
        aria-label="Search name or org"
        [value]="search()"
        (input)="onSearch($any($event.target).value)"
      />
      <select id="compare-position" aria-label="Position" [value]="position()" (change)="setPosition($any($event.target).value)">
        <option value="">All positions</option>
        @for (p of positions; track p) { <option [value]="p">{{ p }}</option> }
      </select>
      @if (leagueId() && levels().length) {
        <select id="compare-level" aria-label="Level" [value]="level()" (change)="setLevel($any($event.target).value)">
          <option value="">All levels</option>
          @for (l of levels(); track l) { <option [value]="l">{{ l }}</option> }
        </select>
      }
      <span class="count">{{ total() | number }} players</span>
    </div>

    @if (error()) { <p class="error">{{ error() }}</p> }
    @if (loading() && !rows().length) {
      <p class="muted">
        Loading both rankings… a league's first comparison scores whichever engine hasn't run
        yet, which can take a minute or two.
      </p>
    }

    @if (rows().length) {
      <div class="table-wrap" [class.dim]="loading()">
        <table>
          <thead>
            <tr>
              @for (c of columns; track c.field) {
                <th
                  [class.num]="c.field !== 'name' && c.field !== 'position'"
                  [class.sorted]="sort().field === c.field"
                  [attr.aria-sort]="sort().field === c.field ? (sort().order > 0 ? 'ascending' : 'descending') : null"
                  [title]="c.title ?? ''"
                >
                  <button type="button" (click)="sortBy(c)">
                    {{ c.label }}
                    @if (sort().field === c.field) { <span>{{ sort().order > 0 ? '▲' : '▼' }}</span> }
                  </button>
                </th>
              }
              @if (leagueId()) { <th>Org</th><th>Level</th> }
            </tr>
          </thead>
          <tbody>
            @for (r of rows(); track r.id) {
              <tr>
                <td class="name">{{ r.name }}</td>
                <td>{{ r.position }}</td>
                <td class="num">{{ r.age }}</td>
                <td class="num">{{ r.legacyScore | number: '1.1-1' }}</td>
                <td class="num">{{ r.legacyRank }}</td>
                <td class="num">{{ r.v2Score | number: '1.1-1' }}</td>
                <td class="num">{{ r.v2Rank }}</td>
                <td class="num" [class.up]="(r.rankDiff ?? 0) > 0" [class.down]="(r.rankDiff ?? 0) < 0">
                  {{ signed(r.rankDiff) }}
                </td>
                <td class="num dimmed">{{ signedScore(r.scoreDiff) }}</td>
                @if (leagueId()) { <td>{{ r.org }}</td><td>{{ r.level }}</td> }
              </tr>
            }
          </tbody>
        </table>
      </div>

      <div class="pager">
        <button type="button" [disabled]="page() === 0 || loading()" (click)="go(page() - 1)">← Prev</button>
        <span class="muted">{{ firstShown() | number }}–{{ lastShown() | number }} of {{ total() | number }}</span>
        <button type="button" [disabled]="lastShown() >= total() || loading()" (click)="go(page() + 1)">Next →</button>
      </div>
    } @else if (!loading() && !error()) {
      <p class="muted">No players match.</p>
    }
  `,
  styles: `
    :host { display: block; }
    .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
    h2 { margin: 0 0 4px; font-size: 18px; }
    .head p { margin: 0; max-width: 70ch; font-size: 13px; }
    .back { color: var(--accent); text-decoration: none; white-space: nowrap; }
    .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 14px 0 10px; }
    .controls input, .controls select {
      font: inherit; color: var(--text); background: var(--bg); border: 1px solid var(--border);
      border-radius: 6px; padding: 5px 8px;
    }
    .controls input { width: 200px; max-width: 100%; }
    .count { color: var(--text-dim); font-variant-numeric: tabular-nums; }
    .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    .seg button {
      font: inherit; padding: 5px 12px; border: none; background: none; color: var(--text-dim); cursor: pointer;
      border-right: 1px solid var(--border);
    }
    .seg button:last-child { border-right: none; }
    .seg button.active { background: var(--accent); color: var(--accent-contrast); font-weight: 600; }
    .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
    .table-wrap.dim { opacity: 0.6; }
    table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
    th, td { padding: 6px 10px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
    th { position: sticky; top: 0; background: var(--bg-elev); font-size: 12px; color: var(--text-dim); }
    th button {
      font: inherit; color: inherit; background: none; border: none; padding: 0; cursor: pointer;
      text-transform: uppercase; letter-spacing: 0.03em;
    }
    th.sorted { color: var(--accent); }
    th.num, td.num { text-align: right; }
    th.num button { text-align: right; }
    td.name { font-weight: 600; }
    tbody tr:hover td { background: var(--bg-elev); }
    .up { color: var(--ok); font-weight: 600; }
    .down { color: var(--danger); font-weight: 600; }
    .dimmed { color: var(--text-dim); }
    .pager { display: flex; align-items: center; justify-content: center; gap: 12px; margin: 12px 0; }
    .pager button {
      font: inherit; padding: 5px 12px; border: 1px solid var(--border); border-radius: 6px;
      background: var(--bg); color: var(--text); cursor: pointer;
    }
    .pager button:disabled { opacity: 0.5; cursor: default; }
  `,
})
export class ModelComparePage {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);

  protected readonly positions = POSITIONS;
  protected readonly columns: Column[] = [
    { field: 'name', label: 'Player', first: 1 },
    { field: 'position', label: 'Pos', first: 1 },
    { field: 'age', label: 'Age', first: 1 },
    { field: 'legacyScore', label: 'Legacy score', first: -1 },
    { field: 'legacyRank', label: 'Legacy rank', first: 1 },
    { field: 'v2Score', label: 'v2 score', first: -1 },
    { field: 'v2Rank', label: 'v2 rank', first: 1 },
    { field: 'rankDiff', label: 'Rank Δ', title: 'Legacy rank minus v2 rank: positive = v2 ranks him higher', first: -1 },
    { field: 'scoreDiff', label: 'Score Δ', title: 'v2 score minus legacy score (different units)', first: -1 },
  ];

  /** `/league/:id/compare` (a child of the league shell) or `/class/:name/compare` */
  protected readonly leagueId = signal(this.route.parent?.snapshot.paramMap.get('id') ?? '');
  protected readonly className = signal(this.route.snapshot.paramMap.get('name') ?? '');

  protected readonly method = signal<'overall' | 'potential'>('overall');
  protected readonly search = signal('');
  protected readonly position = signal('');
  protected readonly level = signal('');
  protected readonly sort = signal<{ field: string; order: number }>({ field: 'v2Rank', order: 1 });
  protected readonly page = signal(0);

  protected readonly rows = signal<ModelComparisonRow[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly levels = signal<string[]>([]);

  protected readonly firstShown = computed(() => (this.total() ? this.page() * PAGE_SIZE + 1 : 0));
  protected readonly lastShown = computed(() => Math.min((this.page() + 1) * PAGE_SIZE, this.total()));

  private searchTimer: ReturnType<typeof setTimeout> | undefined;
  private request = 0;

  constructor() {
    if (this.leagueId()) {
      this.api.leagueLevels(this.leagueId()).then(
        (levels) => this.levels.set(levels),
        () => this.levels.set([]),
      );
    }
    effect(() => {
      const q = {
        className: this.className() || undefined,
        leagueId: this.leagueId() || undefined,
        method: this.leagueId() ? this.method() : undefined,
        search: this.search() || undefined,
        positions: this.position() ? [this.position()] : undefined,
        level: this.level() || undefined,
        sort: this.sort(),
        page: this.page(),
        pageSize: PAGE_SIZE,
      };
      untracked(() => this.load(q));
    });
  }

  private async load(q: Parameters<ApiService['modelComparison']>[0]): Promise<void> {
    const mine = ++this.request;
    this.loading.set(true);
    this.error.set(null);
    try {
      const page = await this.api.modelComparison(q);
      if (mine !== this.request) return;
      this.rows.set(page.rows);
      this.total.set(page.totalRecords);
    } catch (e) {
      if (mine !== this.request) return;
      this.error.set((e as Error).message);
    } finally {
      if (mine === this.request) this.loading.set(false);
    }
  }

  protected setMethod(m: 'overall' | 'potential'): void {
    this.method.set(m);
    this.page.set(0);
  }

  protected onSearch(value: string): void {
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.search.set(value.trim());
      this.page.set(0);
    }, 250);
  }

  protected setPosition(value: string): void {
    this.position.set(value);
    this.page.set(0);
  }

  protected setLevel(value: string): void {
    this.level.set(value);
    this.page.set(0);
  }

  protected sortBy(c: Column): void {
    const s = this.sort();
    this.sort.set(s.field === c.field ? { field: c.field, order: -s.order } : { field: c.field, order: c.first });
    this.page.set(0);
  }

  protected go(page: number): void {
    this.page.set(Math.max(0, page));
  }

  protected signed(v: number | null): string {
    if (v == null) return '—';
    return v > 0 ? `+${v}` : `${v}`;
  }

  protected signedScore(v: number | null): string {
    if (v == null) return '—';
    return (v > 0 ? '+' : '') + v.toFixed(1);
  }
}
