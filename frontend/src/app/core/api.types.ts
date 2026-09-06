export interface DraftClass {
  name: string;
  rankingMethod: string;
  playerCount: number;
  hasCustomOrder: boolean;
  lastProcessed: string | null;
  draftedCount: number;
  leagueId: string | null;
  leagueName: string | null;
}

export interface League {
  id: string;
  name: string;
  leagueUrl: string | null;
  defaultLid: number | null;
  classNames: string[];
  /** ISO timestamp of the last snapshot pull; null if never refreshed. */
  updatedAt: string | null;
  /** Whether the league has a stored StatsPlus cookie. Values are never returned. */
  hasSessionid: boolean;
  hasCsrftoken: boolean;
}

export type LeagueRefreshState = 'idle' | 'running' | 'done' | 'error';

/** Progress of a background league-snapshot refresh. Survives navigation: the
 *  job runs server-side, the page polls `leagueRefreshStatus` to re-attach. */
export interface LeagueRefreshStatus {
  leagueId: string;
  state: LeagueRefreshState;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  /** what the refresh is doing right now; set only while `state` is `running` */
  progress: string | null;
  snapshot: LeagueSnapshot | null;
}

export interface LeagueSnapshot {
  leagueId: string;
  fetchedAt: string | null;
  playerCount: number;
  /** ranking methods already scored to disk for this snapshot */
  rankedMethods: string[];
}

export interface LeagueTeam {
  id: string;
  name: string;
  parentTeamId: string | null;
  /** playing level of this club in the snapshot (MLB, AAA, AA, A, A-, R); null
   *  for an org row or a club with no ranked players */
  level: string | null;
}

export interface LeagueFreshness {
  snapshot: LeagueSnapshot | null;
  /** the sim advanced past the snapshot's date — the page should refresh */
  stale: boolean;
  /** the league's in-game date was actually fetched this call */
  checked: boolean;
  leagueDate: string | null;
}

/** How `leagueSnapshotPlayers` narrows the pool. `LEAGUE` ignores `groupId`. */
export type LeagueGroupBy = 'LEAGUE' | 'ORG' | 'TEAM';

/** The two ranking methods the league view offers (no `draft_class`). */
export const LEAGUE_RANKING_METHODS = ['overall', 'potential'] as const;
export type LeagueRankingMethod = (typeof LEAGUE_RANKING_METHODS)[number];

export interface RankedPlayer {
  rank: number;
  id: string;
  name: string;
  position: string;
  /** the model's best-fit fielding position; null for pitchers */
  bestPosition: string | null;
  type: PlayerType;
  age: number | null;
  batHand: string | null;
  throwHand: string | null;
  /** live-league snapshot only: parent org name, roster team name, level */
  org: string | null;
  team: string | null;
  level: string | null;
  /** live-league snapshot only: link to the player's StatsPlus page */
  statsPlusUrl: string | null;
  modelScore: number | null;
  inGameOverall: number | null;
  inGamePotential: number | null;
  demand: string | null;
  drafted: boolean;
  draftedTeam: string | null;
  draftedPick: number | null;
  draftedRound: number | null;
  draftedRoundPick: number | null;
  positionPlayerScore: number | null;
  pitcherScore: number | null;
  battingScoreComponent: number | null;
  fieldingScoreComponent: number | null;
  starterComponent: number | null;
  relieverComponent: number | null;
  runningScoreComponent: number | null;
  rawOverallScore: number | null;
  components: Record<string, unknown> | null;
  ratings: PlayerRatings | null;
}

export interface PitchRating {
  name: string;
  potential: number | null;
  current: number | null;
}

export interface PlayerRatings {
  batHand: string | null;
  throwHand: string | null;
  injuryProne: string | null;
  workEthic: string | null;
  intelligence: string | null;
  leadership: string | null;
  scoutingAccuracy: string | null;
  batting: Record<string, number | null>;
  fielding: Record<string, number | null>;
  pitching: {
    stuff: number | null;
    movement: number | null;
    control: number | null;
    stuffCur: number | null;
    movementCur: number | null;
    controlCur: number | null;
    stamina: number | null;
    velocity: string | null;
    groundballType: string | null;
    armSlot: string | null;
    pitches: PitchRating[];
  };
}

export type PlayerType = 'Hitter' | 'Pitcher' | 'Two-way';

/** Alias kept for call sites; `type` is now supplied by the backend. */
export type RankedPlayerRow = RankedPlayer;

/** One filter/sort/page slice of a class, matching `RankedPlayerPage` in the schema. */
export interface RankedPlayerPage {
  rows: RankedPlayer[];
  totalRecords: number;
}

/** The three column presets the class table can show. */
export type ClassView = 'modeled' | 'batting' | 'pitching';

/** One greater-than / less-than bound on a sortable column. `label` is for the
 *  UI only; `field` + `min` + `max` are what the backend filter consumes. */
export interface NumericFilter {
  field: string;
  label: string;
  min: number | null;
  max: number | null;
}

/** Everything the table UI feeds back to the container to identify what to
 *  fetch — and round-trips through the URL so a filtered view is reloadable /
 *  shareable. Doesn't carry pagination state: the table loads infinitely, in
 *  fixed-size batches (see `RANKED_PAGE_SIZE`), driven by the container. */
export interface RankedQuery {
  view: ClassView;
  search: string;
  positions: string[];
  bestPositions: string[];
  batHands: string[];
  throwHands: string[];
  teams: string[];
  /** live-league view only: keep only these playing levels (MLB, AAA, …) */
  levels: string[];
  hideDrafted: boolean;
  numericFilters: NumericFilter[];
  sortField: string | null;
  sortOrder: 1 | -1;
}

/** Infinite-scroll batch size: how many rows a single fetch pulls. */
export const RANKED_PAGE_SIZE = 50;

export interface DraftedRefreshResult {
  draftedCount: number;
  matchedById: number;
  matchedByName: number;
  unmatched: number;
}

export const RANKING_METHODS = ['draft_class', 'potential', 'overall'] as const;
export type RankingMethod = (typeof RANKING_METHODS)[number];
