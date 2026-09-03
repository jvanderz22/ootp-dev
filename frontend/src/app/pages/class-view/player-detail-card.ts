import { Component, computed, input, output, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TagModule } from 'primeng/tag';
import { PanelModule } from 'primeng/panel';

import { RankedPlayerRow } from '../../core/api.types';
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
  typeSeverity,
} from '../../core/player-stats';

/** The expanded-row content: grouped, type-gated scouting + model breakdown. */
@Component({
  selector: 'app-player-detail-card',
  imports: [DecimalPipe, FormsModule, TagModule, PanelModule],
  templateUrl: './player-detail-card.html',
  styleUrl: './player-detail-card.scss',
})
export class PlayerDetailCardComponent {
  readonly player = input.required<RankedPlayerRow>();
  /** Total ranked players — upper bound for the rank input. */
  readonly totalRanked = input(0);
  /** New 1-based rank the user committed for this player. */
  readonly setRank = output<number>();

  protected readonly editing = signal(false);
  protected readonly draftRank = signal<number | null>(null);

  protected readonly rankMax = computed(() => this.totalRanked() || null);

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
}
