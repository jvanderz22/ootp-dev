/**
 * Column presets for the ranked-player table. Each view shares a block of
 * leading identity / summary columns and then appends its own rating columns.
 * `field` doubles as the sort key sent to the backend (a flat payload key in
 * camelCase, a dotted rating path like `batting.power`, or `pitch.<Name>`).
 */
import { ClassView, RankedPlayerRow } from './api.types';
import { RankingEngine } from './engine';
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
  | 'WAR'
  | 'Batting'
  | 'Running'
  | 'Positions'
  | 'Infield'
  | 'Outfield'
  | 'Catching'
  | 'Pitching'
  | 'Arsenal'
  | 'Makeup'
  | 'Demand'
  | 'Compare';

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
  tone?: (v: unknown) => '' | 'danger' | 'warn' | 'good';
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
  // v2 engine only (blank under legacy): the score and rank before the draft
  // demand step, so a pick's talent order and its signable order sit side by side
  {
    field: 'preDemandScore',
    header: 'Pre-dem',
    title: 'Score before the demand step',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('preDemandScore'),
    fmt: fmtNum2,
  },
  {
    field: 'preDemandRank',
    header: 'Pre-dem #',
    title: 'Rank before the demand step',
    numeric: true,
    descFirst: false,
    group: 'Model',
    value: model('preDemandRank'),
    fmt: fmtInt,
  },
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
  // v2 engine only: the fitted talent model's line, on the ranking's ratings
  // (potential ones for prospects and draft classes)
  {
    field: 'wrcPlus',
    header: 'wRC+',
    title: 'Modeled wRC+ from the batting ratings (100 = MLB average)',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('wrcPlus'),
    fmt: fmtInt,
  },
  {
    field: 'era',
    header: 'ERA',
    title: 'Modeled ERA from the pitching ratings, as a starter or reliever (whichever he is judged as)',
    numeric: true,
    descFirst: false,
    group: 'Model',
    value: model('era'),
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

const fmtSigned = (digits: number) => (v: unknown): string => {
  if (isBlank(v)) return '—';
  const n = N(v);
  return (n > 0 ? '+' : '') + n.toFixed(digits);
};
const compareCol = (
  field: keyof RankedPlayerRow,
  header: string,
  title: string,
  descFirst: boolean,
  fmt: (v: unknown) => string,
  tone?: ColumnDef['tone'],
): ColumnDef => ({
  field,
  header,
  title,
  numeric: true,
  descFirst,
  group: 'Compare',
  value: model(field),
  fmt,
  tone,
});

/** The Compare view: each engine's overall score and rank side by side. Ranks
 *  are each engine's model order; the units differ (legacy points, v2's
 *  50 + 10 × WAR), so the rank diff is the like-for-like one. */
const COMPARE_COLUMNS: ColumnDef[] = [
  compareCol('legacyScore', 'Legacy', 'Legacy engine overall score (points)', true, fmtNum2),
  compareCol('legacyRank', 'Legacy #', 'Rank under the legacy engine', false, fmtInt),
  compareCol('v2Score', 'v2', 'v2 engine overall score (50 + 10 × WAR)', true, fmtNum2),
  compareCol('v2Rank', 'v2 #', 'Rank under the v2 engine', false, fmtInt),
  compareCol(
    'rankDiff',
    'Rank Δ',
    'Legacy rank minus v2 rank: positive when v2 ranks him higher',
    true,
    fmtSigned(0),
    (v) => (isBlank(v) || N(v) === 0 ? '' : N(v) > 0 ? 'good' : 'danger'),
  ),
  compareCol('scoreDiff', 'Score Δ', 'v2 score minus legacy score (different units: a rough guide)', true, fmtSigned(1)),
];

/** The fields only the Compare view's query fills in. */
export const COMPARE_FIELDS = new Set(COMPARE_COLUMNS.map((c) => c.field));

const COMPARE_LEAD = LEADING_COLUMNS.filter((c) =>
  ['rank', 'name', 'type', 'position', 'age', 'inGameOverall', 'inGamePotential'].includes(c.field),
);

export const VIEW_COLUMNS: Record<ClassView, ColumnDef[]> = {
  modeled: [...LEADING_COLUMNS, ...MODELED_COLUMNS],
  batting: [...BATTING_LEAD, ...BATTING_COLUMNS],
  pitching: [...PITCHING_LEAD, ...PITCHING_COLUMNS],
  compare: [...COMPARE_LEAD, ...COMPARE_COLUMNS],
};

// ------------------------------------------------------------- v2 columns
// v2 values every player in WAR, so its views read in WAR: his value before
// demand, where he's valued, the talent line behind it, and its parts. Each
// side's columns are blank for players not judged on that side.

const warCol = (
  field: keyof RankedPlayerRow,
  header: string,
  title: string,
  group: ColGroup = 'WAR',
): ColumnDef => ({
  field,
  header,
  title,
  numeric: true,
  descFirst: true,
  group,
  value: model(field),
  fmt: fmtNum2,
});

const WAR_COLUMN = warCol('war', 'WAR', 'v2 WAR on StatsPlus’s scale, before the demand step', 'Model');

/** What the rank is on for current ratings: his WAR above the league's own
 *  replacement for his spot (blank where the two are the same). */
const surplusCol = (group: ColGroup) =>
  warCol(
    'surplusWar',
    'Surplus WAR',
    'WAR above what the league gives away free at his spot (WAR minus the spot’s price) - what the rank is on',
    group,
  );

/** His potential ratings' WAR in a full-time role (the league's boards). */
export const CEILING_TITLE = 'WAR at full potential';
const ceilingCol = (group: ColGroup) => warCol('ceilingWar', 'Ceiling', CEILING_TITLE, group);

const ROLE_COLUMN: ColumnDef = {
  field: 'role',
  header: 'Role',
  title: 'Where v2 values him: his best position, or SP / RP',
  numeric: false,
  descFirst: false,
  group: 'Model',
  value: model('role'),
  fmt: fmtText,
};

const field_ = (f: string) => MODELED_COLUMNS.find((c) => c.field === f)!;

/** The score the rank is on, after demand (50 + 10 x WAR); draft classes only,
 *  where demand can move it off his WAR. */
const V2_SCORE_COLUMN: ColumnDef = {
  ...LEADING_COLUMNS.find((c) => c.field === 'modelScore')!,
  header: 'Score',
  title: 'Score the rank is on: after the demand step, 50 + 10 × WAR',
};

const V2_LEAD = LEADING_COLUMNS.filter((c) => c.field !== 'modelScore');

const V2_MODELED_COLUMNS: ColumnDef[] = [
  WAR_COLUMN,
  V2_SCORE_COLUMN,
  field_('preDemandRank'),
  ROLE_COLUMN,
  field_('wrcPlus'),
  field_('era'),
  warCol('battingWar', 'Bat', 'Batting WAR, with the playing-time credit over replacement'),
  warCol('fieldingWar', 'Fld', 'Fielding WAR at his position, with its adjustment and utility'),
  warCol('runningWar', 'Run', 'Baserunning WAR'),
  warCol('starterWar', 'SP', 'WAR as a starter'),
  warCol('relieverWar', 'RP', 'WAR as a reliever (the better of SP / RP counts)'),
  surplusCol('WAR'),
  DEMAND_COLUMN,
  ...DRAFT_COLUMNS,
];

/** A pitcher's ERA in one role (overall, or against one batting hand), and
 *  his innings in the role he's valued in (the Pitching view). */
type RoleEraField = 'spEra' | 'rpEra' | 'spEraVl' | 'spEraVr' | 'rpEraVl' | 'rpEraVr';
const roleEraCol = (field: RoleEraField, header: string, title: string): ColumnDef => ({
  field,
  header,
  title,
  numeric: true,
  descFirst: false,
  group: 'Model',
  value: model(field),
  fmt: fmtNum2,
});
const V2_PITCHING_MODEL: ColumnDef[] = [
  roleEraCol('spEra', 'SP ERA', 'Modeled ERA as a starter (blank when he can’t start)'),
  roleEraCol('rpEra', 'RP ERA', 'Modeled ERA as a reliever'),
  roleEraCol('spEraVl', 'SP vL', 'Modeled ERA as a starter vs LHB (his splits, or estimated)'),
  roleEraCol('spEraVr', 'SP vR', 'Modeled ERA as a starter vs RHB (his splits, or estimated)'),
  roleEraCol('rpEraVl', 'RP vL', 'Modeled ERA as a reliever vs LHB (his splits, or estimated)'),
  roleEraCol('rpEraVr', 'RP vR', 'Modeled ERA as a reliever vs RHB (his splits, or estimated)'),
  {
    field: 'ip',
    header: 'IP',
    title: 'Innings in the role he’s valued in: a starter’s by stamina and efficiency, or the reliever workload',
    numeric: true,
    descFirst: true,
    group: 'Model',
    value: model('ip'),
    fmt: fmtInt,
  },
];

/** A hitter's wRC+ against one pitcher hand (the Batting view). */
const splitWrcCol = (field: 'wrcVl' | 'wrcVr', header: string, hand: string): ColumnDef => ({
  field,
  header,
  title: `Modeled wRC+ vs ${hand} (his splits, or expected for his hand)`,
  numeric: true,
  descFirst: true,
  group: 'Model',
  value: model(field),
  fmt: fmtInt,
});

/** His fielding value at each position, as the card's position table: runs
 *  with the position's adjustment. Field `pos.<POS>` sorts and filters on it. */
const fmtRuns = (v: unknown): string => {
  if (isBlank(v)) return '—';
  const r = Math.round(N(v));
  return r > 0 ? `+${r}` : String(r);
};
const POSITION_VALUE_COLUMNS: ColumnDef[] = FIELDING_POSITIONS.map((pos) => ({
  field: `pos.${pos}`,
  header: pos,
  title: `Fielding value at ${pos}: runs, with the position's adjustment`,
  numeric: true,
  descFirst: true,
  group: 'Positions',
  value: (p: RankedPlayerRow) => p.positionValues?.find((x) => x.position === pos)?.value ?? null,
  fmt: fmtRuns,
}));

/** The Batting view under v2: the ratings with the model's reads beside
 *  them - each position's value after Best Pos, baserunning WAR after the
 *  running grades. */
const V2_BATTING_COLUMNS: ColumnDef[] = BATTING_COLUMNS.flatMap((c) =>
  c === BEST_POS_COLUMN
    ? [c, ...POSITION_VALUE_COLUMNS]
    : c.field === 'batting.steal'
      ? [c, warCol('runningWar', 'WAR', 'Baserunning WAR', 'Running')]
      : [c],
);

const V2_VIEW_COLUMNS: Record<ClassView, ColumnDef[]> = {
  modeled: [...V2_LEAD, ...V2_MODELED_COLUMNS],
  batting: [
    ...V2_LEAD.filter((c) => c.field !== 'type'),
    WAR_COLUMN,
    field_('wrcPlus'),
    splitWrcCol('wrcVl', 'vL', 'LHP'),
    splitWrcCol('wrcVr', 'vR', 'RHP'),
    surplusCol('Model'),
    ceilingCol('Model'),
    ...V2_BATTING_COLUMNS,
  ],
  pitching: [
    ...V2_LEAD.filter((c) => c.field !== 'type'),
    WAR_COLUMN,
    field_('era'),
    ...V2_PITCHING_MODEL,
    surplusCol('Model'),
    ceilingCol('Model'),
    ...PITCHING_COLUMNS,
  ],
  compare: VIEW_COLUMNS.compare,
};

// ------------------------------------------------------ the draft board
// A draft board (the draft odds) reads on a 1-100 score, not WAR (decided
// 2026-11-10; ranking/value.py's `draft_score`): the score the rank is on,
// before demand, and his ceiling. The card keeps his peak and ceiling WAR.

const scoreCol = (field: keyof RankedPlayerRow, header: string, title: string): ColumnDef => ({
  field,
  header,
  title,
  numeric: true,
  descFirst: true,
  group: 'Model',
  value: model(field),
  fmt: fmtInt,
});

const SCORE_COLUMN = scoreCol('score', 'Score', 'Score (1–100), after demand: what the rank is on');
const VALUE_SCORE_COLUMN = scoreCol('valueScore', 'Pre-dem', 'Score (1–100) before demand');
const CEILING_SCORE_COLUMN = scoreCol('ceilingScore', 'Ceiling', 'Ceiling (1–100): at full potential');

/** A v2 view's columns on the draft board's scale: WAR and the points score
 *  become the 1-100 score, the ceiling its own; Surplus WAR is blank there. */
const onDraftScale = (cols: ColumnDef[]): ColumnDef[] =>
  cols
    .filter((c) => c.field !== 'modelScore' && c.field !== 'surplusWar')
    .map((c) => (c.field === 'war' ? SCORE_COLUMN : c.field === 'ceilingWar' ? CEILING_SCORE_COLUMN : c));

const DRAFT_BOARD_COLUMNS: Record<ClassView, ColumnDef[]> = {
  modeled: [
    ...V2_LEAD,
    SCORE_COLUMN,
    VALUE_SCORE_COLUMN,
    field_('preDemandRank'),
    CEILING_SCORE_COLUMN,
    ...onDraftScale(V2_MODELED_COLUMNS).filter((c) => c !== SCORE_COLUMN && c.field !== 'preDemandRank'),
  ],
  batting: onDraftScale(V2_VIEW_COLUMNS.batting),
  pitching: onDraftScale(V2_VIEW_COLUMNS.pitching),
  compare: VIEW_COLUMNS.compare,
};

const COLUMNS_BY_ENGINE: Record<RankingEngine, Record<ClassView, ColumnDef[]>> = {
  v2: V2_VIEW_COLUMNS,
  legacy: VIEW_COLUMNS,
};

/** Columns with no meaning for a live-league snapshot: the drafted/demand
 *  columns (pre-demand included) and the draft-class player-type tag. */
const DROPPED_IN_LEAGUE = new Set([
  'demandKey',
  'draftedPick',
  'draftedTeam',
  'type',
  'preDemandScore',
  'preDemandRank',
]);

/** Columns for a view in a given context and engine. `'league'` drops the
 *  demand / drafted columns and the player-type tag, and inserts Org / Level
 *  right after Pos; under v2 it drops the score too (no demand step, so it's
 *  just his WAR in points). `draftBoard`: v2 rows with the draft odds, read on
 *  the board's 1-100 scale. */
export function viewColumns(
  view: ClassView,
  context: 'class' | 'league' = 'class',
  engine: RankingEngine = 'v2',
  draftBoard = false,
): ColumnDef[] {
  const base = engine === 'v2' && draftBoard ? DRAFT_BOARD_COLUMNS[view] : COLUMNS_BY_ENGINE[engine][view];
  if (context !== 'league') return base;
  const dropped = engine === 'v2' && view !== 'compare' ? new Set([...DROPPED_IN_LEAGUE, 'modelScore']) : DROPPED_IN_LEAGUE;
  // Drop the drafted/demand columns and the Type tag; Pos stays sticky right
  // after Name, with Org (3-letter code) and Level slotted in just after it.
  const trimmed = base.filter((c) => !dropped.has(c.field));
  const at = trimmed.findIndex((c) => c.field === 'position') + 1;
  return [...trimmed.slice(0, at), ...LEAGUE_IDENTITY_COLUMNS, ...trimmed.slice(at)];
}

/** Phones: the view's model columns right after the pinned Pos, so a player's
 *  value is on screen without scrolling sideways. */
export function modelFirst(cols: ColumnDef[]): ColumnDef[] {
  const rest = cols.filter((c) => c.group !== 'Model');
  const at = rest.findIndex((c) => c.sticky === 'pos') + 1;
  if (!at) return cols;
  return [...rest.slice(0, at), ...cols.filter((c) => c.group === 'Model'), ...rest.slice(at)];
}

export const DEFAULT_SORT: Record<ClassView, { field: string; order: 1 | -1 }> = {
  modeled: { field: 'rank', order: 1 },
  batting: { field: 'rank', order: 1 },
  pitching: { field: 'rank', order: 1 },
  compare: { field: 'rank', order: 1 },
};

export const VIEW_OPTIONS: { label: string; value: ClassView }[] = [
  { label: 'Modeled', value: 'modeled' },
  { label: 'Batting', value: 'batting' },
  { label: 'Pitching', value: 'pitching' },
  { label: 'Compare', value: 'compare' },
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

/** Every column across the views that supports a numeric >/< bound — numeric
 *  ratings/scores plus the graded-text and demand columns — deduped by field so
 *  one list backs the filter dropdown regardless of the view. */
function filterableIn(views: Record<ClassView, ColumnDef[]>): FilterableField[] {
  const seen = new Set<string>();
  const out: FilterableField[] = [];
  for (const cols of Object.values(views)) {
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
}

/** What the filter picker offers: the engine's own columns, or the draft
 *  board's. */
export const FILTER_PICKER_FIELDS: Record<RankingEngine | 'draft', FilterableField[]> = {
  v2: filterableIn(V2_VIEW_COLUMNS),
  legacy: filterableIn(VIEW_COLUMNS),
  draft: filterableIn(DRAFT_BOARD_COLUMNS),
};

/** Every filterable field under either engine - for reading a filter back
 *  (from the URL, or a column header) whichever engine wrote it. */
export const FILTERABLE_FIELDS: FilterableField[] = [
  FILTER_PICKER_FIELDS.v2,
  FILTER_PICKER_FIELDS.draft,
  FILTER_PICKER_FIELDS.legacy,
]
  .flat()
  .filter((f, i, all) => all.findIndex((g) => g.field === f.field) === i);

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
