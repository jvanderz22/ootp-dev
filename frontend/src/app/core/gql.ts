import { gql } from '@apollo/client';

const PLAYER_FIELDS = gql`
  fragment PlayerFields on RankedPlayer {
    rank
    id
    name
    position
    age
    modelScore
    inGamePotential
    demand
    drafted
    positionPlayerScore
    pitcherScore
    battingScoreComponent
    fieldingScoreComponent
    starterComponent
    relieverComponent
    rawOverallScore
    components
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

export const RANKED_PLAYERS = gql`
  ${PLAYER_FIELDS}
  query RankedPlayers($name: String!) {
    draftClass(name: $name) {
      ...ClassFields
    }
    rankedPlayers(name: $name) {
      ...PlayerFields
    }
  }
  ${CLASS_FIELDS}
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
  ${PLAYER_FIELDS}
  mutation SaveCustomOrder($name: String!, $order: [ID!]!) {
    saveCustomOrder(name: $name, order: $order) {
      ...PlayerFields
    }
  }
`;

export const CLEAR_CUSTOM_ORDER = gql`
  ${PLAYER_FIELDS}
  mutation ClearCustomOrder($name: String!) {
    clearCustomOrder(name: $name) {
      ...PlayerFields
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
