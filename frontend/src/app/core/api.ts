import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Apollo } from 'apollo-angular';
import { firstValueFrom } from 'rxjs';
import {
  CLEAR_CUSTOM_ORDER,
  DELETE_DRAFT_CLASS,
  DRAFT_CLASSES,
  RANKED_PLAYERS,
  REFRESH_DRAFTED,
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
  StatsPlusSettings,
} from './api.types';

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
  ): Promise<{ draftClass: DraftClass | null; rankedPlayers: RankedPlayer[] }> {
    try {
      const res = await firstValueFrom(
        this.apollo.query<{ draftClass: DraftClass | null; rankedPlayers: RankedPlayer[] }>({
          query: RANKED_PLAYERS,
          variables: { name },
          fetchPolicy: 'network-only',
        }),
      );
      return res.data!;
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

  async saveCustomOrder(name: string, order: string[]): Promise<RankedPlayer[]> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ saveCustomOrder: RankedPlayer[] }>({
          mutation: SAVE_CUSTOM_ORDER,
          variables: { name, order },
        }),
      );
      return res.data!.saveCustomOrder;
    } catch (e) {
      unwrap(e);
    }
  }

  async clearCustomOrder(name: string): Promise<RankedPlayer[]> {
    try {
      const res = await firstValueFrom(
        this.apollo.mutate<{ clearCustomOrder: RankedPlayer[] }>({
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
