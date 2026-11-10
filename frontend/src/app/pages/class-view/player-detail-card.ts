import { Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { DecimalPipe, NgTemplateOutlet, PercentPipe } from '@angular/common';
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
  FIELDING_HEADS,
  fieldingMatrix,
  gradeTone,
  hasModifiers,
  ledgerStat,
  makeupRows,
  modifierGroup,
  otherComponents,
  pitchArsenal,
  pitchingComponents,
  pitchingMiscRows,
  pitchingSkillRows,
  positionFielding,
  showBatting,
  showPitching,
  signedWar,
  speedRows,
  splitRows,
  typeSeverity,
  valueBuild,
} from '../../core/player-stats';

/** The expanded-row content (and, on phones, the full-screen panel's). Under
 *  v2 it reads top-down as verdict -> why -> evidence: a band with his value
 *  and the talent behind it, the value build (the ledger, in WAR), then the
 *  ratings. Legacy keeps its model-score column. */
@Component({
  selector: 'app-player-detail-card',
  imports: [DecimalPipe, PercentPipe, NgTemplateOutlet, FormsModule, TagModule, PanelModule],
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
  /** Off when a surrounding panel already titles the card with the name. */
  readonly showName = input(true);
  /** New 1-based rank the user committed for this player. */
  readonly setRank = output<number>();

  /** Live-league only: the league's trade-list store (list membership itself is
   *  edited from the table row's star popover). */
  readonly tradeStore = input<TradeListStore | null>(null);
  /** Trade Targets page only: the list currently being viewed, so the priority
   *  / note editors know which entry to patch. */
  readonly tradeListId = input<string | null>(null);

  protected readonly priorities = TRADE_PRIORITIES;

  /** Local, editable copies of the viewed entry's priority / note — seeded from
   *  the row (which carries them only when loaded via `tradeListPlayers`). */
  protected readonly priorityDraft = signal<TradePriority>('MEDIUM');
  protected readonly noteDraft = signal('');

  protected isOnList(listId: string): boolean {
    return this.tradeStore()?.lists().find((l) => l.id === listId)?.entryIds
      .includes(this.player().id) ?? false;
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

  protected splitValue(v: number | null): string {
    return v == null ? '—' : String(v);
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

  /** The v2 ledger as the value build (null under legacy, or while loading). */
  protected readonly build = computed(() => valueBuild(this.breakdown()));

  protected readonly isV2 = computed(() => this.player().source.engine === 'v2');

  /** The v2 verdict band. It reads the table row, so it's there before the
   *  breakdown lands; the breakdown then adds the role he's valued in and
   *  what it reads. His WAR is before demand (the model's value); the score
   *  under it is what he's ranked on. */
  protected readonly verdict = computed(() => {
    const p = this.player();
    const b = this.breakdown();
    const pitching = b?.ledger.length
      ? b.ledger.some((l) => l.counted && l.side === 'pitching')
      : p.type === 'Pitcher';
    const role = b?.role ?? p.role ?? (pitching ? p.position : (p.bestPosition ?? p.position));
    const alt = b?.roleWar.find((r) => r.name !== role && r.value != null);
    const altEra = alt && b?.roleEra.find((r) => r.name === alt.name)?.value;
    const roleNote = pitching
      ? [
          ledgerStat(b, 'innings'),
          alt
            ? `${alt.name} ${altEra != null ? `${altEra.toFixed(2)} ERA, ` : ''}${alt.value!.toFixed(2)} WAR`
            : null,
        ]
      : [ledgerStat(b, 'utility')];
    const talentNote = b?.ledger.find(
      (l) => l.counted && l.label === (pitching ? 'pitching' : 'batting'),
    )?.note;
    return {
      war: p.war,
      talentNote: talentNote ?? null,
      score: p.modelScore,
      talent: pitching
        ? { value: p.era == null ? null : p.era.toFixed(2), label: 'ERA' }
        : { value: p.wrcPlus == null ? null : p.wrcPlus.toFixed(0), label: 'wRC+' },
      role,
      roleNote: roleNote.filter(Boolean).join(' · '),
    };
  });

  /** Fielding as an IF / OF / C matrix, his position's group marked. */
  protected readonly fielding = computed(() =>
    fieldingMatrix(this.player(), this.verdict().role ?? null),
  );
  protected readonly fieldingHeads = FIELDING_HEADS;

  /** v2: his fielding at every position, best first. */
  protected readonly positions = computed(() => positionFielding(this.breakdown()));

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

  protected readonly signedWar = signedWar;

  /** "+5" / "−4" / "0": whole runs, signed with a true minus. */
  protected signedRuns(v: number | null): string {
    if (v == null) return '—';
    const r = Math.round(v);
    return r > 0 ? `+${r}` : r < 0 ? `−${-r}` : '0';
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
