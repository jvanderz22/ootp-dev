/**
 * Pure helpers for turning a `RankedPlayer` into the row/skill groups the
 * class-view detail panel and the side-by-side compare view both render.
 * Kept free of `this` so components can expose them as plain fields.
 */
import { PlayerType, RankedPlayer } from './api.types';

export interface RatingRow {
  label: string;
  potential: number | null;
  current: number | null;
}

/** Nicer labels for the noisier `components` keys shown in the detail view. */
const KEY_LABELS: Record<string, string> = {
  'Pos - Batting Model': 'Batting model (raw)',
  'Pos - Running Model': 'Running model (raw)',
  'Pos - Overall Model Score': 'Position model (raw)',
  'Pos - Utility Bonus': 'Utility bonus',
  'SP Model Score': 'SP model (raw)',
  'RP Model Score': 'RP model (raw)',
  'SP Base Modifier': 'SP modifiers ×',
  'RP Base Modifier': 'RP modifiers ×',
  'SP Pitcher Pitch Component': 'SP pitch-mix ×',
  'SP HR component': 'SP HR-risk ×',
  'Starter Score w/Modifiers': 'SP score w/ mods',
  'Reliever Score w/Modifiers': 'RP score w/ mods',
  'Pre Rank-adj Rank': 'Pre rank-adjust rank',
  'Pre Rank-adj Score': 'Pre rank-adjust score',
};

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

/**
 * Colour cue for the descriptive scouting grades (personality, injury
 * proneness, scout accuracy): red for the weakest tiers, amber for "average".
 */
export function gradeTone(v: unknown): '' | 'danger' | 'warn' {
  const s = String(v ?? '').trim().toLowerCase();
  if (s === 'fragile' || s === 'low' || s === 'very low') return 'danger';
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
  ];
  return rows.filter(([, v]) => v != null && v !== 0).map(([k, v]) => [k, String(v)]);
}

export function pitchArsenal(p: RankedPlayer) {
  return p.ratings?.pitching.pitches ?? [];
}

// ------------------------------------------------------ component grouping
function pick(p: RankedPlayer, prefixes: string[]): [string, number][] {
  const c = p.components;
  if (!c) return [];
  return Object.entries(c)
    .filter(([k]) => prefixes.some((pre) => k.startsWith(pre)))
    .map(([k, v]) => [k, Number(v)] as [string, number]);
}

/** "DraftSecondaryPersonalityModifier" -> "Draft secondary personality" */
function prettyModifier(raw: string): string {
  const s = raw
    .replace(/Modifier$/, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    .trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : raw;
}

export function label(key: string): string {
  const mapped = KEY_LABELS[key];
  if (mapped) return mapped;
  const best = key.match(/^Pos - Best Pos Score \((\w+)\)$/);
  if (best) return `Best position (${best[1]})`;
  const rankAdj = key.match(/^Rank-adj Modifier (.+)$/);
  if (rankAdj) return `${prettyModifier(rankAdj[1])} (rank-adj)`;
  return key;
}

export function battingComponents(p: RankedPlayer): [string, number][] {
  return pick(p, ['Pos - ']).map(([k, v]) => [label(k), v]);
}

export function pitchingComponents(p: RankedPlayer): [string, number][] {
  return pick(p, ['SP ', 'RP ', 'Starter Score', 'Reliever Score']).map(
    ([k, v]) => [label(k), v],
  );
}

export function modifierGroup(
  p: RankedPlayer,
  kind: 'pos' | 'pitcher',
): { rows: { label: string; value: number }[]; total: number | null } | null {
  const c = p.components;
  if (!c) return null;
  const prefix = kind === 'pos' ? 'Pos Modifier ' : 'Pitcher Modifier ';
  const totalKey = kind === 'pos' ? 'Total Pos Modifier' : 'Total Pitcher Modifier';
  const rows = Object.entries(c)
    .filter(([k]) => k.startsWith(prefix))
    .map(([k, v]) => ({ label: prettyModifier(k.slice(prefix.length)), value: Number(v) }));
  if (!rows.length) return null;
  return { rows, total: c[totalKey] != null ? Number(c[totalKey]) : null };
}

/** Whether the player has a relevant modifier group to show (type-scoped). */
export function hasModifiers(p: { type: PlayerType } & RankedPlayer): boolean {
  return (
    (showBatting(p.type) && !!modifierGroup(p, 'pos')) ||
    (showPitching(p.type) && !!modifierGroup(p, 'pitcher'))
  );
}

export function otherComponents(p: RankedPlayer): [string, unknown][] {
  const c = p.components;
  if (!c) return [];
  const skip = [
    'Pos - ', 'SP ', 'RP ', 'Starter Score', 'Reliever Score',
    'Pos Modifier ', 'Pitcher Modifier ', 'Total Pos Modifier', 'Total Pitcher Modifier',
  ];
  return Object.entries(c)
    .filter(([k]) => !skip.some((pre) => k.startsWith(pre)))
    .map(([k, v]) => [label(k), v] as [string, unknown]);
}
