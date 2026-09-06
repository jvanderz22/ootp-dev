/**
 * Column presets for the ranked-player table. Each view shares a block of
 * leading identity / summary columns and then appends its own rating columns.
 * `field` doubles as the sort key sent to the backend (a flat payload key in
 * camelCase, a dotted rating path like `batting.power`, or `pitch.<Name>`).
 */
import { ClassView, RankedPlayerRow } from './api.types';
import { gradeTone } from './player-stats';

/** Pitchers first, then scorekeeping order for position players. */
export const POSITION_ORDER = [
  'P',
  'SP',
  'RP',
  'CL',
  'C',
  '1B',
  '2B',
  '3B',
  'SS',
  'LF',
  'CF',
  'RF',
  'OF',
  'IF',
  'DH',
];

export const PITCHER_POSITIONS = ['P', 'SP', 'RP', 'CL'];

/** The eight positions the fielding models score — the option set for the
 *  "Best Pos" filter (which is model-derived, so pitchers never appear). */
export const FIELDING_POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF'];

export type ColGroup =
  | 'Player'
  | 'Draft'
  | 'In-Game'
  | 'Model'
  | 'Batting'
  | 'Running'
  | 'Infield'
  | 'Outfield'
  | 'Catching'
  | 'Pitching'
  | 'Arsenal'
  | 'Makeup'
  | 'Demand';

export interface ColumnDef {
  field: string;
  header: string;
  /** right-aligned + tabular numerals */
  numeric: boolean;
  /** first header click sorts descending (model / rating columns) */
  descFirst: boolean;
  group: ColGroup;
  /** cell accessor — reads the payload or digs into `ratings` */
  value: (p: RankedPlayerRow) => unknown;
  /** cell formatter */
  fmt: (v: unknown) => string;
  /** render as a coloured player-type tag instead of text */
  tag?: boolean;
  /** abbreviated header — full label surfaced as a `title` tooltip */
  title?: string;
  /** pin against the table's left edge during horizontal scroll */
  sticky?: 'rank' | 'name' | 'pos';
  /** widen the cell and keep its text on one line */
  wide?: boolean;
  /** optional colour cue for the cell text, from its formatted-ish value */
  tone?: (v: unknown) => '' | 'danger' | 'warn';
  /** optional per-cell tooltip (e.g. the full team name behind a short code) */
  cellTitle?: (v: unknown) => string;
}

// ---------------------------------------------------------------- formatters
const N = (v: unknown) => Number(v);
const isBlank = (v: unknown) => v == null || v === '' || Number.isNaN(N(v));

export const fmtNum2 = (v: unknown): string => (isBlank(v) ? '—' : N(v).toFixed(2));
export const fmtInt = (v: unknown): string => (isBlank(v) ? '—' : String(Math.round(N(v))));
export const fmtText = (v: unknown): string => (v == null || v === '' ? '—' : String(v));
/** 20–80 scouting grade: 0 / missing shows as a dash */
export const fmtGrade = (v: unknown): string =>
  isBlank(v) || N(v) <= 0 ? '—' : String(Math.round(N(v)));
/** Right / Left / Switch → R / L / S */
export const fmtHand = (v: unknown): string =>
  v == null || v === '' ? '—' : String(v).charAt(0).toUpperCase();
/** Real-world abbreviations for the clubs this league carries, keyed by the full
 *  "City Nickname" string the snapshot / draft feed emits (StatsPlus has no
 *  abbreviation field — `/api/teams/` is only id, city, nickname, parent). Add a
 *  line here when a club is missing or renamed; unlisted names fall back to the
 *  3-letter trim below. Keys are lower-cased. */
const TEAM_CODES: Record<string, string> = {
  'arizona diamondbacks': 'ARI',
  'atlanta braves': 'ATL',
  'baltimore orioles': 'BAL',
  'boston red sox': 'BOS',
  'chicago cubs': 'CHC',
  'chicago white sox': 'CWS',
  'cincinnati reds': 'CIN',
  'cleveland guardians': 'CLE',
  'cleveland spiders': 'CLE',
  'colorado rockies': 'COL',
  'detroit tigers': 'DET',
  'houston astros': 'HOU',
  'kansas city royals': 'KC',
  'los angeles angels': 'LAA',
  'los angeles dodgers': 'LAD',
  'miami marlins': 'MIA',
  'milwaukee brewers': 'MIL',
  'minnesota twins': 'MIN',
  'new york mets': 'NYM',
  'new york yankees': 'NYY',
  'oakland athletics': 'OAK',
  'philadelphia phillies': 'PHI',
  'pittsburgh pirates': 'PIT',
  'san diego padres': 'SD',
  'san francisco giants': 'SF',
  'seattle mariners': 'SEA',
  'st. louis cardinals': 'STL',
  'st louis cardinals': 'STL',
  'tampa bay rays': 'TB',
  'texas rangers': 'TEX',
  'toronto blue jays': 'TOR',
  'washington nationals': 'WSH',
  'washington senators': 'WSH',
  'diablos rojos de cdmx': 'CDMX',
};

/** Team name → a compact code: a real abbreviation from `TEAM_CODES` when the
 *  club is known, else a ~3-letter trim ("Expos" → "EXP"). Full name in a cell
 *  tooltip either way. */
export const fmtTeamCode = (v: unknown): string => {
  if (v == null || v === '') return '—';
  const name = String(v).trim();
  const mapped = TEAM_CODES[name.toLowerCase()];
  if (mapped) return mapped;
  const s = name.replace(/[^A-Za-z]/g, '');
  return s ? s.slice(0, 3).toUpperCase() : '—';
};
/** Map full descriptive words to short tags; unknowns pass through unchanged. */
const abbrev =
  (map: Record<string, string>) =>
  (v: unknown): string => {
    if (v == null || v === '') return '—';
    const s = String(v).trim();
    return map[s.toLowerCase()] ?? s;
  };
/** Very High → VH, Average → A, Very Low → VL … */
export const fmtScoutAcc = abbrev({
  'very high': 'VH',
  high: 'H',
  average: 'A',
  low: 'L',
  'very low': 'VL',
});
/** Iron Man → IM, Durable → D, Normal → N, Fragile → F, Wrecked → W */
export const fmtDurability = abbrev({
  'iron man': 'IM',
  durable: 'D',
  normal: 'N',
  fragile: 'F',
  wrecked: 'W',
});

// ---------------------------------------------------------------- accessors
const bat = (k: string) => (p: RankedPlayerRow) => p.ratings?.batting?.[k] ?? null;
const field = (k: string) => (p: RankedPlayerRow) => p.ratings?.fielding?.[k] ?? null;
const pitch =
  (k: 'stuff' | 'movement' | 'control' | 'stamina' | 'velocity' | 'groundballType') =>
  (p: RankedPlayerRow) =>
    p.ratings?.pitching?.[k] ?? null;
const arsenal = (name: string) => (p: RankedPlayerRow) =>
  p.ratings?.pitching?.pitches?.find((x) => x.name.toLowerCase() === name.toLowerCase())
    ?.potential ?? null;

const model =
  (k: keyof RankedPlayerRow): ((p: RankedPlayerRow) => unknown) =>
  (p) =>
    p[k];

type MetaKey = 'injuryProne' | 'workEthic' | 'intelligence' | 'leadership' | 'scoutingAccuracy';
const meta = (k: MetaKey) => (p: RankedPlayerRow) => p.ratings?.[k] ?? null;

// ---------------------------------------------------------------- column sets
export const LEADING_COLUMNS: ColumnDef[] = [
  {
    field: 'rank',
    header: '#',
    numeric: true,
    descFirst: false,
    group: 'Player',
    value: model('rank'),
    fmt: fmtInt,
    sticky: 'rank',
  },
  {
    field: 'name',
    header: 'Name',
    numeric: false,
    descFirst: false,
    group: 'Player',
    value: model('name'),
    fmt: fmtText,
    sticky: 'name',
  },
  {
    field: 'type',
    header: 'Type',
    numeric: false,
    descFirst: false,
    group: 'Player',
    value: model('type'),
    fmt: fmtText,
    tag: true,
  },
  {
    field: 'position',
    header: 'Pos',
    numeric: false,
    descFirst: false,
    group: 'Player',
    value: model('position'),
    fmt: fmtText,
    sticky: 'pos',
  },
  {
    field: 'age',
    header: 'Age',
    numeric: true,
    descFirst: false,
    group: 'Player',
    value: model('age'),
    fmt: fmtInt,
  },
  {
    field: 'batHand',
    header: 'Bats',
    numeric: false,
    descFirst: false,
    group: 'Player',
    value: model('batHand'),
    fmt: fmtHand,
  },
  {
    field: 'throwHand',
    header: 'Throws',
    numeric: false,
    descFirst: false,
    group: 'Player',
    value: model('throwHand'),
    fmt: fmtHand,
  },
  {
    field: 'inGameOverall',
    header: 'OVR',
    numeric: true,
    descFirst: true,
    group: 'In-Game',
    value: model('inGameOverall'),
    fmt: fmtInt,
  },
  {
    field: 'inGamePotential',
    header: 'POT',
    numeric: true,
    descFirst: true,
    group: 'In-Game',
    value: model('inGamePotential'),
    fmt: fmtInt,
  },
  {
    field: 'modelScore',
    header: 'Overall',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('modelScore'),
    fmt: fmtNum2,
  },
];

/** Org (3-letter code, full name on hover) + Level identity — live-league view
 *  only, inserted right after the Pos column in every view (see `viewColumns`). */
export const LEAGUE_IDENTITY_COLUMNS: ColumnDef[] = [
  {
    field: 'org',
    header: 'Org',
    numeric: false,
    descFirst: false,
    group: 'Player',
    value: model('org'),
    fmt: fmtTeamCode,
    cellTitle: (v) => (v == null || v === '' ? '' : String(v)),
  },
  {
    field: 'level',
    header: 'Lvl',
    title: 'Level',
    numeric: false,
    descFirst: false,
    group: 'Player',
    value: model('level'),
    fmt: fmtText,
  },
];

/** compact factory for a 20–80 scouting-grade column */
const gradeCol = (
  fieldKey: string,
  header: string,
  title: string,
  group: ColGroup,
  value: (p: RankedPlayerRow) => unknown,
): ColumnDef => ({
  field: fieldKey,
  header,
  title,
  numeric: true,
  descFirst: true,
  group,
  value,
  fmt: fmtGrade,
});

/** compact factory for a descriptive text-grade column (personality, etc.) */
const textCol = (
  fieldKey: string,
  header: string,
  title: string,
  group: ColGroup,
  value: (p: RankedPlayerRow) => unknown,
  fmt: (v: unknown) => string = fmtText,
): ColumnDef => ({
  field: fieldKey,
  header,
  title,
  numeric: false,
  descFirst: false,
  group,
  value,
  fmt,
  tone: gradeTone,
});

/** Market demand — trails every view as its own group. */
const DEMAND_COLUMN: ColumnDef = {
  field: 'demandKey',
  header: 'Demand',
  numeric: false,
  descFirst: false,
  group: 'Demand',
  value: model('demand'),
  fmt: fmtText,
};

/** Personality / scouting grades shared by the batting & pitching views. */
const PERSONALITY_COLUMNS: ColumnDef[] = [
  textCol('workEthic', 'WE', 'Work ethic', 'Makeup', meta('workEthic')),
  textCol('intelligence', 'INT', 'Intelligence', 'Makeup', meta('intelligence')),
  textCol('leadership', 'L', 'Leadership', 'Makeup', meta('leadership')),
  textCol(
    'scoutingAccuracy',
    'SCT',
    'Scout accuracy',
    'Makeup',
    meta('scoutingAccuracy'),
    fmtScoutAcc,
  ),
];

const DURABILITY_COLUMN = textCol(
  'injuryProne',
  'DUR',
  'Durability',
  'Makeup',
  meta('injuryProne'),
  fmtDurability,
);

/** Where a drafted player went — blank for players still on the board. Only the
 *  modeled view carries these, trailing every other column; `Pick` is the
 *  overall selection number, `Team` a short code with the full name on hover. */
const DRAFT_COLUMNS: ColumnDef[] = [
  {
    field: 'draftedPick',
    header: 'Pick',
    title: 'Overall pick',
    numeric: true,
    descFirst: false,
    group: 'Draft',
    value: model('draftedPick'),
    fmt: fmtInt,
  },
  {
    field: 'draftedTeam',
    header: 'Team',
    title: 'Drafting team',
    numeric: false,
    descFirst: false,
    group: 'Draft',
    value: model('draftedTeam'),
    fmt: fmtTeamCode,
    cellTitle: (v) => (v == null || v === '' ? '' : String(v)),
  },
];

/** The model's best-fit fielding position — a categorical value, filtered via a
 *  dedicated position picker rather than a numeric bound. Sits in the Model
 *  group in every view that carries it. */
const BEST_POS_COLUMN: ColumnDef = {
  field: 'bestPosition',
  header: 'Best Pos',
  title: 'Model best-fit position',
  numeric: false,
  descFirst: false,
  group: 'Model',
  value: model('bestPosition'),
  fmt: fmtText,
  wide: true,
};

const MODELED_COLUMNS: ColumnDef[] = [
  {
    field: 'positionPlayerScore',
    header: 'Batter',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('positionPlayerScore'),
    fmt: fmtNum2,
  },
  {
    field: 'pitcherScore',
    header: 'Pitcher',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('pitcherScore'),
    fmt: fmtNum2,
  },
  {
    field: 'battingScoreComponent',
    header: 'Batting',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('battingScoreComponent'),
    fmt: fmtNum2,
  },
  {
    field: 'fieldingScoreComponent',
    header: 'Fielding',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('fieldingScoreComponent'),
    fmt: fmtNum2,
  },
  BEST_POS_COLUMN,
  {
    field: 'runningScoreComponent',
    header: 'Running',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('runningScoreComponent'),
    fmt: fmtNum2,
  },
  {
    field: 'starterComponent',
    header: 'SP',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('starterComponent'),
    fmt: fmtNum2,
  },
  {
    field: 'relieverComponent',
    header: 'RP',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('relieverComponent'),
    fmt: fmtNum2,
  },
  DEMAND_COLUMN,
  ...DRAFT_COLUMNS,
];

const BATTING_COLUMNS: ColumnDef[] = [
  gradeCol('batting.contact', 'CON', 'Contact', 'Batting', bat('contact')),
  gradeCol('batting.avoidK', 'Ks', 'Avoid K', 'Batting', bat('avoidK')),
  gradeCol('batting.gap', 'GAP', 'Gap', 'Batting', bat('gap')),
  gradeCol('batting.power', 'POW', 'Power', 'Batting', bat('power')),
  gradeCol('batting.eye', 'EYE', 'Eye', 'Batting', bat('eye')),
  BEST_POS_COLUMN,
  gradeCol('fielding.ifRange', 'IFR', 'IF Range', 'Infield', field('ifRange')),
  gradeCol('fielding.ifArm', 'IFA', 'IF Arm', 'Infield', field('ifArm')),
  gradeCol('fielding.turnDp', 'DP', 'Turn DP', 'Infield', field('turnDp')),
  gradeCol('fielding.ofRange', 'OFR', 'OF Range', 'Outfield', field('ofRange')),
  gradeCol('fielding.ofArm', 'OFA', 'OF Arm', 'Outfield', field('ofArm')),
  gradeCol('fielding.cFraming', 'CFR', 'C Framing', 'Catching', field('cFraming')),
  gradeCol('fielding.cBlocking', 'CBL', 'C Blocking', 'Catching', field('cBlocking')),
  gradeCol('batting.speed', 'SPD', 'Speed', 'Running', bat('speed')),
  gradeCol('batting.steal', 'STL', 'Steal', 'Running', bat('steal')),
  ...PERSONALITY_COLUMNS,
  DEMAND_COLUMN,
];

const PITCH_TYPES: [string, string][] = [
  ['Fastball', 'FB'],
  ['Slider', 'SL'],
  ['Curveball', 'CB'],
  ['Changeup', 'CH'],
  ['Sinker', 'SI'],
  ['Splitter', 'SP'],
  ['Cutter', 'CT'],
  ['Forkball', 'FK'],
  ['Circlechange', 'CC'],
  ['Screwball', 'SC'],
  ['Knuckleball', 'KN'],
  ['Knucklecurve', 'KC'],
];

const PITCHING_COLUMNS: ColumnDef[] = [
  gradeCol('pitching.stuff', 'STU', 'Stuff', 'Pitching', pitch('stuff')),
  gradeCol('pitching.movement', 'MOV', 'Movement', 'Pitching', pitch('movement')),
  gradeCol('pitching.control', 'CTL', 'Control', 'Pitching', pitch('control')),
  gradeCol('pitching.stamina', 'STM', 'Stamina', 'Pitching', pitch('stamina')),
  {
    field: 'pitching.velocity',
    header: 'VELO',
    title: 'Velocity',
    numeric: false,
    descFirst: false,
    group: 'Pitching',
    value: pitch('velocity'),
    fmt: fmtText,
    wide: true,
  },
  {
    field: 'pitching.groundballType',
    header: 'GB',
    title: 'Groundball type',
    numeric: false,
    descFirst: false,
    group: 'Pitching',
    value: pitch('groundballType'),
    fmt: fmtText,
  },
  ...PITCH_TYPES.map(([name, abbr]): ColumnDef => ({
    field: `pitch.${name}`,
    header: abbr,
    title: name,
    numeric: true,
    descFirst: true,
    group: 'Arsenal',
    value: arsenal(name),
    fmt: fmtGrade,
  })),
  DURABILITY_COLUMN,
  ...PERSONALITY_COLUMNS,
  DEMAND_COLUMN,
];

/** Leading block for the rating views: drop the player-type tag but keep the
 *  blended overall; each view then appends its own side-of-the-ball score. */
const RATING_LEAD = LEADING_COLUMNS.filter((c) => c.field !== 'type');

const BATTING_LEAD: ColumnDef[] = [
  ...RATING_LEAD,
  {
    field: 'positionPlayerScore',
    header: 'Batter',
    title: 'Overall batter model score',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('positionPlayerScore'),
    fmt: fmtNum2,
  },
];

const PITCHING_LEAD: ColumnDef[] = [
  ...RATING_LEAD,
  {
    field: 'pitcherScore',
    header: 'Pitcher',
    title: 'Overall pitcher model score',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('pitcherScore'),
    fmt: fmtNum2,
  },
];

export const VIEW_COLUMNS: Record<ClassView, ColumnDef[]> = {
  modeled: [...LEADING_COLUMNS, ...MODELED_COLUMNS],
  batting: [...BATTING_LEAD, ...BATTING_COLUMNS],
  pitching: [...PITCHING_LEAD, ...PITCHING_COLUMNS],
};

/** Columns with no meaning for a live-league snapshot: the drafted/demand
 *  columns and the draft-class player-type tag. */
const DROPPED_IN_LEAGUE = new Set(['demandKey', 'draftedPick', 'draftedTeam', 'type']);

/** Columns for a view in a given context. `'league'` drops the demand / drafted
 *  columns and the player-type tag, and inserts Org / Level right after Pos. */
export function viewColumns(view: ClassView, context: 'class' | 'league' = 'class'): ColumnDef[] {
  const base = VIEW_COLUMNS[view];
  if (context !== 'league') return base;
  // Drop the drafted/demand columns and the Type tag; Pos stays sticky right
  // after Name, with Org (3-letter code) and Level slotted in just after it.
  const trimmed = base.filter((c) => !DROPPED_IN_LEAGUE.has(c.field));
  const at = trimmed.findIndex((c) => c.field === 'position') + 1;
  return [...trimmed.slice(0, at), ...LEAGUE_IDENTITY_COLUMNS, ...trimmed.slice(at)];
}

export const DEFAULT_SORT: Record<ClassView, { field: string; order: 1 | -1 }> = {
  modeled: { field: 'rank', order: 1 },
  batting: { field: 'rank', order: 1 },
  pitching: { field: 'rank', order: 1 },
};

export const VIEW_OPTIONS: { label: string; value: ClassView }[] = [
  { label: 'Modeled', value: 'modeled' },
  { label: 'Batting', value: 'batting' },
  { label: 'Pitching', value: 'pitching' },
];

/** Descriptive-grade columns whose text maps to a tier ordinal the backend can
 *  still compare with >/< (Very Low = 0 … Very High = 4;
 *  Wrecked/Fragile/Normal/Durable/Iron Man = 0/1/2/3/4). */
const GRADED_TEXT_FIELDS = new Set([
  'injuryProne',
  'workEthic',
  'intelligence',
  'leadership',
  'scoutingAccuracy',
]);

export interface FilterableField {
  field: string;
  /** "Batting · Power" — group-prefixed so the flat picker stays legible */
  label: string;
  group: ColGroup;
  /** true when the column shows tier text, not a number (hint in the UI) */
  graded: boolean;
}

/** Every column across all three views that supports a numeric >/< bound —
 *  numeric ratings/scores plus the graded-text and demand columns — deduped by
 *  field so one master list backs the filter dropdown regardless of the view. */
export const FILTERABLE_FIELDS: FilterableField[] = (() => {
  const seen = new Set<string>();
  const out: FilterableField[] = [];
  for (const cols of Object.values(VIEW_COLUMNS)) {
    for (const c of cols) {
      const graded = GRADED_TEXT_FIELDS.has(c.field);
      const usable = (c.numeric || graded || c.field === 'demandKey') && c.field !== 'rank';
      if (!usable || seen.has(c.field)) continue;
      seen.add(c.field);
      const name = c.field === 'demandKey' ? 'Demand ($ value)' : (c.title ?? c.header);
      out.push({ field: c.field, label: `${c.group} · ${name}`, group: c.group, graded });
    }
  }
  return out;
})();

/** Contiguous group runs across a column list, for the first header row. */
export function groupSpans(cols: ColumnDef[]): { label: ColGroup; span: number }[] {
  const out: { label: ColGroup; span: number }[] = [];
  for (const c of cols) {
    const last = out[out.length - 1];
    if (last && last.label === c.group) last.span += 1;
    else out.push({ label: c.group, span: 1 });
  }
  return out;
}
