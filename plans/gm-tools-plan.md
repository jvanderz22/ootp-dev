# Plan: GM tools — contracts, roster, and a to-do list per file

Three features that turn the rankings into decisions for your own org:

1. **Long-term value and contracts:** what a player is worth over the
   years of a deal, and what deal to offer him.
2. **Roster optimizer:** the best 26-man roster from your org, given who's
   hurt.
3. **New-file to-do list:** after each sim file, a short ranked list of
   moves: lineup changes, call-ups, DFAs, waiver claims.

They share a foundation (step 0). After that, the order I'd recommend is
2 → 3 → 1. The optimizer mostly reuses what's built. The to-do list is
mostly the optimizer's output compared with your actual roster. Contracts
need two new models (multi-year projection and a market price) and are
the largest piece.

Status: exploration. No code yet. Unknowns are at the end.

## What we already have

- **Next-season WAR on current ratings** (v2 `overall` profile): talent →
  value, platoon splits, pitcher matchups, and per-spot replacement
  (`ranking/value.py` `Replacement`, `replacement_v1.json`).
- **The spot model:** 7 full-time bats with bats 8–12 tapered, 5 SP, and
  8 bullpen spots by leverage. Prices come from an assignment LP's shadow
  prices. Your 26-man roster is the same problem, solved for one team
  instead of the league.
- **Potential WAR and development factors:** the ceiling, makeup, and
  durability (`ranking/development.py`), plus prospect odds (in progress).
- **StatsPlus plumbing** (`statsplus_api.py`): ratings, players, teams,
  lgdata, and season stats (`fetch_player_stats`, overall / vs L / vs R,
  with `war`).
- **Snapshots:** `players.csv` plus `players.prev.csv`, so we already keep
  the previous file to diff against. There's also the season archive.
- **Rule 5 eligibility** derived from service time (`_is_rule5_eligible`).

## What StatsPlus gives us (checked live on yfmlb, 2026-11-11)

**`/api/players/`** (60 columns). The roster-status fields, none stored in
the snapshot today:

| Need | Fields |
|---|---|
| Injury | `injury_is_injured`, `injury_left` (days), `injury_dl_left`, `is_on_dl`, `is_on_dl60`, `dl_days_this_year` |
| 40-man | `is_on_secondary` |
| Waivers / DFA | `is_on_waivers`, `days_on_waivers_left`, `designated_for_assignment` |
| Service / control | `mlb_service_days`, `mlb_service_days_this_year`, `mlb_service_years`, `has_received_arbitration`, `pro_service_*`, `secondary_service_*` |
| Where he is | `Team ID`, `Parent Team ID`, `Level`, `Organization ID`, `free_agent` |

Live counts: 246 injured (20 on the IL, 18 on the 60-day), 8 on waivers,
43 DFA'd, 1,298 on 40-man rosters.

**`/api/contract/`** (13,840 rows): `salary0..salary14` (this season
onward), `years`, `current_year`, `is_major`, `no_trade`, team / player /
vesting options with buyouts, and PA/IP and award bonuses.
**`/api/contractextension/`** has the same schema but different rows:
extensions already signed that start in a later season.

Shape of the major-league contracts: the minimum salary is $900K, which is
also the median. p90 is $10.3M and the max is $60M. `years` is 0 on 2,948 of
3,959 rows, probably pre-arb and auto-renewed deals; to decode. There are
40 team options and 21 player options.

**Not in the API:**
- **Minor-league options remaining.** This is the biggest gap for the
  optimizer and the to-do list: optioning a player down is free only if he
  has options left.
- **Asking prices.** There's no FA or extension demand (the same gap as
  `DEM` on the draft side).
- **League financial rules:** arbitration scale, minimum salary schedule,
  roster limits (26 active, max pitchers), and the luxury tax, if any.
- **Your actual depth chart and lineup.** We can see who is on the 26-man
  roster, but not the batting order or roles.

## Step 0: Shared foundation

1. **"My org" per league:** a setting in `leagues.json` and Settings that
   names your org id. Every feature below is scoped to it.
2. **Roster-status columns in the snapshot:** add the table above to
   `SNAPSHOT_META_FIELDS`. They're bookkeeping, so the rankers ignore them.
   An `available_in_days` (0 if healthy) is derived from the injury fields.
3. **Contracts per refresh:** pull both contract endpoints into
   `league_snapshots/<league>/contracts.csv` (and keep a `.prev`). Join on
   `player_id`, and decode `years` / `current_year` / `season_year`.
4. **Current-season stats per refresh:** batting and pitching for the
   season to date, MLB and the minors (each `lid`). These are context for
   the to-do list ("hitting .180"), not inputs to value.
5. **Gaps:** an options-remaining override you set per player (default:
   unknown, flagged), plus a small league-rules config (26 active, 13
   pitcher max, 40-man, minimum salary, arbitration years).

## Feature 2: Roster optimizer

**Question:** given everyone in my org who is available, what's the best
26-man roster, and how should it be used?

**Model.** The league-replacement LP, run for one team:

- **Players:** your org's MLB roster and minor leaguers, minus anyone
  injured past the planning window.
- **Spots:** the per-team spot list (7 regulars, tapered bench, 5 SP,
  8 bullpen spots by leverage), plus real-roster constraints the league
  model skips:
  - one player per fielding position in each lineup, valued by his grid at
    that position (we already score every position);
  - a backup C, and enough infield and outfield coverage on the bench;
  - 26 active and the pitcher cap;
  - only 40-man players can be active, so a non-40-man call-up costs a
    40-man spot (a DFA or a 60-day IL move).
- **Platoons:** two lineups, vs RHP and vs LHP, from the split WAR we
  already compute. The bench is built partly for the short side.
- **Objective:** WAR from the spots filled. An integer program, small
  enough (about 200 org players) for `scipy.optimize.milp` or PuLP.

**Injuries.** `injury_left` gives each player a return date. The
optimizer runs for "today" and, as an option, a horizon such as the next
2 weeks. A player back in 5 days isn't replaced. A 60-day IL candidate
frees a 40-man spot.

**Output (the Roster page):**
- **Lineups:** vs RHP and vs LHP, with positions.
- **Pitching:** the rotation, then the bullpen ordered by leverage role
  (closer, setup, middle, long).
- **Bench and the next man up** at each position.
- **Moves:** what changes from today's roster to the optimal one (call
  up X, option Y, 60-day IL Z, DFA W), with the WAR gained by each.

**Ratings vs stats.** The model values players on ratings, and in OOTP
ratings drive results, so stats are mostly noise over a season. I'd rank
on ratings and show season stats next to each player. Your call (Q3).

## Feature 3: New-file to-do list

**Question:** a new file just ran. What should I do before the next one?

**Trigger:** the snapshot refresh, which already happens per file. The
list compares this snapshot with `players.prev.csv` and the previous
contracts file, and reruns the optimizer.

**Checks, roughly in priority order:**

| Item | Rule | Shows |
|---|---|---|
| Injury | A player on the 26-man roster is newly injured | Return date; the optimizer's replacement and the move it needs |
| Returning | An injured player is now healthy, or his IL stint is ending | Who goes down to make room |
| Roster | The active roster differs from the optimal one by more than a WAR threshold | Each swap with its WAR |
| Lineup | The optimal lineup or rotation changed since the last file (ratings moved, injury, platoon) | Who in, who out |
| Call-up | A minor leaguer's WAR beats the worst active player at his spot | WAR gain, 40-man cost, service-time note (see below) |
| DFA | A 40-man player is below replacement and is blocking someone better | WAR, salary still owed, options left |
| Waiver claim | Another org's player on waivers or DFA'd beats your worst 40-man player at his spot | WAR gain, contract, days left to claim |
| Free agent | An unsigned FA beats your worst active player at a spot | WAR gain, likely cost |
| Ratings movers | A big rating change in your org since the last file | Delta; promote a breakout, watch a decline |
| Deadlines | Rule 5 protection, option decisions, arbitration, expiring deals | Date and the decision |

**Service time.** Calling up a prospect starts his service clock: 172 days
is a year, and the dates set arbitration and free agency. The call-up item
shows days to the next threshold, e.g. "Holding him 12 more days saves a
year of control". This ties to Feature 1, where a year of control is worth
real surplus.

**What it can't see.** Batting order and bullpen roles are set in the
game, and the API doesn't expose them. The lineup items compare with the
last *recommended* lineup, not the one actually in use. Usage from
season-to-date stats (GS, PA share since the last file) can roughly
detect "he isn't playing". Optional.

**Output:** a To-do page per league for your org. Each item is one line,
the action and the WAR, sorted by WAR gained, deadlines pinned on top.
Labels stay terse and in baseball terms ("Call up", "DFA", "Claim",
"+0.6 WAR", "3 days left").

## Feature 1: Long-term value and contracts

**Question:** what is this player worth over the years of a contract, and
what deal should I offer?

### 1a. A year-by-year WAR projection

Today we have one season on current ratings and a ceiling on potential.
A contract needs WAR for each season out to ~10 years.

- **Young players:** move from current WAR toward the ceiling on the
  development path. Prospect odds already fit how much of the ceiling is
  reached and how fast by age; we'd extend that to a yearly path.
- **Prime and decline:** an aging curve fit on our own data: the season
  archive (ratings by season, same player) and StatsPlus season WAR
  (`league_stats/`, 2030 on), with the delta method by age, separately
  for hitters, SP, and RP. OOTP's aging is its own, so we fit it rather
  than borrow MLB's.
- **Durability:** expected games lost from `Prone` and IL history
  (`dl_days_this_year`, past seasons), widening with age.
- **Uncertainty:** a band per year (P10/P50/P90), wider further out.

### 1b. A market price for WAR

- **$/WAR:** fit on the league's own contracts. Free agents and
  extensions with 6+ years of service give salary against projected WAR
  at signing. That gives the market rate, and whether it's linear or
  steeper for stars.
- **Control years:** pre-arb (minimum salary) and arbitration years (a
  fitted share of market value by arbitration year) come from service
  time. This is what makes a young player's surplus large.
- **Inflation and discounting:** a per-year discount rate (a setting) and
  the league's salary trend, if the contract history shows one.

### 1c. Contract value and a recommendation

- **Surplus value:** for each year, (projected WAR above replacement ×
  $/WAR) − salary, discounted and summed. Options are valued as choices:
  a team option is exercised only if he's worth more than its salary; a
  player option only if he's worth less.
- **For a current contract:** surplus by year, total surplus, and the
  year it turns negative. That flags sell-high and dead money.
- **Extension or FA offer:** for each length, the breakeven AAV and the
  value at your chosen risk (P50, or more conservative). The
  recommendation is the length and AAV that maximize surplus at that risk,
  with an "ideal deal" line ("4 yr / $11.5M or less; years 5+ lose
  value"). Since the asking price isn't in the API, you enter the ask from
  the game and the tool says whether it beats breakeven.
- **Buying out control:** for a pre-arb or arbitration player, compare
  the cost of an extension that buys out arbitration and FA years with
  going year to year.

**Output:** a Contract section on the player card (surplus by year, the
recommended deal), and an org Payroll view (commitments and surplus by
season, expiring deals, arbitration cases).

## Phases

| Step | Work | Depends on |
|---|---|---|
| 0 | My org setting; roster-status columns; contracts + season stats per refresh; options override; league rules config | — |
| 2a | Team optimizer (positions, 26 / 40-man, pitcher cap), injuries as availability | 0 |
| 2b | vs RHP / vs LHP lineups, roles, moves list; Roster page | 2a |
| 3a | Snapshot diff + to-do rules (injury, returning, roster, call-up, DFA) | 2b |
| 3b | Waivers, FA, ratings movers, deadlines; To-do page | 3a |
| 1a | Aging curve + yearly projection with bands | archive, stats history |
| 1b | $/WAR + control-year (pre-arb / arb) fits from contracts | 0, 1a |
| 1c | Contract surplus, option logic, deal recommendation; card section + Payroll view | 1a, 1b |
| 3c | Service-time and contract items in the to-do list | 1c |

## Unknowns

1. **Order:** 2 → 3 → 1 (quick wins first), or contracts first since you
   listed it first?
2. **Options remaining:** with no API field, is a per-player override you
   maintain acceptable, or is there somewhere in the game export (an OOTP
   dump, the S+ player page) we could read it from?
3. **Ratings vs stats** for "underperforming": rank purely on ratings
   with stats as context, or let a bad stretch count against a player?
4. **League rules:** roster sizes, pitcher cap, arbitration scale, and
   minimum salary schedule for yfmlb and WBF. Are they the OOTP defaults?
5. **Winning now vs later:** should the optimizer and the to-do list weigh
   service-time savings against this season's WAR? A contender and a
   rebuilder would answer differently. A single setting might be enough.
6. **Delivery:** in-app pages only, or also a notification (e.g. a
   summary after each refresh)?
7. **Discount rate and risk** for contracts: one default, or a setting
   on the page?
