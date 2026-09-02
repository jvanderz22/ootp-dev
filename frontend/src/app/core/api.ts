import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Apollo } from 'apollo-angular';
import { firstValueFrom } from 'rxjs';
import {
  CLASS_DETAIL,
  CLEAR_CUSTOM_ORDER,
  DELETE_DRAFT_CLASS,
  DRAFT_CLASSES,
  RANKED_PAGE,
  REFRESH_DRAFTED,
  REORDER_PLAYERS,
  REPROCESS_DRAFT_CLASS,
  SAVE_CUSTOM_ORDER,
  SET_RANKING_METHOD,
  STATSPLUS_SETTINGS,
  UPDATE_SETTINGS,
  UPLOAD_DRAFT_CLASS,
} from './gql';
import {
  DraftClass,
  DraftedRefreshResult,
  RankedPlayer,
  RankedPlayerPage,
  RankedQuery,
  StatsPlusSettings,
} from './api.types';

type ReorderPlayer = Pick<
  RankedPlayer,
  'id' | 'name' | 'position' | 'age' | 'modelScore' | 'drafted'
>;

/** Map the flat UI query onto the GraphQL `filter` / `sort` input objects. */
function queryVars(name: string, q: RankedQuery) {
  return {
    name,
    filter: {
      search: q.search.trim() || null,
      positions: q.positions.length ? q.positions : null,
      hideDrafted: q.hideDrafted,
    },
    sort: q.sortField ? { field: q.sortField, order: q.sortOrder } : null,
    page: q.page,
    pageSize: q.pageSize,
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

  async classDetail(
    name: string,
    q: RankedQuery,
  ): Promise<{
    draftClass: DraftClass | null;
    positions: string[];
    page: RankedPlayerPage;
  }> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{
          draftClass: DraftClass | null;
          classPositions: string[];
          rankedPlayers: RankedPlayerPage;
        }>({
          query: CLASS_DETAIL,
          variables: queryVars(name, q),
          fetchPolicy: 'network-only',
        }),
      );
      return {
        draftClass: res.data!.draftClass,
        positions: res.data!.classPositions,
        page: res.data!.rankedPlayers,
      };
    } catch (e) {
      unwrap(e);
    }
  }

  async rankedPlayersPage(name: string, q: RankedQuery): Promise<RankedPlayerPage> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ rankedPlayers: RankedPlayerPage }>({
          query: RANKED_PAGE,
          variables: queryVars(name, q),
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
    leagueUrl?: string;
    sessionid?: string;
    csrftoken?: string;
    defaultLid?: number | null;
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
