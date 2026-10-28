import { Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { DecimalPipe, NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TagModule } from 'primeng/tag';
import { PanelModule } from 'primeng/panel';

import { ApiService } from '../../core/api';
import {
  PlayerSplits,
  RankedPlayerRow,
  ScoreBreakdown,
  TRADE_PRIORITIES,
  TradePriority,
} from '../../core/api.types';
import { TradeListStore } from '../../core/trade-list-store';
import {
  battingComponents,
  battingSkillRows,
  fieldingRows,
  gradeTone,
  hasModifiers,
  makeupRows,
  modifierGroup,
  otherComponents,
  pitchArsenal,
  pitchingComponents,
  pitchingMiscRows,
  pitchingSkillRows,
  showBatting,
  showPitching,
  speedRows,
  splitRows,
  typeSeverity,
} from '../../core/player-stats';

/** The expanded-row content: grouped, type-gated scouting + model breakdown. */
@Component({
  selector: 'app-player-detail-card',
  imports: [DecimalPipe, NgTemplateOutlet, FormsModule, TagModule, PanelModule],
  templateUrl: './player-detail-card.html',
  styleUrl: './player-detail-card.scss',
})
export class PlayerDetailCardComponent {
  readonly player = input.required<RankedPlayerRow>();
  /** Total ranked players — upper bound for the rank input. */
  readonly totalRanked = input(0);
  /** Whether the "Edit rank" control is offered — only draft classes have a
   *  hand-editable order; the live-league view hides it. */
  readonly canEditRank = input(true);
  /** New 1-based rank the user committed for this player. */
  readonly setRank = output<number>();

  /** Live-league only: the league's trade-list store. When set, a "Trade lists"
   *  block is shown (which lists the player is on, add / remove). */
  readonly tradeStore = input<TradeListStore | null>(null);
  /** Trade Targets page only: the list currently being viewed, so the priority
   *  / note editors know which entry to patch. */
  readonly tradeListId = input<string | null>(null);

  protected readonly onLists = computed(
    () => this.tradeStore()?.listsWith(this.player().id) ?? [],
  );
  protected readonly allLists = computed(() => this.tradeStore()?.lists() ?? []);
  protected readonly priorities = TRADE_PRIORITIES;
  protected readonly newListName = signal('');
  protected readonly tlBusy = signal(false);

  /** Local, editable copies of the viewed entry's priority / note — seeded from
   *  the row (which carries them only when loaded via `tradeListPlayers`). */
  protected readonly priorityDraft = signal<TradePriority>('MEDIUM');
  protected readonly noteDraft = signal('');

  protected isOnList(listId: string): boolean {
    return this.allLists().find((l) => l.id === listId)?.entryIds.includes(this.player().id)
      ?? false;
  }

  protected async toggleList(listId: string, on: boolean): Promise<void> {
    const store = this.tradeStore();
    if (!store || this.tlBusy()) return;
    this.tlBusy.set(true);
    try {
      if (on) await store.addPlayer(listId, this.player().id);
      else await store.removePlayer(listId, this.player().id);
    } finally {
      this.tlBusy.set(false);
    }
  }

  protected async addNewList(): Promise<void> {
    const store = this.tradeStore();
    const name = this.newListName().trim();
    if (!store || !name || this.tlBusy()) return;
    this.tlBusy.set(true);
    try {
      const made = await store.create(name);
      await store.addPlayer(made.id, this.player().id);
      this.newListName.set('');
    } finally {
      this.tlBusy.set(false);
    }
  }

  /** Commit the priority / note editors — only meaningful with a `tradeListId`
   *  in context (the Trade Targets page). */
  protected async commitEntry(): Promise<void> {
    const store = this.tradeStore();
    const listId = this.tradeListId();
    if (!store || !listId) return;
    await store.setEntry(listId, this.player().id, {
      priority: this.priorityDraft(),
      note: this.noteDraft(),
    });
  }

  protected readonly editing = signal(false);
  protected readonly draftRank = signal<number | null>(null);

  private readonly api = inject(ApiService);
  /** How the score was built — fetched when the card opens, not shipped with
   *  every table row. Null while loading (those sections just stay hidden). */
  protected readonly breakdown = signal<ScoreBreakdown | null>(null);

  /** Batting / pitching grids show current + potential, or (live league only -
   *  OOTP's draft export has no splits) the current ratings vs L / vs R. The
   *  splits cost a model run, so they're fetched the first time L/R is picked.
   *  `undefined` while loading, null when the snapshot has no splits. */
  protected readonly splitMode = signal(false);
  protected readonly splits = signal<PlayerSplits | null | undefined>(undefined);
  private splitsFor: RankedPlayerRow | null = null;

  /** Colour a split cell against the combined current rating. */
  protected splitTone(v: number | null, combined: number | null): string {
    if (v == null || combined == null || v === combined) return '';
    return v > combined ? 'up' : 'down';
  }

  constructor() {
    effect(() => {
      const p = this.player();
      untracked(() => {
        this.priorityDraft.set((p.priority as TradePriority) ?? 'MEDIUM');
        this.noteDraft.set(p.note ?? '');
      });
    });
    effect(() => {
      const p = this.player();
      this.breakdown.set(null);
      this.api.playerBreakdown(p.source, p.id).then(
        (b) => {
          if (this.player() === p) this.breakdown.set(b);
        },
        () => {}, // the card still shows the scores and ratings without it
      );
    });
    effect(() => {
      const p = this.player();
      if (!this.splitMode() || this.splitsFor === p) return;
      this.splitsFor = p;
      this.splits.set(undefined);
      this.api.playerSplits(p.source, p.id).then(
        (s) => {
          if (this.player() === p) this.splits.set(s);
        },
        () => {
          if (this.player() === p) this.splits.set(null);
        },
      );
    });
  }

  protected readonly rankMax = computed(() => this.totalRanked() || null);

  /** "Org · Team · Level" for live-league rows; empty in the draft-class view. */
  protected readonly orgLine = computed(() => {
    const p = this.player();
    return [p.org, p.team && p.team !== p.org ? p.team : null, p.level]
      .filter(Boolean)
      .join(' · ');
  });

  protected startEdit(): void {
    this.draftRank.set(this.player().rank);
    this.editing.set(true);
  }

  protected cancelEdit(): void {
    this.editing.set(false);
  }

  protected commitRank(): void {
    const next = Math.round(Number(this.draftRank()));
    if (!Number.isFinite(next) || next < 1 || next === this.player().rank) {
      this.editing.set(false);
      return;
    }
    this.setRank.emit(next);
    this.editing.set(false);
  }

  protected readonly showBatting = showBatting;
  protected readonly showPitching = showPitching;
  protected readonly typeSeverity = typeSeverity;

  /** p-tag severity for the scout-accuracy badge — no red, so it never reads
   *  like the "drafted" tag. */
  protected scoutSeverity(v: unknown): 'success' | 'warn' | 'secondary' {
    const t = gradeTone(v);
    return t === 'danger' ? 'warn' : t === 'warn' ? 'secondary' : 'success';
  }
  protected readonly makeupRows = makeupRows;
  protected readonly battingSkillRows = battingSkillRows;
  protected readonly speedRows = speedRows;
  protected readonly fieldingRows = fieldingRows;
  protected readonly pitchingSkillRows = pitchingSkillRows;
  protected readonly pitchingMiscRows = pitchingMiscRows;
  protected readonly pitchArsenal = pitchArsenal;
  protected readonly battingComponents = battingComponents;
  protected readonly pitchingComponents = pitchingComponents;
  protected readonly hasModifiers = hasModifiers;
  protected readonly modifierGroup = modifierGroup;
  protected readonly otherComponents = otherComponents;
  protected readonly splitRows = splitRows;
}
