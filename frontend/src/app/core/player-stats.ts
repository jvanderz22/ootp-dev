/**
 * Pure helpers for turning a `RankedPlayer` into the row/skill groups the
 * class-view detail panel and the side-by-side compare view both render.
 * Kept free of `this` so components can expose them as plain fields.
 */
import {
  LedgerLine,
  PlayerSplits,
  PlayerType,
  RankedPlayer,
  ScoreBreakdown,
  SplitScores,
} from './api.types';

export interface RatingRow {
  label: string;
  potential: number | null;
  current: number | null;
  /** one of the parts OOTP builds the row above it from (Contact, Movement) */
  part?: boolean;
}

/** Drops a composite's part rows the export doesn't carry (old classes have
 *  no BABIP / HRA / PBABIP). */
function withParts(rows: RatingRow[]): RatingRow[] {
  return rows.filter((r) => !r.part || r.current != null || r.potential != null);
}

// ---------------------------------------------------------- player typing
export function classify(p: RankedPlayer): PlayerType {
  const pp = p.positionPlayerScore ?? 0;
  const pit = p.pitcherScore ?? 0;
  const hi = Math.max(pp, pit);
  const lo = Math.min(pp, pit);
  if (hi > 0 && lo * 2 > hi) return 'Two-way';
  return pit >= pp ? 'Pitcher' : 'Hitter';
}

export function typeSeverity(t: PlayerType): 'info' | 'warn' | 'success' {
  return t === 'Two-way' ? 'warn' : t === 'Pitcher' ? 'info' : 'success';
}

/** Generational suffixes kept intact when a name is abbreviated. */
const NAME_SUFFIXES = new Set(['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v']);

/**
 * Compact form of a player name for space-tight layouts (the mobile ranked
 * table): first initial + last name, keeping any generational suffix.
 * "Ronald Acuña Jr." → "R. Acuña Jr."; single-token or already-short names
 * pass through unchanged.
 */
export function abbreviatePlayerName(name: string): string {
  const raw = (name ?? '').trim();
  const parts = raw.split(/\s+/);
  if (parts.length < 2) return raw;
  let last = parts.length - 1;
  let suffix = '';
  if (parts.length > 2 && NAME_SUFFIXES.has(parts[last].toLowerCase())) {
    suffix = ` ${parts[last]}`;
    last -= 1;
  }
  const initial = parts[0].charAt(0).toUpperCase();
  return `${initial}. ${parts[last]}${suffix}`;
}

/**
 * Colour cue for the descriptive scouting grades (personality, injury
 * proneness, scout accuracy): red for the weakest tiers, amber for "average".
 */
export function gradeTone(v: unknown): '' | 'danger' | 'warn' {
  const s = String(v ?? '').trim().toLowerCase();
  if (s === 'wrecked' || s === 'fragile' || s === 'low' || s === 'very low') return 'danger';
  if (s === 'average') return 'warn';
  return '';
}

/**
 * Numeric sort key for the contract-demand column so the table orders it by
 * dollar value rather than lexically. Mirrors `parse_demand` in the pipeline:
 * a trailing `k`/`m` scales the digits (× 1_000 / × 100_000), "Slot" is 0, and
 * "Impossible" sorts past every real figure. Missing/unparseable demands sort
 * below "Slot".
 */
export function demandSortKey(demand: string | null | undefined): number {
  if (!demand) return -1;
  const s = demand.trim().toLowerCase();
  if (s === 'slot') return 0;
  if (s === 'impossible') return Number.POSITIVE_INFINITY;
  const digits = s.replace(/[^0-9]/g, '');
  if (!digits) return -1;
  const n = Number(digits);
  if (s.endsWith('k')) return n * 1_000;
  if (s.endsWith('m')) return n * 100_000;
  return n;
}

export function showBatting(t: PlayerType): boolean {
  return t === 'Hitter' || t === 'Two-way';
}

export function showPitching(t: PlayerType): boolean {
  return t === 'Pitcher' || t === 'Two-way';
}

// --------------------------------------------------- scouting attributes
export function makeupRows(p: RankedPlayer): [string, string][] {
  const r = p.ratings;
  if (!r) return [];
  const rows: [string, string | null][] = [
    ['Bats / Throws', [r.batHand, r.throwHand].filter(Boolean).join(' / ') || null],
    ['Durability', r.injuryProne],
    ['Work ethic', r.workEthic],
    ['Intelligence', r.intelligence],
    ['Leadership', r.leadership],
  ];
  return rows.filter(([, v]) => !!v) as [string, string][];
}

export function battingSkillRows(p: RankedPlayer): RatingRow[] {
  const b = p.ratings?.batting;
  if (!b) return [];
  return withParts([
    { label: 'Contact', potential: b['contact'], current: b['contactCur'] },
    { label: 'BABIP', potential: b['babip'], current: b['babipCur'], part: true },
    { label: 'Avoid K', potential: b['avoidK'], current: b['avoidKCur'], part: true },
    { label: 'Gap', potential: b['gap'], current: b['gapCur'] },
    { label: 'Power', potential: b['power'], current: b['powerCur'] },
    { label: 'Eye', potential: b['eye'], current: b['eyeCur'] },
  ]);
}

export function speedRows(p: RankedPlayer): [string, number | null][] {
  const b = p.ratings?.batting;
  if (!b) return [];
  return [
    ['Speed', b['speed']],
    ['Steal', b['steal']],
    ['Baserunning', b['running']],
  ];
}

export function fieldingRows(p: RankedPlayer): [string, number][] {
  const f = p.ratings?.fielding;
  if (!f) return [];
  const spec: [string, string][] = [
    ['IF range', 'ifRange'], ['IF arm', 'ifArm'], ['IF error', 'ifError'], ['Turn DP', 'turnDp'],
    ['OF range', 'ofRange'], ['OF arm', 'ofArm'], ['OF error', 'ofError'],
    ['C framing', 'cFraming'], ['C blocking', 'cBlocking'], ['C arm', 'cArm'],
  ];
  return spec
    .map(([label, key]) => [label, f[key] ?? 0] as [string, number])
    .filter(([, v]) => v > 0);
}

export function pitchingSkillRows(p: RankedPlayer): RatingRow[] {
  const pt = p.ratings?.pitching;
  if (!pt) return [];
  return withParts([
    { label: 'Stuff', potential: pt.stuff, current: pt.stuffCur },
    { label: 'Movement', potential: pt.movement, current: pt.movementCur },
    { label: 'HR allowed', potential: pt.hra, current: pt.hraCur, part: true },
    { label: 'PBABIP', potential: pt.pbabip, current: pt.pbabipCur, part: true },
    { label: 'Control', potential: pt.control, current: pt.controlCur },
  ]);
}

export function pitchingMiscRows(p: RankedPlayer): [string, string][] {
  const pt = p.ratings?.pitching;
  if (!pt) return [];
  const rows: [string, string | number | null][] = [
    ['Stamina', pt.stamina],
    ['Velocity', pt.velocity],
    ['GB type', pt.groundballType],
    ['Arm slot', pt.armSlot],
  ];
  return rows.filter(([, v]) => v != null && v !== 0).map(([k, v]) => [k, String(v)]);
}

export function pitchArsenal(p: RankedPlayer) {
  return p.ratings?.pitching.pitches ?? [];
}

// ------------------------------------------------------- platoon splits
export interface SplitRow {
  label: string;
  /** the combined current rating */
  combined: number | null;
  vsL: number | null;
  vsR: number | null;
  part?: boolean;
  /** engine v2's read of the side (wRC+ / ERA), not a rating */
  model?: boolean;
  /** ERA: a lower number is the better side */
  lowerBetter?: boolean;
  decimals?: number;
}

// Same order as battingSkillRows / pitchingSkillRows; `true` marks a part.
const BATTING_SPLIT_SPEC: [string, keyof SplitScores, boolean?][] = [
  ['Contact', 'contact'],
  ['BABIP', 'babip', true],
  ['Avoid K', 'avoidK', true],
  ['Gap', 'gap'],
  ['Power', 'power'],
  ['Eye', 'eye'],
];

const PITCHING_SPLIT_SPEC: [string, keyof SplitScores, boolean?][] = [
  ['Stuff', 'stuff'],
  ['Movement', 'movement'],
  ['HR allowed', 'hra', true],
  ['PBABIP', 'pbabip', true],
  ['Control', 'control'],
];

/** Combined / vs-L / vs-R rows for the batting or pitching rating grid's L/R mode. */
export function splitRows(s: PlayerSplits | null | undefined, side: 'batting' | 'pitching'): SplitRow[] {
  if (!s) return [];
  const spec = side === 'batting' ? BATTING_SPLIT_SPEC : PITCHING_SPLIT_SPEC;
  const ratings = spec
    .map(([label, key, part]) => ({
      label,
      combined: s.combined[key] as number | null,
      vsL: s.vsL[key] as number | null,
      vsR: s.vsR[key] as number | null,
      part,
    }))
    .filter((r) => !r.part || r.combined != null || r.vsL != null || r.vsR != null);
  // v2's read of each side heads the grid when there is one
  const model: SplitRow =
    side === 'batting'
      ? { label: 'wRC+', combined: s.combined.wrcPlus, vsL: s.vsL.wrcPlus, vsR: s.vsR.wrcPlus, model: true }
      : {
          label: `ERA as ${s.combined.eraRole ?? ''}`.trim(),
          combined: s.combined.era,
          vsL: s.vsL.era,
          vsR: s.vsR.era,
          model: true,
          lowerBetter: true,
          decimals: 2,
        };
  return model.combined == null ? ratings : [model, ...ratings];
}

// ------------------------------------------------------- score breakdown
// The model internals behind a score come from `playerBreakdown` (fetched on
// demand), already trimmed server-side to the side(s) the player is judged on.

/** "DraftSecondaryPersonalityModifier" -> "Draft secondary personality" */
function prettyModifier(raw: string): string {
  const s = raw
    .replace(/Modifier$/, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    .trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : raw;
}

function present(rows: [string, number | null][]): [string, number][] {
  return rows.filter(([, v]) => v != null) as [string, number][];
}

export function battingComponents(
  b: ScoreBreakdown | null,
  bestPosition: string | null,
): [string, number][] {
  const bat = b?.batting;
  if (!bat) return [];
  return present([
    [bestPosition ? `Best position (${bestPosition})` : 'Best position', bat.bestPositionScore],
    ['Utility bonus', bat.utilityBonus],
    ['Batting model (raw)', bat.battingModel],
    ['Running model (raw)', bat.runningModel],
    ['Position model (raw)', bat.positionModel],
  ]);
}

export function pitchingComponents(b: ScoreBreakdown | null): [string, number][] {
  const pit = b?.pitching;
  if (!pit) return [];
  const { starter: sp, reliever: rp } = pit;
  return present([
    ['SP pitch-mix ×', sp.pitchMix],
    ['SP HR-risk ×', sp.hrRisk],
    ['SP model (raw)', sp.model],
    ['SP modifiers ×', sp.baseModifier],
    ['RP model (raw)', rp.model],
    ['RP modifiers ×', rp.baseModifier],
    ['SP score w/ mods', sp.score],
    ['RP score w/ mods', rp.score],
  ]);
}

export function modifierGroup(
  b: ScoreBreakdown | null,
  kind: 'pos' | 'pitcher',
): { rows: { label: string; value: number }[]; total: number | null } | null {
  const group = (kind === 'pos' ? b?.batting : b?.pitching)?.modifiers;
  const rows = (group?.modifiers ?? [])
    .filter((m) => m.value != null)
    .map((m) => ({ label: prettyModifier(m.name), value: m.value as number }));
  if (!rows.length) return null;
  return { rows, total: group?.total ?? null };
}

/** Whether there's a modifier group to show (sides are already type-scoped). */
export function hasModifiers(b: ScoreBreakdown | null): boolean {
  return !!modifierGroup(b, 'pos') || !!modifierGroup(b, 'pitcher');
}

/** The "Diagnostics" panel: rank adjustments plus any older-pipeline values. */
export function otherComponents(b: ScoreBreakdown | null): [string, unknown][] {
  if (!b) return [];
  const adj = b.rankAdjust;
  const rows: [string, unknown][] = [
    ...(adj?.modifiers ?? []).map(
      (m) => [`${prettyModifier(m.name)} (rank-adj)`, m.value] as [string, unknown],
    ),
    ['Pre rank-adjust rank', adj?.preRank ?? null],
    ['Pre rank-adjust score', adj?.preScore ?? null],
    ...b.legacy.map((m) => [m.name, m.value] as [string, unknown]),
  ];
  return rows.filter(([, v]) => v != null);
}

// v2's ledger is in display points, 50 + 10 x WAR: the card reads it in WAR,
// with the 50 of replacement level as the baseline rather than a line.
const REPLACEMENT_POINTS = 50;
const POINTS_PER_WAR = 10;

export function pointsToWar(points: number): number {
  return (points - REPLACEMENT_POINTS) / POINTS_PER_WAR;
}

/** One ledger line in WAR, placed on the waterfall: its bar runs from the
 *  running total before it to the one after, as a % of the range the totals
 *  span (zero included). */
export interface ValueStep {
  label: string;
  stat: string | null;
  note: string | null;
  war: number;
  left: number;
  width: number;
}

export interface ValueGroup {
  stage: string;
  title: string;
  steps: ValueStep[];
}

export interface ValueBuild {
  /** everything before the demand step, by stage in pipeline order */
  groups: ValueGroup[];
  /** his value: the sum of those groups */
  war: number;
  /** the demand step's lines (draft classes) */
  demand: ValueStep[];
  /** the score after demand, in WAR and in points */
  finalWar: number;
  score: number;
  /** lines with no effect (modifiers at x1.00) aren't drawn */
  hidden: number;
  /** the side he isn't judged on - listed, not counted */
  other: { title: string; war: number; steps: ValueStep[] } | null;
}

const VALUE_STAGE_TITLES: Record<string, string> = {
  model: 'Talent & role',
  modifiers: 'Adjustments',
  development: 'Development',
  'two-way': 'Two-way',
  demand: 'Demand',
};
const LEDGER_MIN_DELTA = 0.005;

function ledgerLabel(line: LedgerLine): string {
  const label =
    line.stage === 'modifiers' || line.stage === 'demand' ? prettyModifier(line.label) : line.label;
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** A line that moves nothing is still shown when it's a talent read (the
 *  platoon's "no starts"); a modifier at x1.00 isn't. */
function shown(line: LedgerLine): boolean {
  return Math.abs(line.delta) >= LEDGER_MIN_DELTA || (line.stage === 'model' && !!line.stat);
}

/** "+0.31" / "−0.06" / "0.00": signed, with a true minus, none once it rounds to zero. */
export function signedWar(war: number): string {
  const text = Math.abs(war).toFixed(2);
  if (Number(text) === 0) return text;
  return (war > 0 ? '+' : '−') + text;
}

/** Place `lines` as a waterfall from zero WAR. */
function waterfall(lines: LedgerLine[]): { line: LedgerLine; step: ValueStep }[] {
  let running = 0;
  let lo = 0;
  let hi = 0;
  const spans = lines.map((line) => {
    const start = running;
    running += line.delta / POINTS_PER_WAR;
    lo = Math.min(lo, running);
    hi = Math.max(hi, running);
    return { line, start, end: running };
  });
  const range = hi - lo || 1;
  return spans.map(({ line, start, end }) => ({
    line,
    step: {
      label: ledgerLabel(line),
      stat: line.stat,
      note: line.note,
      war: end - start,
      left: ((Math.min(start, end) - lo) / range) * 100,
      width: (Math.abs(end - start) / range) * 100,
    },
  }));
}

/** v2's ledger as the card's value build: in WAR, grouped by stage, demand
 *  apart. Null when there's no ledger (the legacy engine). */
export function valueBuild(b: ScoreBreakdown | null): ValueBuild | null {
  if (!b?.ledger?.length) return null;
  const isBaseline = (l: LedgerLine) =>
    l.stage === 'model' && l.side == null && l.label === 'replacement level';
  const counted = b.ledger.filter((l) => l.counted && !isBaseline(l));
  const groups: ValueGroup[] = [];
  const demand: ValueStep[] = [];
  let hidden = 0;
  let war = 0;
  let finalWar = 0;
  for (const { line, step } of waterfall(counted)) {
    finalWar += step.war;
    if (line.stage !== 'demand') war += step.war;
    if (!shown(line)) {
      hidden++;
    } else if (line.stage === 'demand') {
      demand.push(step);
    } else {
      let group = groups[groups.length - 1];
      if (group?.stage !== line.stage) {
        group = { stage: line.stage, title: VALUE_STAGE_TITLES[line.stage] ?? line.stage, steps: [] };
        groups.push(group);
      }
      group.steps.push(step);
    }
  }
  const rest = b.ledger.filter((l) => !l.counted);
  const other = rest.length
    ? {
        title: rest[0].side === 'pitching' ? 'As a pitcher' : 'As a hitter',
        war: rest.reduce((sum, l) => sum + l.delta, 0) / POINTS_PER_WAR,
        steps: waterfall(rest)
          .filter(({ line }) => shown(line))
          .map(({ step }) => step),
      }
    : null;
  return {
    groups,
    war,
    demand,
    finalWar,
    score: REPLACEMENT_POINTS + finalWar * POINTS_PER_WAR,
    hidden,
    other,
  };
}

/** The headline stat of the counted ledger line named `label`, if any. */
export function ledgerStat(b: ScoreBreakdown | null, label: string): string | null {
  return b?.ledger.find((l) => l.counted && l.label === label)?.stat ?? null;
}

// ---------------------------------------------------------- fielding matrix
// The ten fielding ratings as three groups: infield and outfield share
// Range / Arm / Error (+ Turn DP), catcher has its own. The group his
// position plays from is the one his value reads, so the card marks it.

export interface FieldingGroup {
  key: 'IF' | 'OF' | 'C';
  label: string;
  cells: (number | null)[];
  primary: boolean;
}

const FIELD_GROUP_OF: Record<string, 'IF' | 'OF' | 'C'> = {
  '1B': 'IF', '2B': 'IF', '3B': 'IF', SS: 'IF', LF: 'OF', CF: 'OF', RF: 'OF', C: 'C',
};

export const FIELDING_HEADS = {
  field: ['Range', 'Arm', 'Error', 'DP'],
  catcher: ['Frame', 'Block', 'Arm'],
};

export function fieldingMatrix(p: RankedPlayer, position: string | null): FieldingGroup[] {
  const f = p.ratings?.fielding;
  if (!f) return [];
  const main = position ? FIELD_GROUP_OF[position] : undefined;
  const v = (k: string) => (f[k] ? (f[k] as number) : null);
  const groups: FieldingGroup[] = [
    { key: 'IF', label: 'Infield', cells: [v('ifRange'), v('ifArm'), v('ifError'), v('turnDp')], primary: main === 'IF' },
    { key: 'OF', label: 'Outfield', cells: [v('ofRange'), v('ofArm'), v('ofError'), null], primary: main === 'OF' },
    { key: 'C', label: 'Catcher', cells: [v('cFraming'), v('cBlocking'), v('cArm')], primary: main === 'C' },
  ];
  return groups.filter((g) => g.cells.some((c) => c != null));
}
