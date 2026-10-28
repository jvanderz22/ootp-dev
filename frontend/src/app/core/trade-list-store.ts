import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiService } from './api';
import { TradeList, TradePriority } from './api.types';

/**
 * Trade-target lists for one league. Provided on the `league/:id` shell
 * (`providers: [TradeListStore]`) alongside `LeagueSnapshotStore`, so every
 * child tab — Current League, the star affordance, the Trade Targets page —
 * shares one instance and it's torn down when the league changes.
 *
 * Holds only the list-level shape (`lists()`), not per-entry `note` / `priority`
 * detail; the Trade Targets page fetches that with `api.tradeListPlayers`. Every
 * mutation refreshes `lists()` from the mutation's own return value, so the
 * membership set (`listedIds()`) and the picker stay current with no refetch.
 */
@Injectable()
export class TradeListStore {
  private readonly api = inject(ApiService);

  readonly lists = signal<TradeList[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  /** Union of every entry's playerId across the league's lists — an O(1)
   *  "is this player on any list?" check for the ranked-table star. */
  readonly listedIds = computed(() => {
    const s = new Set<string>();
    for (const l of this.lists()) for (const id of l.entryIds) s.add(id);
    return s;
  });

  private leagueId = '';

  async init(leagueId: string): Promise<void> {
    if (leagueId === this.leagueId && this.lists().length) return;
    this.leagueId = leagueId;
    await this.reload();
  }

  async reload(): Promise<void> {
    if (!this.leagueId) return;
    this.loading.set(true);
    this.error.set(null);
    try {
      this.lists.set(await this.api.tradeLists(this.leagueId));
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }

  /** The lists a given player currently sits on. */
  listsWith(playerId: string): TradeList[] {
    return this.lists().filter((l) => l.entryIds.includes(playerId));
  }

  private replace(updated: TradeList): void {
    this.lists.update((ls) => {
      const i = ls.findIndex((l) => l.id === updated.id);
      if (i === -1) return [...ls, updated];
      const next = [...ls];
      next[i] = updated;
      return next;
    });
  }

  async create(name: string): Promise<TradeList> {
    const made = await this.api.createTradeList(this.leagueId, name);
    this.replace(made);
    return made;
  }

  async rename(listId: string, name: string): Promise<void> {
    this.replace(await this.api.renameTradeList(this.leagueId, listId, name));
  }

  async remove(listId: string): Promise<void> {
    await this.api.deleteTradeList(this.leagueId, listId);
    this.lists.update((ls) => ls.filter((l) => l.id !== listId));
  }

  async addPlayer(
    listId: string,
    playerId: string,
    priority?: TradePriority | null,
    note?: string | null,
  ): Promise<void> {
    this.replace(
      await this.api.addToTradeList(this.leagueId, listId, playerId, priority, note),
    );
  }

  async removePlayer(listId: string, playerId: string): Promise<void> {
    this.replace(await this.api.removeFromTradeList(this.leagueId, listId, playerId));
  }

  async setEntry(
    listId: string,
    playerId: string,
    patch: { priority?: TradePriority | null; note?: string | null },
  ): Promise<void> {
    this.replace(await this.api.setTradeListEntry(this.leagueId, listId, playerId, patch));
  }
}
