/**
 * Pure helpers for turning a `RankedPlayer` into the row/skill groups the
 * class-view detail panel and the side-by-side compare view both render.
 * Kept free of `this` so components can expose them as plain fields.
 */
import { PlayerType, RankedPlayer, ScoreBreakdown } from './api.types';

export interface RatingRow {
  label: string;
  potential: number | null;
  current: number | null;
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
  return [
    { label: 'Contact', potential: b['contact'], current: b['contactCur'] },
    { label: 'Avoid K', potential: b['avoidK'], current: b['avoidKCur'] },
    { label: 'Gap', potential: b['gap'], current: b['gapCur'] },
    { label: 'Power', potential: b['power'], current: b['powerCur'] },
    { label: 'Eye', potential: b['eye'], current: b['eyeCur'] },
  ];
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
  return [
    { label: 'Stuff', potential: pt.stuff, current: pt.stuffCur },
    { label: 'Movement', potential: pt.movement, current: pt.movementCur },
    { label: 'Control', potential: pt.control, current: pt.controlCur },
  ];
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
