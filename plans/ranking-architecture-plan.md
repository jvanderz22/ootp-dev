# Plan: Ranking redesign

Replace the stack of hand-tuned multipliers with layered models in one unit
(WAR). Each layer answers one question with one stated method. The models are
fit from data, held to the general rules your grids encode. Every step's
contribution is recorded so a
ranking explains itself. It's built in parallel to the current code (engine `v2`
next to `legacy`) and judged by `eval_rankings.py` at every step.

## Decisions

| Date | Decision |
|---|---|
| 2026-11-04 | **Unit is WAR.** Every layer outputs WAR or a WAR distribution. |
| 2026-11-04 | **Ranking rule: expected value, with upside favored at equal EV** (see "Uncertainty and the ranking rule"). |
| 2026-11-05 | **The decision layer is your existing demand modifier, applied as the very last step.** It already handles signability the way you want. Every draft run records each player's value both before and after it. No slot amounts or budget modelling (this replaces the 2026-11-04 slot-based design). |
| 2026-11-05 | **The scoring models are fit from data instead of your handcrafted grids, but the same general rules apply.** The grids' rules (skill floors, power needs contact, all three pitching ratings need a floor, ...) become constraints and a rules suite every fitted model must pass. Details and the draft rule list are in `ranking-v2-technical-plan.md`. |
| 2026-11-04 | **Your tuned values are priors and may stay** (superseded for the attribute grids on 2026-11-05; still holds for the modifier tables). They push things the direction you want. Fitted layers start from them, and explicit judgment adjustments remain as their own visible step. |
| 2026-11-04 | **Build in parallel** (engine `v2`) and compare side by side before switching. |
| 2026-11-04 | **Current scoring is judged on performance stats**, with OVR as the fallback and the watchlist as a sanity check. **Draft scoring is judged on holding potential**: OVR from age 25, POT now before; gone from the league = bust; baseline = draft-day POT order. |
| 2026-11-04 | **Batting inputs are OOTP's base ratings** (BABIP, Avoid K, Gap, Power, Eye), not Contact. Contact ≈ ½ BABIP + ½ Avoid K. |
| 2026-11-04 | The signal inventory is a report only and never fails the suite. |
| 2026-11-07 | **The rules list is confirmed**, then **the four Power rules become hypotheses**: the Power 40 / 30 floors, "power without contact is much less valuable" and "archetypes land at similar values". The 2041–42 stats disagree with all four (see "Findings so far"). They're reported, not enforced, and re-checked as the archive grows. |
| 2026-11-07 | **Hitter talent is built from one rate per rating** (Avoid K → K%, Eye → BB%, Power → HR per contact, BABIP → hits on balls in play, Gap → extra bases per hit), chained into a PA and valued with linear weights fit to the league's runs. It's fit on every level at once with a level term, and committed as lookup tables. |
| 2026-11-08 | **Pitcher rule 5 (a 30 in Stuff, Movement or Control means emergency value) becomes a hypothesis.** The stats can barely test it, and the few cases weren't worthless. |
| 2026-11-08 | **Pitchers ship on the fitted model even though OVR disagrees.** The stats back it: held-out runs allowed and career MLB WAR. The OVR / POT outcome looks worse, so **the draft eval now also reports career MLB WAR** next to OVR / POT. |
| 2026-11-07 | **Until the value layer, fitted batting goes onto the legacy points scale by matching percentiles** over the league's hitters. Hitters keep their legacy points distribution, so phase 3 only reorders hitters among themselves; the hitter-vs-pitcher balance moves in phase 5 (WAR). |

## Why: what's wrong today

- **No unit.** Each role's model is fit to a hand-labeled 0–100 grid, so
  comparing roles needs more constants: RP ×0.82 (×0.72 for the draft), the
  0.73 / 0.22 / 0.05 batting / fielding / running weights, the two-way bonus
  with a 1.8 vs 2.2 threshold.
- **Effects are multipliers of multipliers, none of them fit to data.**
  `PersonalityModifier` = (WE × INT) raised to an age weight, then to a
  score weight. Age, injury and secondary personality are scaled by
  `RankGradiatedModel` curves of the model score. `DraftDemandModifier` has
  eight rank bands, each with its own piecewise demand curve. Nobody can say
  what the combined effect is.
- **The inputs overlap.** Stuff and Contact are composites, and their parts
  are counted again: pitch mix and velo on top of Stuff (fixed for current
  ratings in 0ce9a72), and Avoid K on top of Contact. Draft pitchers still
  have Stuff in five places (Aliff takes ×0.93 twice).
- **Signability is folded into the talent score.** The demand modifier does
  the job you want, but its output replaces the score. The pre-demand value
  only survives as a breakdown entry, so you can't easily see or rank by
  either one.
- **Settings live in five places.** `type ==` branches in scorers, ranker
  subclasses, constructor args, a `splits.py` copy (fixed), and
  `model_cache.warm()`.
- **Results are hard to follow.** Scorers return positional lists and the
  breakdown goes through a ContextVar side channel. There was dead code too
  (`apply_adjustment`, the `*DistanceFromOverallModifier`s, the one-player
  `calculate_*` paths), now deleted.

## Design

### Four layers

| Layer | Question it answers | Method | Replaces |
|---|---|---|---|
| **1. Talent** | ratings → expected rate stats (hitters: runs per PA from BABIP / Avoid K / Gap / Power / Eye; pitchers: runs per 9 innings from base components; fielding runs by position) | regression fit to StatsPlus season stats against ratings, weighted by PA / IP, monotone in each rating, held to the rules suite from your grids | the attribute grids, SP / RP pitch mix, velo, HR risk, hit profile, handedness |
| **2. Value** | rates → WAR for a season | expected playing time (role, stamina, injury proneness as expected games lost) + positional adjustment + replacement level | RP ×0.82, the 0.73 / 0.22 / 0.05 weights, injury multipliers, two-way bonus |
| **3. Development** | a prospect → distribution of peak WAR | fit on past classes + archived snapshots: rating growth given age, POT, work ethic, intelligence, scouting accuracy | age, personality, secondary personality, scouting accuracy, the draft overall / Stuff modifiers |
| **4. Decision** | draft board: how does signability change it? | your `DraftDemandModifier`, unchanged, run last on the pre-demand order (see "Draft decision layer") | nothing: it moves to the end |

Each **profile** (current, potential, draft) is one declared config: which
ratings to read (current / potential / vs L / vs R), which layers run, and
their settings. That's the `ScoringProfile` idea from the first draft of this
plan, now one config per profile.

### Fitting

- **Rules, not labels:** the models are fit from data. Your grids' general
  rules (skill floors, interactions, archetype balance) become constraints
  and a rules suite every fitted model must pass. Data is thin at first
  (about one clean season of ratings ↔ stats), so the rules do most of the
  shaping until the archive grows.
- **Judgment adjustments:** your tuned values that should stay as opinion,
  not just as priors, live in their own step with their own line in the
  record, so it's always visible how much of a score is fit and how much is
  judgment.
- **Monotone constraints** keep the obvious directions fixed: a higher
  rating never lowers a score.
- **Weighting:** by PA / IP for talent and by players for development.
- **Validation:** hold out a whole class or season at a time (never random
  rows), check calibration (predicted vs actual WAR by decile), and run
  `eval_rankings.py` against `legacy` for every change.
- **Inputs are base ratings only.** Composites (Contact, and probably
  Movement / Stuff) aren't inputs. Before building the pitcher talent model,
  run the same composition fit as Contact (Movement ~ HRA + PBABIP?), since
  StatsPlus exports `HRA` and `PBABIP*`.

### Uncertainty and the ranking rule

- **Projections are distributions:** P10 / P50 / P90 of peak WAR, from the
  development layer.
- **Outcomes are valued at v(WAR) = max(WAR, 0):** a bust gets released, so
  his cost stops at replacement while a star's value has no cap. **Ranking by
  E[v] is the default.** It's plain expected value, and it already favors a
  high-ceiling, low-floor player over a safer one with the same mean WAR.
- **Optional star-premium dial:** v = max(WAR, 0)^γ with γ ≥ 1 (default 1)
  adds more upside preference.
- **Board display:** expected value plus the P10–P90 range, so "same EV,
  different shape" is visible.

### Draft decision layer

- **The demand modifier stays, as the very last step.** It's applied after
  every other layer, to the order those layers produce. It reads rank, so
  it has to see the finished pre-demand ranking.
- **Before and after:** every draft run stores both the pre-demand value and
  rank and the post-demand value and rank, as first-class outputs (not just
  a breakdown entry), so the board can show either and the eval tool can
  compare either. The eval's draft metrics already use the pre-demand order.
- **Ledger line:** in WAR, the demand step's contribution is
  value × (factor − 1).
- **Not planned:** slot amounts, over-slot budget, and the chance a player is
  still there at your pick. Revisit only if the demand modifier stops doing
  the job.

### Step-by-step record (ledger) and run manifest

- **Ledger:** every layer appends lines (stage, label, inputs used, WAR
  contribution), and the lines sum exactly to the final value. For
  distributions, the ledger records the change in E[v]. The player card shows
  it as a waterfall: talent, value, development, judgment, decision.
- **Run manifest:** every run stores the engine version, a hash of the
  config, a hash of the training data, and the snapshot / class version it
  scored. Any ranking can be reproduced and two runs can be diffed.
- **Stage-by-stage comparison:** `eval_rankings.py` reads ledgers, so an
  engine comparison can say which stage moved a player.
- **Typed results:** each stage returns a typed result. There's no ContextVar.

## Data

What we have:
- **Live snapshots:** `fly_data/`, the `yfmlb` and `wbf` leagues.
- **Raw StatsPlus ratings export:** it has BABIP, HRA and PBABIP, but the
  snapshot doesn't map them yet.
- **Draft classes 2033–2042:** classes before 2039 are older game formats
  (only `VELO`, and so on). That's expected; the eval tool adapts them.
- **`drafted_picks`.**

To start collecting, because history doesn't backfill:
- **A ratings snapshot archive:** one per league per season, taken on or
  after in-game April 8 (see phase 1). Pairing ratings with stats and
  learning development both need ratings history, and StatsPlus only serves
  current ratings.
- **Season stats:** player batting / pitching / fielding by year with L/R
  splits. These are listed in the StatsPlus API (via StatsPlus-MCP's docs)
  but not tried yet. Check whether past seasons and WAR are included.
- **BABIP in OOTP draft exports** (current + potential). You're adding it to
  the export view going forward.

## Evaluation (`eval_rankings.py`, built)

- **current:** model vs in-game OVR for now (stats once pulled), with
  residuals by rating bucket for SP / RP / hitters.
- **draft:** past classes re-scored vs outcome; whole class, within the same
  draft POT, top-100 mean outcome; baseline = draft-day POT.
- **Watchlist:** McDonald, Perello, Aliff.
- **Comparisons:** `--against REF` (git worktree), `--against-engine NAME`
  (old vs new from one checkout), `--data-dir fly_data` (live data).
- **Engine reports (2b):** `--parity` (every field, two engines),
  `--explain <player>` (ledgers side by side) and `--signals` (which parts
  read each rating).
- **Draft on career MLB WAR (2026-11-08):** a second table judges the same
  pre-demand order on each draftee's MLB WAR (batting + pitching) through
  the last season on disk, 0 if he never got there.
- **To add:** the `potential` profile and calibration once stats exist.

## Findings so far

- **Low-Stuff starters were penalized for low Stuff 2–3 times** (pitch mix,
  velo). Fixed for current ratings in 0ce9a72, which also dropped velo from
  `OverallRanker`. On live data SP went 0.884 → 0.887 and RP 0.849 → 0.846
  (watch it). McDonald: 36.0 → 45.2, still the lowest OVR-65 SP.
- **Avoid K counts twice for hitters.** Gap vs OVR at equal Contact, live
  `yfmlb` MLB/AAA:

  | Contact | Avoid K ≤ 40 | Avoid K 45–50 | Avoid K 55+ |
  |---|---|---|---|
  | 40–45 | −6.8 | −1.4 | +2.3 |
  | 50–55 | −6.7 | +3.0 | +6.4 |

- **Contact ≈ 0.50·BABIP + 0.49·Avoid K** (R² 0.967, RMSE 1.9, about
  rounding noise; potential 0.54 / 0.48; the splits match). Power adds
  nothing. It only looks like it matters without BABIP, because it stands in
  for BABIP. Script: `fit_contact.py`.
- **Draft model vs draft-day POT** (outcome = POT now, first pass): the model
  adds signal within a POT level (+0.12 to +0.24) but loses to plain POT
  order across the class (2034–37: 0.37–0.43 vs 0.43–0.48). Its calls to put
  a lower-POT player over a higher one don't pay off on average.
- **Starters with Control 55+ sit 5–6 above OVR** on live data. This is
  unexplained so far.
- **Signal inventory (`--signals`, live data, 2026-11-06).** Ratings read in
  more than one place on the side a player is judged on:
  - **Hitters, every profile:** Avoid K twice (directly and inside Contact);
    Power in the batting model and the hit-profile modifier; Speed in the
    running model and the hit-profile modifier.
  - **Draft and potential hitters:** the draft-batter modifier reads the
    current Contact *and* Avoid K, so current Avoid K counts twice too.
  - **Draft and potential pitchers:** potential Stuff has 3 readers (the
    pitching models plus the draft-pitcher overall and Stuff modifiers),
    potential Movement 3, potential Control 2. This is the Aliff
    Stuff-stacking item.
  - **Draft and potential, both sides:** Age is read by the age and
    personality modifiers, and the draft class reads Intelligence and Work
    Ethic in both personality modifiers.
  - **Phase 3, hitter talent (2026-11-07).** Fit on 2,526 player-season-level
  rows (2042 ratings at every level, plus 2041 for veterans, hitters 24+).
  Cross-validated with folds grouped by player, the spearman of predicted
  with actual runs per PA (200+ PA) inside each level:

  | Level | Rows | Fitted | Legacy |
  |---|---|---|---|
  | MLB | 522 | 0.693 | 0.583 |
  | AAA | 373 | 0.563 | 0.506 |
  | AA | 292 | 0.606 | 0.532 |
  | A | 339 | 0.503 | 0.523 |

  - **Against OVR on live MLB / AAA hitters:** spearman 0.769 → 0.831. The
    Contact ≤ 40 residual goes −6.4 → −2.7 and Avoid K ≤ 40 −6.8 → −2.9, so
    the Avoid K double count is gone. Pitchers are unchanged apart from 7
    two-way players. Draft classes don't move yet: none of the old exports
    has BABIP.
  - **The stats disagree with the grid's Power rules.** HR per contact climbs
    smoothly with no cliff: .007 below 30, .012 at 30, .018 at 35, .022 at 40,
    .032 at 45. Power 60+ hitters with weak contact (BABIP / Avoid K ≤ 42)
    hit 115 wRC+ in MLB / AAA, against 134 with good contact. That's the same
    gap as at Power 40–50 (94 vs 108). The legacy grid buried exactly these
    hitters: Nestor Gallegos (Power 65, Avoid K 40) goes from rank 853 to 306
    and hit 110 and 129 wRC+; Pete Ayers 616 → 117, 124 and 112.
  - **The grid's scale anchors roughly hold:** balanced 60s / 65s / 70s fit
    141 / 162 / 181 wRC+ against the grid's 130 / 160 / 180. But 55s fit
    121, not 100: an average MLB hitter here has 50s ratings.
  - **Young players are left out** (under 24). Their ratings rise during a
    season, so their stats came from lower ratings than the end-of-season
    snapshot shows, which flattens the bottom of every curve.
- **Phase 4, pitcher talent (2026-11-08).**
  - **How OOTP builds the composites:** Movement ≈ 0.81·HRA + 0.18·PBABIP
    (R² 0.93; potential 0.73 / 0.24), and G/F adds nothing. Stuff ≈
    0.49·best pitch + 0.31·second + 0.13·third (R² 0.93), and velocity adds
    almost nothing. So legacy's pitch-mix maps counted the pitches a second
    time on top of Stuff.
  - **MLB punishes low Movement much harder than the minors do.** Inside
    MLB, HR per contact goes .045 at Movement 50 → .056 at 45 → .068 at 40
    → .080 at 35. MLB's HR rate is about 2.5× AAA's, which hid this in
    pooled MLB / AAA tables. The fitted model follows MLB, so it's much
    harsher on low Movement than legacy or OOTP's OVR.
  - **Cross-validated (folds by player), against runs allowed per BF** (from
    the line's events | actually charged), 150+ BF:

    | Level, role | Rows | Fitted | Legacy |
    |---|---|---|---|
    | MLB RP | 353 | 0.500 \| 0.433 | 0.385 \| 0.318 |
    | MLB SP | 251 | 0.477 \| 0.335 | 0.446 \| 0.374 |
    | AAA RP | 231 | 0.306 \| 0.234 | 0.287 \| 0.184 |
    | AAA SP | 204 | 0.418 \| 0.312 | 0.385 \| 0.291 |
    | AA RP | 185 | 0.228 \| 0.187 | 0.258 \| 0.228 |
    | AA SP | 143 | 0.387 \| 0.323 | 0.350 \| 0.291 |
    | A RP | 244 | 0.384 \| 0.272 | 0.270 \| 0.194 |
    | A SP | 145 | 0.243 \| 0.186 | 0.150 \| 0.139 |

    The MLB SP charged-runs gap is within noise: legacy's SP score doesn't
    correlate with the fitted model's residual (−0.02), and neither do
    stamina or pitch count.
  - **No support for the other legacy talent factors.** Extreme-GB starters
    allow 3.4% *more* runs than their components predict (legacy gives them
    ×1.10). Pitch count and stamina don't move runs allowed. Relievers allow
    about 5% fewer runs than their components at every G/F, which is runs
    accounting (inherited runners), not talent. Adding the pitch grades or
    velocity to the K model doesn't help consistently.
  - **Against OVR on live MLB / AAA:** SP 0.886 → 0.892, with the Stuff and
    Control residuals flattening; RP 0.853 → 0.822, because the model weights
    Movement far above OVR (residual +16.6 at Movement 65+).
  - **Draft classes**, scored on Movement since the exports have no HRA /
    PBABIP: worse against OVR / POT (within-POT 0.05–0.24 → 0.01–0.16).
    Against career MLB WAR they're better in every class with MLB time
    (2033–37 pitchers 0.045 / 0.162 / 0.258 / 0.080 / 0.031 → 0.081 / 0.189 /
    0.287 / 0.099 / 0.051, and the top-100 WAR is up). Watchlist: Aliff
    #28 → #9.
  - **Watch:** draft boards hold fewer pitchers. Pitchers in the pre-demand
    top 100 went 37 → 26 (2035), 27 → 23 (2038), 42 → 37 (2040), 23 → 25
    (2042). The bridge matches current-ratings pitchers, not potential ones;
    phase 5 (WAR) settles the balance between hitters and pitchers.
- **Fixed: current pitchers read potential ratings.** The HR-risk modifier
    keyed off potential Movement, and the knuckleball check off potential
    pitches, even when ranking on current ratings. Both now follow the
    scorer's ratings (fixed in legacy, so v2 has it too; goldens regenerated,
    only the `overall` sections moved). Live MLB / AAA: 60 of 1,521 current
    scores changed, all down (median −3%, young arms whose current Movement
    trails their potential); SP spearman 0.887 unchanged, RP 0.846 → 0.845.
    A test now checks the current profile reads no potential ratings.

## Phases

Each phase ends with an eval run against `legacy` and a check of the
watchlist.

**0. Evaluation harness: done** (3fcff0d).

**1. Data**
- ✅ **BABIP, HRA and PBABIP** (current, potential, vs L/R) map into the
  snapshot as `BABIP` / `HT P`, `HRA` / `HRA P`, `PBABIP` / `PBABIP P`
  (splits `"BABIP vL"` and so on). They're on `GamePlayer` as
  `babip(_ovr)`, `hr_allowed(_ovr)` and `pbabip(_ovr)`, and read None when a
  dataset lacks them. Production fills them on its next refresh after deploy.
  - **OOTP export headers, confirmed 2026-11-05** from an OOTP 27 export:
    current BABIP is `BABIP` and potential is **`HT P`** (height is the
    separate `HT` column). Checked by fit: potential Contact ≈ 0.55·`HT P`
    + 0.49·`K P`, matching StatsPlus. The snapshot uses the same names.
  - The export view had no HRA / PBABIP columns. If OOTP offers them, add
    them and confirm their headers; until then draft-class pitchers have no
    Movement components.
- ✅ **Season snapshots** (your spec, 2026-11-05: keep it simple, one per
  season per league from about in-game 4/8):
  - The first snapshot built on or after April 8 of a season is kept as
    `league_snapshots/<league>/archive/<season>.csv.gz`, plus `<season>.json`
    with the in-game date it was taken. It's never overwritten.
  - **When the app wakes up** (startup), `collect_season_snapshots` checks
    each league. If the stored snapshot already qualifies, it's archived with
    no StatsPlus call. Otherwise, once the in-game date is past April 8 and
    the season has none, the normal refresh starts and archives as it builds.
  - League-page refreshes during a session archive the same way.
  - It starts collecting once deployed.
  - **The first 2042 archive had no BABIP.** It was taken from the snapshot
    stored before the BABIP mapping deployed. On 2026-11-07 it was replaced
    with the live in-game 2042-12-11 snapshot, which has BABIP; the original
    is kept as `archive-2042-nobabip.csv.gz` next to `archive/`.
- ✅ **Season stats:** `league_stats.py <league> <years>` writes
  `league_stats/<league>/{bat,pitch,field}/<year>.csv`, every level and
  split. What StatsPlus serves (checked 2026-11-05):
  - `/api/playerbatstatsv2/`, `playerpitchstatsv2`, `playerfieldstatsv2`
    with `year`, `lid` and `split`. Without `lid` it's MLB only; each
    `/api/lgdata/` league id (18 in `yfmlb`, levels 1–6) gives the minors.
  - Past seasons are served (2034 checked). One row per player-team stint.
  - **WAR is included** (`war` for batting and pitching, plus `ra9war`), along
    with full counting stats and `ubr`. Fielding has `zr`, `framing` and `arm`.
    2042 MLB WAR sums to 1,037 (hitting 584, pitching 453).
  - Backfilled 2030–2042 for `yfmlb` into `fly_data/league_stats/`.
- ~~Slot amounts and the over-slot budget~~: not needed. The demand
  modifier stays as the decision layer (2026-11-05).

**2. `v2` skeleton, built in parallel (no score changes)**

Steps 2a–2c are in `plans/ranking-v2-technical-plan.md`.
- ✅ **2a, the engine:** a `ranking/` package with a profile per ranking
  method, typed results, the ledger and the run manifest. Today's logic
  runs as "legacy" stages, unchanged, and the demand step runs last with
  pre- and post-demand scores and ranks kept. Registered as engine `v2`
  (`eval_rankings.py --engine v2`).
  - **Gate passed (2026-11-05):** `v2` matches `legacy` on every field,
    breakdowns included, in unit tests and on 31,629 live rankings (the
    snapshot under both profiles plus all ten `yfmlb` classes). Every
    ledger sums to its score.
  - Pitching shows as one "SP / RP role adjustments" ledger line until
    phase 4 replaces the legacy pitcher scorer.
- ✅ **2b, eval reports:** `--parity`, `--explain <player>` and the signal
  inventory (`--signals`). Live parity: 11 of 11 pools identical. The
  inventory's findings are under "Findings so far".
- ✅ **2c, the app:** runs are stored per engine with the ledger and
  pre-demand fields; the player card shows the ledger as a waterfall; the
  draft table has pre-demand columns; a top-bar toggle switches engines
  (default `v2`). Deployed.
- ✅ **Dead code deleted:** `apply_adjustment`, the two
  `*DistanceFromOverallModifier`s and the one-player `calculate_*` ranker
  paths. Nothing called them; no scores changed.

**3. Talent layer, hitters first: done** (2026-11-07)
- ✅ `ranking/hitter_talent.py` (the model and its committed artifact
  `ranking/artifacts/hitter_talent_v1.json`), fit by
  `python -m ranking.fitting.hitter_talent --data-dir fly_data`, which prints
  the cross-validation against legacy, the rules and the hypotheses.
- ✅ Rules suite (`ranking/fitting/rules.py`, `tests/test_model_rules.py`):
  7 rules pass, and 4 Power hypotheses aren't supported (see "Findings so far").
- ✅ In `v2`, `LegacyModel` takes its batting component from the fitted
  model, and the legacy batting model only runs for players without BABIP.
  The ledger line reads "batting talent (N wRC+)".
- Refit once the 2043 archive (April ratings) is in. That's the first
  season with start-of-season ratings, and the first real season-grouped
  holdout.
- Not done yet: `eval_rankings.py --hypotheses` (re-checking hypotheses
  against the stats); the vs L / vs R splits (phase 6).

**4. Talent layer, pitchers: done** (2026-11-08)
- ✅ Composition fits (see "Findings so far").
- ✅ `ranking/pitcher_talent.py` with artifact
  `ranking/artifacts/pitcher_talent_v1.json`, fit by
  `python -m ranking.fitting.pitcher_talent --data-dir fly_data`. Four
  chained rates (Stuff → K%, Control → BB%, HRA → HR per contact, PBABIP →
  hits on balls in play), each with level and role terms, tabulated for MLB
  starters and relievers. A second pair of `hr` / `hit` tables on Movement
  serves classes without HRA / PBABIP.
- ✅ In `v2`, `LegacyModel` takes pitching from the fitted model. Dropped:
  the SP / RP grids, GB-type, HR-risk, knuckleball and grade-based pitch-mix
  factors, and the Stuff −10 / +5 role shift (the fitted role term replaces
  it). Kept until phase 5: stamina and the pitch-count part of the mix maps,
  as an "SP / RP role" ledger line, and the RP multiplier. The legacy scorer
  only runs for a pitcher without Stuff / Control / Movement.
- ✅ Rules: pitcher rule 5 is now a hypothesis, which leaves no enforced
  pitching rule. Hypotheses: H1 holds (Movement + Control carry weak Stuff;
  Control alone doesn't); H2 isn't supported (80 / 40 / 40 is a decent
  starter, 92, and a so-so reliever, 94); H3 holds only barely (Stuff is
  worth −16.0 in relief vs −15.9 starting, since role is an additive term).
- The test fixtures' BABIP / HRA / PBABIP are now derived from Contact and
  Movement, as in a real export. The legacy goldens are byte-identical.

**5. Value layer**
- Playing time, the injury → games model, positional adjustment and
  replacement level → WAR.
- Retires RP ×0.82, the batting / fielding / running weights and the two-way
  bonus.

**6. Development layer**
- Distributions of peak WAR from past classes and the archive.
- Retires the age, personality, scouting accuracy and draft modifiers, keeping
  your values as priors / judgment.
- Platoon items from `my-todo.txt` land here and in talent (vs L / vs R
  ratings per profile).

**7. Decision layer**
- The demand modifier as the last stage, with pre- and post-demand values and
  ranks stored and shown. Ranking by E[v] plus the upside dial.

**8. Switch the app to `v2`**
- Change `get_ranker_for_method`, regenerate the goldens deliberately, and
  delete `legacy`.

## Open questions

- ~~**Replacement level and WAR:** StatsPlus's WAR directly, or our own?~~
  Our own from the counting stats, so positional adjustment and replacement
  level are explicit, calibrated against StatsPlus's WAR (2026-11-05).
- ~~**Web app:** a toggle or the eval report?~~ A toggle, defaulting to `v2`
  (2026-11-05).
