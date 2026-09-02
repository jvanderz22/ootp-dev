export interface DraftClass {
  name: string;
  rankingMethod: string;
  playerCount: number;
  hasCustomOrder: boolean;
  lastProcessed: string | null;
  draftedCount: number;
}

export interface RankedPlayer {
  rank: number;
  id: string;
  name: string;
  position: string;
  type: PlayerType;
  age: number | null;
  batHand: string | null;
  throwHand: string | null;
  modelScore: number | null;
  inGameOverall: number | null;
  inGamePotential: number | null;
  demand: string | null;
  drafted: boolean;
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

/** Everything the table UI feeds back to the container to fetch a page. */
export interface RankedQuery {
  search: string;
  positions: string[];
  hideDrafted: boolean;
  sortField: string | null;
  sortOrder: 1 | -1;
  page: number;
  pageSize: number;
}

export interface StatsPlusSettings {
  leagueUrl: string | null;
  defaultLid: number | null;
  hasSessionid: boolean;
  hasCsrftoken: boolean;
}

export interface DraftedRefreshResult {
  draftedCount: number;
  matchedById: number;
  matchedByName: number;
  unmatched: number;
}

export const RANKING_METHODS = ['draft_class', 'potential', 'overall'] as const;
export type RankingMethod = (typeof RANKING_METHODS)[number];
