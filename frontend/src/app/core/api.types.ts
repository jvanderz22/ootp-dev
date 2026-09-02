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
  age: number | null;
  modelScore: number | null;
  inGamePotential: number | null;
  demand: string | null;
  drafted: boolean;
  positionPlayerScore: number | null;
  pitcherScore: number | null;
  battingScoreComponent: number | null;
  fieldingScoreComponent: number | null;
  starterComponent: number | null;
  relieverComponent: number | null;
  rawOverallScore: number | null;
  components: Record<string, unknown> | null;
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
