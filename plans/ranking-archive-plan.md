# Plan: Work that waits on the ratings archive

Engine v2 is fit on one season of ratings: the 2042 archive, the live
in-game 2042-12-11 snapshot. Several parts of it are judgment, or on the
legacy tables, only because one season can't measure them. This plan lists
that work and the order to do it in as archived seasons arrive. The design
is in `plans/ranking-architecture-plan.md` and the build steps are in
`plans/ranking-v2-technical-plan.md`. This doc only tracks what the archive
unlocks.

## What the archive gives, and when

The archive keeps one snapshot per league per season, the first one built on
or after in-game April 8. It's kept at
`league_snapshots/<league>/archive/<season>.csv.gz`, with a `.json` file
recording the in-game date. The fits read every archived season that has
BABIP (`ranking.fitting.datasets.season_snapshots`).

| When (in-game)                         | New data                                                  | What it unlocks                                                                                                                  |
| -------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **April 2043 archive**                 | a second ratings snapshot, the first taken at season start | ratings-only checks: split predictors across seasons, a first look at offseason rating growth, eval outcomes one season on |
| **End of the 2043 season** + stats pull | 2043 batting / pitching / fielding lines                  | the talent refits with a real season holdout, value calibration against WAR, the hypotheses re-check                            |
| **April 2044 archive**                 | a third snapshot: one full year of growth per player      | the development layer: rating growth by age, age and readiness fit together, makeup re-checked on growth                         |

A refit right after the April 2043 archive adds **no** talent rows. The fits
pair a snapshot with that season's stats (`datasets._join`), and the 2043
lines don't exist yet. Partial-season lines would be too thin to use. Don't
refit the talent models until the 2043 season is over and pulled.

## Before anything: confirm the archive exists

- The app only archives when it wakes up (`collect_season_snapshots` on
  startup) or on a league refresh. There's no scheduled wake-up (your call,
  2026-11-05). Once the game is past April 8, 2043, open the app or refresh
  the league, then check that `archive/2043.csv.gz` and `2043.json` exist on
  the Fly volume, with a `league_date` in April.
- Check that its header has everything the fits read: BABIP, HRA, PBABIP,
  their potential columns, the vL / vR split columns, `Slot`, `T` / `B`,
  and the pitch grades (the first 2042 archive was taken before BABIP was
  mapped and had to be replaced).
- Copy it down to `fly_data/` with `fly ssh sftp`.
- Once the 2043 season is over: `python league_stats.py yfmlb 2043`.

## 1. At the April 2043 archive (ratings only)

- **Split predictors, tested across seasons.** Fit on 2042 and test on 2043
  for the pitcher split predictor (`split_gap`, cross-validated R² 0.41 on
  2042 alone) and the hitters' expected splits (`expected_splits`). A
  pitcher's slot and pitch mix barely change between seasons, so this mostly
  tests whether the fit holds on a different set of ratings. Refit on both
  seasons if it holds.
- **The matchup tilt's scale.** `FULL_TILT_SPLIT` (20 runs index) is the
  95th percentile of 2042 splits. Check it's stable on 2043.
- **First look at rating growth.** Pair each player's December 2042 and
  April 2043 ratings. That's an offseason plus spring training, not a full
  year, so it's a sanity check of the direction only: do younger players,
  and players with high work ethic and intelligence, grow more? Don't fit
  factors on it.
- **Draft eval, one season on.** `eval_rankings.py` judges past classes on
  the latest snapshot. With 2043 it can judge them on both snapshots. Check
  that the v2 board holds up on the newer outcome, especially the 2041–42
  classes, whose outcomes are still mostly potential.

## 2. At the end of the 2043 season (ratings + stats)

### Talent refits

- **Hitters, pitchers, fielding, running** (`ranking.fitting.hitter_talent`,
  `pitcher_talent`, `fielding_talent`, `running_talent`, each with
  `--data-dir fly_data`):
  - **The first real holdout:** fit on 2042 and test on 2043. Folds are
    grouped by player today, because a season split isn't possible yet. Then
    fit on both seasons for the artifact.
  - **Start-of-season ratings:** 2043's are April ratings matched to the
    season they lead into. 2042's were taken in December, after the season
    they're paired with. Compare the two seasons' fits. If December ratings
    turn out to have been flattered by their own season, weight 2043 more.
  - Refit the pitcher role shift's margin only if the role-reference exports
    are redone. They're SD-org exports, not archive data
    (`fly_data/role_reference/`).
- **PBABIP.** It's kept at a third of its fitted effect because one season's
  BABIP spread is about what luck gives (2026-11-08). See whether two
  seasons can size it.
- **Fielding** is the part you're most skeptical of. A second season of
  `zr` / `framing` tests whether one line (−11.5 + 0.362 × grid) still
  prices every position, and whether the position floors still hold.
- **Points bridges and platoon mixes** refit with the artifacts. The mixes
  come from 2030–2042 stats and won't move much.

### Hypotheses

- **Build `eval_rankings.py --hypotheses`** (planned, never built). It
  re-checks each hypothesis against the stats: matching players' actual
  wRC+ / ERA / WAR against their peers. It reports whether the data supports
  each one and whether the fitted model agrees.
- **Re-check with two seasons:**
  - the four Power rules: the 40 / 30 floors, power without contact, and
    archetype balance;
  - pitcher rule 5 (a 30 in a pitching rating is emergency-only);
  - H1–H3.
- A hypothesis becomes a rule only if the data backs it and you agree.

### Value calibration

- **Predicted vs actual WAR by decile** (planned "once the value layer
  exists"): score the April 2043 ratings, then compare with each player's
  2043 StatsPlus WAR, rescaled to a full-time role. This is the first
  out-of-sample check of the whole talent → WAR chain.
- **The leverage map** (`value_v1`) refits on 2043 bullpens.
- **The innings-per-start curve by stamina** refits on 2043 starts.
- **Judgment calls the stats can inform but don't decide:** full leverage
  for relievers (1.0), the two-way share ramp, and the matchup tilt. Report
  what 2043 says about each. They stay your call.

## 3. At the April 2044 archive (a full year of growth)

This is the development layer as the architecture plan meant it: fit on
rating growth, not only on end states.

- **Rating growth by age, potential, work ethic and intelligence.** Pair
  each player's April 2043 and April 2044 ratings. That's one full
  development year per player, at every level and age.
- **Age and readiness, fit together.** Today age is on your legacy table,
  balanced by the legacy draft-day current-ratings modifiers (2026-11-08).
  That's because the two outcomes disagree: value now says older draftees
  realize less (×0.6 at 22 vs 18), while career WAR says the opposite (×2.5,
  since college picks reach MLB sooner). Growth curves measure the runway
  directly. Fit age and current-ratings readiness together, and replace
  `AgeModifier` and the draft current-ratings modifiers if the fit beats them
  on the draft eval.
- **Makeup and durability factors, re-checked on growth.** The factors in
  `ranking/development.py` are the conservative end of a fit on end states
  (2033–36 classes), tapered by potential WAR. Check that growth agrees on
  their direction, and on the taper (makeup matters about half as much at 4+
  WAR). Keep the conservative-end, rank-dependent shape you asked for. Any
  change to the numbers is your call.
- **Outcome distributions (P90).** These were dropped on 2026-11-08 because
  P90 just followed the board value and flattened at 3.6 WAR, with only ~90
  past draftees that high. Revisit them only if growth data gives top
  prospects real spread.
- **Still judgment:** scouting accuracy (nearly every draftee here is
  "Very High") and leadership (org value beyond MLB outcomes).

## Each time a season lands

1. Confirm the archive and its columns, and copy it to `fly_data/`.
2. Pull the season's stats once it's over.
3. Refit in dependency order: hitter → pitcher → fielding → running →
   value. Then run the development evidence script
   (`ranking.fitting.development`) on the new outcomes.
4. Run `eval_rankings.py --engine v2 --against <the last commit>` on current
   and on every class, and read the rules suite and the hypotheses.
5. Review with you before anything ships. A refit changes
   `ranking.manifest.model_version`, so stored runs rescore themselves on
   their next read after the deploy, and the goldens need regenerating.
