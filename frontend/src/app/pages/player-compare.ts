import { Component, computed, input, output } from '@angular/core';
import { DialogModule } from 'primeng/dialog';
import { TagModule } from 'primeng/tag';

import { RankedPlayerRow } from '../core/api.types';
import {
  RatingRow,
  battingSkillRows,
  fieldingRows,
  makeupRows,
  modifierGroup,
  otherComponents,
  pitchArsenal,
  pitchingMiscRows,
  pitchingSkillRows,
  showBatting,
  showPitching,
  speedRows,
  typeSeverity,
} from '../core/player-stats';

export interface CompareRow {
  label: string;
  a: string;
  b: string;
  /** which side is numerically ahead (blank = tie / not comparable) */
  win: 'a' | 'b' | null;
}

export interface CompareSection {
  title: string;
  rows: CompareRow[];
}

type Num = number | null | undefined;

/** Merge two label-keyed lists, keeping A's order then B-only extras. */
function align<T>(
  aRows: readonly [string, T][],
  bRows: readonly [string, T][],
): { label: string; a: T | null; b: T | null }[] {
  const map = new Map<string, { label: string; a: T | null; b: T | null }>();
  const order: string[] = [];
  for (const [k, v] of aRows) {
    map.set(k, { label: k, a: v, b: null });
    order.push(k);
  }
  for (const [k, v] of bRows) {
    const e = map.get(k);
    if (e) e.b = v;
    else {
      map.set(k, { label: k, a: null, b: v });
      order.push(k);
    }
  }
  return order.map((k) => map.get(k)!);
}

function fmtNum(v: Num, decimals: number): string {
  return v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(decimals);
}

function numericRow(
  label: string,
  a: Num,
  b: Num,
  decimals = 2,
  higherBetter = true,
): CompareRow {
  let win: 'a' | 'b' | null = null;
  if (a != null && b != null && Number.isFinite(+a) && Number.isFinite(+b) && +a !== +b) {
    win = higherBetter === +a > +b ? 'a' : 'b';
  }
  return { label, a: fmtNum(a, decimals), b: fmtNum(b, decimals), win };
}

function textRow(label: string, a: string | null, b: string | null): CompareRow {
  return { label, a: a ?? '—', b: b ?? '—', win: null };
}

/** "current · potential" pair, compared on the current (overall) rating. */
function ratingRow(label: string, a: RatingRow | null, b: RatingRow | null): CompareRow {
  const show = (r: RatingRow | null) =>
    r ? `${r.current ?? '—'} · ${r.potential ?? '—'}` : '—';
  let win: 'a' | 'b' | null = null;
  const ac = a?.current;
  const bc = b?.current;
  if (ac != null && bc != null && ac !== bc) win = ac > bc ? 'a' : 'b';
  return { label, a: show(a), b: show(b), win };
}

function dropEmpty(rows: CompareRow[]): CompareRow[] {
  return rows.filter((r) => !(r.a === '—' && r.b === '—'));
}

/**
 * Row for a value of unknown shape: numeric when both sides parse, else text.
 * `judge` off keeps the raw diagnostic numbers unhighlighted — higher isn't
 * necessarily "better" for pipeline internals.
 */
function valueRow(label: string, a: unknown, b: unknown, judge = true): CompareRow {
  const parse = (v: unknown) => (v == null || v === '' ? null : Number(v));
  const an = parse(a);
  const bn = parse(b);
  const aOk = a == null || (an != null && Number.isFinite(an));
  const bOk = b == null || (bn != null && Number.isFinite(bn));
  if (aOk && bOk && (an != null || bn != null)) {
    const row = numericRow(label, an, bn, 2);
    return judge ? row : { ...row, win: null };
  }
  return textRow(label, a == null ? null : String(a), b == null ? null : String(b));
}

@Component({
  selector: 'app-player-compare',
  imports: [DialogModule, TagModule],
  templateUrl: './player-compare.html',
  styleUrl: './player-compare.scss',
})
export class PlayerCompareComponent {
  readonly a = input<RankedPlayerRow | null>(null);
  readonly b = input<RankedPlayerRow | null>(null);
  readonly visible = input(false);
  readonly closed = output<void>();

  protected readonly typeSeverity = typeSeverity;

  protected readonly sections = computed<CompareSection[]>(() => {
    const A = this.a();
    const B = this.b();
    if (!A || !B) return [];

    const anyBat = showBatting(A.type) || showBatting(B.type);
    const anyPitch = showPitching(A.type) || showPitching(B.type);
    const out: CompareSection[] = [];

    out.push({
      title: 'Player',
      rows: [
        textRow('Type', A.type, B.type),
        textRow('Position', A.position, B.position),
        textRow('Age', A.age?.toString() ?? null, B.age?.toString() ?? null),
        numericRow('Rank', A.rank, B.rank, 0, false),
        textRow('Demand', A.demand, B.demand),
      ],
    });

    out.push({
      title: 'Overview',
      rows: [
        numericRow('In-game OVR', A.inGameOverall, B.inGameOverall, 0),
        numericRow('In-game POT', A.inGamePotential, B.inGamePotential, 0),
        ...align(makeupRows(A), makeupRows(B)).map((r) => textRow(r.label, r.a, r.b)),
      ],
    });

    if (anyBat) {
      const skills = align(
        battingSkillRows(A).map((r) => [r.label, r] as [string, RatingRow]),
        battingSkillRows(B).map((r) => [r.label, r] as [string, RatingRow]),
      ).map((r) => ratingRow(r.label, r.a, r.b));
      const speed = align(speedRows(A), speedRows(B)).map((r) =>
        numericRow(r.label, r.a, r.b, 0),
      );
      const rows = dropEmpty([...skills, ...speed]);
      if (rows.length) out.push({ title: 'Batting & speed', rows });

      const field = dropEmpty(
        align(fieldingRows(A), fieldingRows(B)).map((r) =>
          numericRow(r.label, r.a, r.b, 0),
        ),
      );
      if (field.length) out.push({ title: 'Fielding', rows: field });
    }

    if (anyPitch) {
      const skills = align(
        pitchingSkillRows(A).map((r) => [r.label, r] as [string, RatingRow]),
        pitchingSkillRows(B).map((r) => [r.label, r] as [string, RatingRow]),
      ).map((r) => ratingRow(r.label, r.a, r.b));
      const misc = align(pitchingMiscRows(A), pitchingMiscRows(B)).map((r) =>
        textRow(r.label, r.a, r.b),
      );
      const rows = dropEmpty([...skills, ...misc]);
      if (rows.length) out.push({ title: 'Pitching', rows });

      // Pitches only carry a potential rating, so compare on that alone.
      const arsenal = dropEmpty(
        align(
          pitchArsenal(A).map((p) => [p.name, p.potential] as [string, number | null]),
          pitchArsenal(B).map((p) => [p.name, p.potential] as [string, number | null]),
        ).map((r) => numericRow(r.label, r.a, r.b, 0)),
      );
      if (arsenal.length) out.push({ title: 'Arsenal (pot)', rows: arsenal });
    }

    out.push({
      title: 'Model',
      rows: dropEmpty([
        numericRow('Overall', A.modelScore, B.modelScore),
        numericRow('Raw overall', A.rawOverallScore, B.rawOverallScore),
        numericRow('Batter score', A.positionPlayerScore, B.positionPlayerScore),
        numericRow('Pitcher score', A.pitcherScore, B.pitcherScore),
        numericRow('Batting model', A.battingScoreComponent, B.battingScoreComponent),
        numericRow('Fielding model', A.fieldingScoreComponent, B.fieldingScoreComponent),
        numericRow('Running model', A.runningScoreComponent, B.runningScoreComponent),
        numericRow('SP model', A.starterComponent, B.starterComponent),
        numericRow('RP model', A.relieverComponent, B.relieverComponent),
      ]),
    });

    // Score multipliers. When a two-way player brings both groups, prefix the
    // per-modifier rows so "Pos" and "Pitcher" entries stay distinguishable.
    const posA = anyBat ? modifierGroup(A, 'pos') : null;
    const posB = anyBat ? modifierGroup(B, 'pos') : null;
    const pitA = anyPitch ? modifierGroup(A, 'pitcher') : null;
    const pitB = anyPitch ? modifierGroup(B, 'pitcher') : null;
    const bothGroups = !!(posA || posB) && !!(pitA || pitB);
    const modRows: CompareRow[] = [];

    if (posA || posB) {
      const pre = bothGroups ? 'Pos: ' : '';
      modRows.push(
        ...align(
          (posA?.rows ?? []).map((m) => [m.label, m.value] as [string, number]),
          (posB?.rows ?? []).map((m) => [m.label, m.value] as [string, number]),
        ).map((r) => numericRow(pre + r.label, r.a, r.b, 3)),
        numericRow('Position modifiers ×', posA?.total, posB?.total, 3),
      );
    }
    if (pitA || pitB) {
      const pre = bothGroups ? 'Pitcher: ' : '';
      modRows.push(
        ...align(
          (pitA?.rows ?? []).map((m) => [m.label, m.value] as [string, number]),
          (pitB?.rows ?? []).map((m) => [m.label, m.value] as [string, number]),
        ).map((r) => numericRow(pre + r.label, r.a, r.b, 3)),
        numericRow('Pitcher modifiers ×', pitA?.total, pitB?.total, 3),
      );
    }
    const mods = dropEmpty(modRows);
    if (mods.length) out.push({ title: 'Modifiers', rows: mods });

    // The "Diagnostics" panel from the detail view: raw pipeline internals.
    const diag = dropEmpty(
      align<unknown>(otherComponents(A), otherComponents(B)).map((r) =>
        valueRow(r.label, r.a, r.b, false),
      ),
    );
    if (diag.length) out.push({ title: 'Diagnostics', rows: diag });

    return out;
  });

  protected onVisibleChange(v: boolean): void {
    if (!v) this.closed.emit();
  }
}
