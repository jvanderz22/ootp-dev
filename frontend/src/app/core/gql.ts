import { gql } from '@apollo/client';

const PLAYER_FIELDS = gql`
  fragment PlayerFields on RankedPlayer {
    rank
    id
    name
    position
    type
    age
    batHand
    throwHand
    modelScore
    inGameOverall
    inGamePotential
    demand
    drafted
    positionPlayerScore
    pitcherScore
    battingScoreComponent
    fieldingScoreComponent
    starterComponent
    relieverComponent
    runningScoreComponent
    rawOverallScore
    components
    ratings
  }
`;

const CLASS_FIELDS = gql`
  fragment ClassFields on DraftClass {
    name
    rankingMethod
    playerCount
    hasCustomOrder
    lastProcessed
    draftedCount
  }
`;

export const DRAFT_CLASSES = gql`
  ${CLASS_FIELDS}
  query DraftClasses {
    draftClasses {
      ...ClassFields
    }
  }
`;

/** Initial class load: metadata + position facet + first page of players. */
export const CLASS_DETAIL = gql`
  ${CLASS_FIELDS}
  ${PLAYER_FIELDS}
  query ClassDetail(
    $name: String!
    $filter: RankedPlayerFilter
    $sort: RankedPlayerSort
    $page: Int
    $pageSize: Int
  ) {
    draftClass(name: $name) {
      ...ClassFields
    }
    classPositions(name: $name)
    rankedPlayers(
      name: $name
      filter: $filter
      sort: $sort
      page: $page
      pageSize: $pageSize
    ) {
      totalRecords
      rows {
        ...PlayerFields
      }
    }
  }
`;

/** Subsequent filter/sort/page fetches — just the player slice. */
export const RANKED_PAGE = gql`
  ${PLAYER_FIELDS}
  query RankedPage(
    $name: String!
    $filter: RankedPlayerFilter
    $sort: RankedPlayerSort
    $page: Int
    $pageSize: Int
  ) {
    rankedPlayers(
      name: $name
      filter: $filter
      sort: $sort
      page: $page
      pageSize: $pageSize
    ) {
      totalRecords
      rows {
        ...PlayerFields
      }
    }
  }
`;

/** Full ordered list, slim fields — backs reorder mode. */
export const REORDER_PLAYERS = gql`
  query ReorderPlayers($name: String!) {
    rankedPlayers(name: $name, allRows: true) {
      rows {
        id
        name
        position
        age
        modelScore
        drafted
      }
    }
  }
`;

export const STATSPLUS_SETTINGS = gql`
  query StatsPlusSettings {
    statsPlusSettings {
      leagueUrl
      defaultLid
      hasSessionid
      hasCsrftoken
    }
  }
`;

export const UPLOAD_DRAFT_CLASS = gql`
  ${CLASS_FIELDS}
  mutation UploadDraftClass($name: String!, $rankingMethod: String!, $file: Upload!) {
    uploadDraftClass(name: $name, rankingMethod: $rankingMethod, file: $file) {
      ...ClassFields
    }
  }
`;

export const SET_RANKING_METHOD = gql`
  ${CLASS_FIELDS}
  mutation SetRankingMethod($name: String!, $rankingMethod: String!) {
    setRankingMethod(name: $name, rankingMethod: $rankingMethod) {
      ...ClassFields
    }
  }
`;

export const REPROCESS_DRAFT_CLASS = gql`
  ${CLASS_FIELDS}
  mutation ReprocessDraftClass($name: String!) {
    reprocessDraftClass(name: $name) {
      ...ClassFields
    }
  }
`;

export const DELETE_DRAFT_CLASS = gql`
  mutation DeleteDraftClass($name: String!) {
    deleteDraftClass(name: $name)
  }
`;

export const SAVE_CUSTOM_ORDER = gql`
  ${CLASS_FIELDS}
  mutation SaveCustomOrder($name: String!, $order: [ID!]!) {
    saveCustomOrder(name: $name, order: $order) {
      ...ClassFields
    }
  }
`;

export const SET_PLAYER_RANK = gql`
  ${CLASS_FIELDS}
  mutation SetPlayerRank($name: String!, $id: ID!, $rank: Int!) {
    setPlayerRank(name: $name, id: $id, rank: $rank) {
      ...ClassFields
    }
  }
`;

export const CLEAR_CUSTOM_ORDER = gql`
  ${CLASS_FIELDS}
  mutation ClearCustomOrder($name: String!) {
    clearCustomOrder(name: $name) {
      ...ClassFields
    }
  }
`;

export const REFRESH_DRAFTED = gql`
  mutation RefreshDrafted($name: String!) {
    refreshDraftedFromStatsPlus(name: $name) {
      draftedCount
      matchedById
      matchedByName
      unmatched
    }
  }
`;

export const UPDATE_SETTINGS = gql`
  mutation UpdateStatsPlusSettings(
    $leagueUrl: String
    $sessionid: String
    $csrftoken: String
    $defaultLid: Int
  ) {
    updateStatsPlusSettings(
      leagueUrl: $leagueUrl
      sessionid: $sessionid
      csrftoken: $csrftoken
      defaultLid: $defaultLid
    ) {
      leagueUrl
      defaultLid
      hasSessionid
      hasCsrftoken
    }
  }
`;
