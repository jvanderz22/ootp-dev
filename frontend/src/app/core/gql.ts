import { gql } from '@apollo/client';

const PLAYER_FIELDS = gql`
  fragment PlayerFields on RankedPlayer {
    rank
    id
    name
    position
    bestPosition
    type
    age
    batHand
    throwHand
    org
    team
    level
    statsPlusUrl
    modelScore
    inGameOverall
    inGamePotential
    demand
    drafted
    draftedTeam
    draftedPick
    draftedRound
    draftedRoundPick
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
    leagueId
    leagueName
  }
`;

const LEAGUE_FIELDS = gql`
  fragment LeagueFields on League {
    id
    name
    leagueUrl
    defaultLid
    classNames
    updatedAt
    hasSessionid
    hasCsrftoken
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
    draftTeams(name: $name)
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

export const LEAGUES = gql`
  ${LEAGUE_FIELDS}
  query Leagues {
    leagues {
      ...LeagueFields
    }
  }
`;

const LEAGUE_SNAPSHOT_FIELDS = gql`
  fragment LeagueSnapshotFields on LeagueSnapshot {
    leagueId
    fetchedAt
    playerCount
    rankedMethods
  }
`;

const LEAGUE_TEAM_FIELDS = gql`
  fragment LeagueTeamFields on LeagueTeam {
    id
    name
    parentTeamId
    level
  }
`;

export const LEAGUE_SNAPSHOT = gql`
  ${LEAGUE_SNAPSHOT_FIELDS}
  query LeagueSnapshot($leagueId: ID!) {
    leagueSnapshot(leagueId: $leagueId) {
      ...LeagueSnapshotFields
    }
  }
`;

/** Initial league-view load: snapshot meta + org/team facets + first page. */
export const LEAGUE_VIEW_DETAIL = gql`
  ${LEAGUE_SNAPSHOT_FIELDS}
  ${LEAGUE_TEAM_FIELDS}
  ${PLAYER_FIELDS}
  query LeagueViewDetail(
    $leagueId: ID!
    $method: String!
    $groupBy: LeagueGroupBy!
    $groupId: ID
    $filter: RankedPlayerFilter
    $sort: RankedPlayerSort
    $page: Int
    $pageSize: Int
  ) {
    leagueSnapshot(leagueId: $leagueId) {
      ...LeagueSnapshotFields
    }
    leagueOrgs(leagueId: $leagueId) {
      ...LeagueTeamFields
    }
    leagueTeams(leagueId: $leagueId) {
      ...LeagueTeamFields
    }
    leagueLevels(leagueId: $leagueId)
    leagueSnapshotPlayers(
      leagueId: $leagueId
      method: $method
      groupBy: $groupBy
      groupId: $groupId
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

/** Subsequent filter/sort/page fetches for the league view — just the slice. */
export const LEAGUE_SNAPSHOT_PLAYERS = gql`
  ${PLAYER_FIELDS}
  query LeagueSnapshotPlayers(
    $leagueId: ID!
    $method: String!
    $groupBy: LeagueGroupBy!
    $groupId: ID
    $filter: RankedPlayerFilter
    $sort: RankedPlayerSort
    $page: Int
    $pageSize: Int
  ) {
    leagueSnapshotPlayers(
      leagueId: $leagueId
      method: $method
      groupBy: $groupBy
      groupId: $groupId
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

export const LEAGUE_ORG_RANKINGS = gql`
  ${PLAYER_FIELDS}
  query LeagueOrgRankings($leagueId: ID!) {
    leagueOrgRankings(leagueId: $leagueId) {
      orgId
      orgName
      orgScore
      prospectCount
      top10
      top50
      top100
      top250
      top500
      topProspects {
        ...PlayerFields
      }
    }
  }
`;

const LEAGUE_REFRESH_STATUS_FIELDS = gql`
  ${LEAGUE_SNAPSHOT_FIELDS}
  fragment LeagueRefreshStatusFields on LeagueRefreshStatus {
    leagueId
    state
    startedAt
    finishedAt
    error
    progress
    snapshot {
      ...LeagueSnapshotFields
    }
  }
`;

export const REFRESH_LEAGUE_SNAPSHOT = gql`
  ${LEAGUE_REFRESH_STATUS_FIELDS}
  mutation RefreshLeagueSnapshot($leagueId: ID!) {
    refreshLeagueSnapshot(leagueId: $leagueId) {
      ...LeagueRefreshStatusFields
    }
  }
`;

export const LEAGUE_REFRESH_STATUS = gql`
  ${LEAGUE_REFRESH_STATUS_FIELDS}
  query LeagueRefreshStatus($leagueId: ID!) {
    leagueRefreshStatus(leagueId: $leagueId) {
      ...LeagueRefreshStatusFields
    }
  }
`;

export const CHECK_LEAGUE_SNAPSHOT_FRESHNESS = gql`
  ${LEAGUE_SNAPSHOT_FIELDS}
  mutation CheckLeagueSnapshotFreshness($leagueId: ID!) {
    checkLeagueSnapshotFreshness(leagueId: $leagueId) {
      snapshot {
        ...LeagueSnapshotFields
      }
      stale
      checked
      leagueDate
    }
  }
`;

export const CREATE_LEAGUE = gql`
  ${LEAGUE_FIELDS}
  mutation CreateLeague(
    $name: String!
    $leagueUrl: String
    $defaultLid: Int
    $classNames: [String!]
    $sessionid: String
    $csrftoken: String
  ) {
    createLeague(
      name: $name
      leagueUrl: $leagueUrl
      defaultLid: $defaultLid
      classNames: $classNames
      sessionid: $sessionid
      csrftoken: $csrftoken
    ) {
      ...LeagueFields
    }
  }
`;

export const UPDATE_LEAGUE = gql`
  ${LEAGUE_FIELDS}
  mutation UpdateLeague(
    $id: ID!
    $name: String
    $leagueUrl: String
    $defaultLid: Int
    $classNames: [String!]
    $sessionid: String
    $csrftoken: String
  ) {
    updateLeague(
      id: $id
      name: $name
      leagueUrl: $leagueUrl
      defaultLid: $defaultLid
      classNames: $classNames
      sessionid: $sessionid
      csrftoken: $csrftoken
    ) {
      ...LeagueFields
    }
  }
`;

export const DELETE_LEAGUE = gql`
  mutation DeleteLeague($id: ID!) {
    deleteLeague(id: $id)
  }
`;

export const SET_CLASS_LEAGUE = gql`
  ${CLASS_FIELDS}
  mutation SetClassLeague($name: String!, $leagueId: String) {
    setClassLeague(name: $name, leagueId: $leagueId) {
      ...ClassFields
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

