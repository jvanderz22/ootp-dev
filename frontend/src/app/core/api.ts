import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Apollo } from 'apollo-angular';
import { firstValueFrom } from 'rxjs';
import {
  CLASS_DETAIL,
  CLEAR_CUSTOM_ORDER,
  CREATE_LEAGUE,
  DELETE_DRAFT_CLASS,
  DELETE_LEAGUE,
  CHECK_LEAGUE_SNAPSHOT_FRESHNESS,
  DRAFT_CLASSES,
  LEAGUE_REFRESH_STATUS,
  LEAGUE_SNAPSHOT,
  LEAGUE_SNAPSHOT_PLAYERS,
  LEAGUE_VIEW_DETAIL,
  LEAGUES,
  RANKED_PAGE,
  REFRESH_DRAFTED,
  REFRESH_LEAGUE_SNAPSHOT,
  REORDER_PLAYERS,
  REPROCESS_DRAFT_CLASS,
  SAVE_CUSTOM_ORDER,
  SET_CLASS_LEAGUE,
  SET_PLAYER_RANK,
  SET_RANKING_METHOD,
  STATSPLUS_SETTINGS,
  UPDATE_LEAGUE,
  UPDATE_SETTINGS,
  UPLOAD_DRAFT_CLASS,
} from './gql';
import {
  DraftClass,
  DraftedRefreshResult,
  League,
  LeagueFreshness,
  LeagueGroupBy,
  LeagueRefreshStatus,
  LeagueSnapshot,
  LeagueTeam,
  RANKED_PAGE_SIZE,
  RankedPlayer,
  RankedPlayerPage,
  RankedQuery,
  StatsPlusSettings,
} from './api.types';

type ReorderPlayer = Pick<
  RankedPlayer,
  'id' | 'name' | 'position' | 'age' | 'modelScore' | 'drafted'
>;

/** Map the flat UI query onto the GraphQL `filter` / `sort` input objects,
 *  plus the batch window (`page` / `pageSize`) the caller wants fetched. */
function queryVars(name: string, q: RankedQuery, page: number, pageSize: number) {
  const numeric = q.numericFilters
    .filter((f) => f.field && (f.min != null || f.max != null))
    .map((f) => ({ field: f.field, min: f.min, max: f.max }));
  return {
    name,
    filter: {
      search: q.search.trim() || null,
      positions: q.positions.length ? q.positions : null,
      batHands: q.batHands.length ? q.batHands : null,
      throwHands: q.throwHands.length ? q.throwHands : null,
      teams: q.teams.length ? q.teams : null,
      hideDrafted: q.hideDrafted,
      numeric: numeric.length ? numeric : null,
    },
    sort: q.sortField ? { field: q.sortField, order: q.sortOrder } : null,
    page,
    pageSize,
  };
}

/** Same as `queryVars` but for the league snapshot: keyed by `leagueId` +
 *  `method` + the org/team grouping rather than a class `name`. */
function leagueQueryVars(
  leagueId: string,
  method: string,
  groupBy: LeagueGroupBy,
  groupId: string | null,
  q: RankedQuery,
  page: number,
  pageSize: number,
) {
  const vars = queryVars('', q, page, pageSize);
  return {
    leagueId,
    method,
    groupBy,
    groupId: groupId || null,
    filter: vars.filter,
    sort: vars.sort,
    page: vars.page,
    pageSize: vars.pageSize,
  };
}

function unwrap(err: unknown): never {
  const e = err as { graphQLErrors?: { message: string }[]; message?: string };
  throw new Error(e?.graphQLErrors?.[0]?.message ?? e?.message ?? 'Request failed');
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly apollo = inject(Apollo);
  private readonly http = inject(HttpClient);

  async draftClasses(): Promise<DraftClass[]> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ draftClasses: DraftClass[] }>({
          query: DRAFT_CLASSES,
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.draftClasses;
    } catch (e) {
      unwrap(e);
    }
  }

  /** Initial load for a class: metadata + facets + the first batch of rows. */
  async classDetail(
    name: string,
    q: RankedQuery,
    pageSize: number = RANKED_PAGE_SIZE,
  ): Promise<{
    draftClass: DraftClass | null;
    positions: string[];
    teams: string[];
    page: RankedPlayerPage;
  }> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{
          draftClass: DraftClass | null;
          classPositions: string[];
          draftTeams: string[];
          rankedPlayers: RankedPlayerPage;
        }>({
          query: CLASS_DETAIL,
          variables: queryVars(name, q, 0, pageSize),
          fetchPolicy: 'network-only',
        }),
      );
      return {
        draftClass: res.data!.draftClass,
        positions: res.data!.classPositions,
        teams: res.data!.draftTeams,
        page: res.data!.rankedPlayers,
      };
    } catch (e) {
      unwrap(e);
    }
  }

  /** One batch of rows for `page` (0-based, `pageSize` rows each) — the
   *  initial batch on a filter/sort reset, or the next one an infinite-scroll
   *  load-more asks for. */
  async rankedPlayersPage(
    name: string,
    q: RankedQuery,
    page: number,
    pageSize: number = RANKED_PAGE_SIZE,
  ): Promise<RankedPlayerPage> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ rankedPlayers: RankedPlayerPage }>({
          query: RANKED_PAGE,
          variables: queryVars(name, q, page, pageSize),
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.rankedPlayers;
    } catch (e) {
      unwrap(e);
    }
  }

  async reorderPlayers(name: string): Promise<ReorderPlayer[]> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ rankedPlayers: { rows: ReorderPlayer[] } }>({
          query: REORDER_PLAYERS,
          variables: { name },
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.rankedPlayers.rows;
    } catch (e) {
      unwrap(e);
    }
  }

  async uploadDraftClass(
    name: string,
    rankingMethod: string,
    file: File,
  ): Promise<DraftClass> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ uploadDraftClass: DraftClass }>({
          mutation: UPLOAD_DRAFT_CLASS,
          variables: { name, rankingMethod, file },
          context: { useMultipart: true },
        }),
      );
      return res.data!.uploadDraftClass;
    } catch (e) {
      unwrap(e);
    }
  }

  async setRankingMethod(name: string, rankingMethod: string): Promise<DraftClass> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ setRankingMethod: DraftClass }>({
          mutation: SET_RANKING_METHOD,
          variables: { name, rankingMethod },
        }),
      );
      return res.data!.setRankingMethod;
    } catch (e) {
      unwrap(e);
    }
  }

  async reprocess(name: string): Promise<DraftClass> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ reprocessDraftClass: DraftClass }>({
          mutation: REPROCESS_DRAFT_CLASS,
          variables: { name },
        }),
      );
      return res.data!.reprocessDraftClass;
    } catch (e) {
      unwrap(e);
    }
  }

  async deleteClass(name: string): Promise<void> {
    try {
      await firstValueFrom(
        this.apollo.mutate({ mutation: DELETE_DRAFT_CLASS, variables: { name } }),
      );
    } catch (e) {
      unwrap(e);
    }
  }

  async saveCustomOrder(name: string, order: string[]): Promise<DraftClass> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ saveCustomOrder: DraftClass }>({
          mutation: SAVE_CUSTOM_ORDER,
          variables: { name, order },
        }),
      );
      return res.data!.saveCustomOrder;
    } catch (e) {
      unwrap(e);
    }
  }

  async setPlayerRank(name: string, id: string, rank: number): Promise<DraftClass> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ setPlayerRank: DraftClass }>({
          mutation: SET_PLAYER_RANK,
          variables: { name, id, rank },
        }),
      );
      return res.data!.setPlayerRank;
    } catch (e) {
      unwrap(e);
    }
  }

  async clearCustomOrder(name: string): Promise<DraftClass> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ clearCustomOrder: DraftClass }>({
          mutation: CLEAR_CUSTOM_ORDER,
          variables: { name },
        }),
      );
      return res.data!.clearCustomOrder;
    } catch (e) {
      unwrap(e);
    }
  }

  async refreshDrafted(name: string): Promise<DraftedRefreshResult> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ refreshDraftedFromStatsPlus: DraftedRefreshResult }>({
          mutation: REFRESH_DRAFTED,
          variables: { name },
        }),
      );
      return res.data!.refreshDraftedFromStatsPlus;
    } catch (e) {
      unwrap(e);
    }
  }

  // --- live league snapshot ------------------------------------------------
  async leagueSnapshot(leagueId: string): Promise<LeagueSnapshot | null> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ leagueSnapshot: LeagueSnapshot | null }>({
          query: LEAGUE_SNAPSHOT,
          variables: { leagueId },
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.leagueSnapshot;
    } catch (e) {
      unwrap(e);
    }
  }

  /** Initial league-view load: snapshot meta + org/team facets + first batch. */
  async leagueViewDetail(
    leagueId: string,
    method: string,
    groupBy: LeagueGroupBy,
    groupId: string | null,
    q: RankedQuery,
    pageSize: number = RANKED_PAGE_SIZE,
  ): Promise<{
    snapshot: LeagueSnapshot | null;
    orgs: LeagueTeam[];
    teams: LeagueTeam[];
    page: RankedPlayerPage;
  }> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{
          leagueSnapshot: LeagueSnapshot | null;
          leagueOrgs: LeagueTeam[];
          leagueTeams: LeagueTeam[];
          leagueSnapshotPlayers: RankedPlayerPage;
        }>({
          query: LEAGUE_VIEW_DETAIL,
          variables: leagueQueryVars(leagueId, method, groupBy, groupId, q, 0, pageSize),
          fetchPolicy: 'network-only',
        }),
      );
      return {
        snapshot: res.data!.leagueSnapshot,
        orgs: res.data!.leagueOrgs,
        teams: res.data!.leagueTeams,
        page: res.data!.leagueSnapshotPlayers,
      };
    } catch (e) {
      unwrap(e);
    }
  }

  /** One infinite-scroll batch for the league view. */
  async leagueSnapshotPlayersPage(
    leagueId: string,
    method: string,
    groupBy: LeagueGroupBy,
    groupId: string | null,
    q: RankedQuery,
    page: number,
    pageSize: number = RANKED_PAGE_SIZE,
  ): Promise<RankedPlayerPage> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ leagueSnapshotPlayers: RankedPlayerPage }>({
          query: LEAGUE_SNAPSHOT_PLAYERS,
          variables: leagueQueryVars(leagueId, method, groupBy, groupId, q, page, pageSize),
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.leagueSnapshotPlayers;
    } catch (e) {
      unwrap(e);
    }
  }

  /** Kick off a background snapshot refresh. Returns immediately with
   *  `state: 'running'`; poll `leagueRefreshStatus` for progress. */
  async refreshLeagueSnapshot(leagueId: string): Promise<LeagueRefreshStatus> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ refreshLeagueSnapshot: LeagueRefreshStatus }>({
          mutation: REFRESH_LEAGUE_SNAPSHOT,
          variables: { leagueId },
        }),
      );
      return res.data!.refreshLeagueSnapshot;
    } catch (e) {
      unwrap(e);
    }
  }

  /** Current status of the in-flight (or last) background refresh for a league.
   *  Used to re-attach the progress indicator after navigating back to the page. */
  async leagueRefreshStatus(leagueId: string): Promise<LeagueRefreshStatus> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ leagueRefreshStatus: LeagueRefreshStatus }>({
          query: LEAGUE_REFRESH_STATUS,
          variables: { leagueId },
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.leagueRefreshStatus;
    } catch (e) {
      unwrap(e);
    }
  }

  /** On league-page load: is the stored snapshot still current? Only hits
   *  StatsPlus (for the in-game date) when the snapshot is over a day old. */
  async checkLeagueSnapshotFreshness(leagueId: string): Promise<LeagueFreshness> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ checkLeagueSnapshotFreshness: LeagueFreshness }>({
          mutation: CHECK_LEAGUE_SNAPSHOT_FRESHNESS,
          variables: { leagueId },
        }),
      );
      return res.data!.checkLeagueSnapshotFreshness;
    } catch (e) {
      unwrap(e);
    }
  }

  async settings(): Promise<StatsPlusSettings> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ statsPlusSettings: StatsPlusSettings }>({
          query: STATSPLUS_SETTINGS,
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.statsPlusSettings;
    } catch (e) {
      unwrap(e);
    }
  }

  async updateSettings(input: {
    sessionid?: string;
    csrftoken?: string;
  }): Promise<StatsPlusSettings> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ updateStatsPlusSettings: StatsPlusSettings }>({
          mutation: UPDATE_SETTINGS,
          variables: input,
        }),
      );
      return res.data!.updateStatsPlusSettings;
    } catch (e) {
      unwrap(e);
    }
  }

  async leagues(): Promise<League[]> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ leagues: League[] }>({
          query: LEAGUES,
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!.leagues;
    } catch (e) {
      unwrap(e);
    }
  }

  async createLeague(input: {
    name: string;
    leagueUrl?: string | null;
    defaultLid?: number | null;
    classNames?: string[];
  }): Promise<League> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ createLeague: League }>({
          mutation: CREATE_LEAGUE,
          variables: input,
        }),
      );
      return res.data!.createLeague;
    } catch (e) {
      unwrap(e);
    }
  }

  async updateLeague(input: {
    id: string;
    name?: string;
    leagueUrl?: string | null;
    defaultLid?: number | null;
    classNames?: string[];
  }): Promise<League> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ updateLeague: League }>({
          mutation: UPDATE_LEAGUE,
          variables: input,
        }),
      );
      return res.data!.updateLeague;
    } catch (e) {
      unwrap(e);
    }
  }

  async deleteLeague(id: string): Promise<void> {
    try {
      await firstValueFrom(
        this.apollo.mutate({ mutation: DELETE_LEAGUE, variables: { id } }),
      );
    } catch (e) {
      unwrap(e);
    }
  }

  async setClassLeague(name: string, leagueId: string | null): Promise<DraftClass> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ setClassLeague: DraftClass }>({
          mutation: SET_CLASS_LEAGUE,
          variables: { name, leagueId },
        }),
      );
      return res.data!.setClassLeague;
    } catch (e) {
      unwrap(e);
    }
  }

  async downloadUploadCsv(name: string): Promise<void> {
    const blob = await firstValueFrom(
      this.http.get(`/download/${encodeURIComponent(name)}/upload.csv`, {
        responseType: 'blob',
      }),
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}-c-plus.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
