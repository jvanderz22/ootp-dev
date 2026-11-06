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
  breakdown goes through a ContextVar side channel. There's dead code too:
  `apply_adjustment`, the `*DistanceFromOverallModifier`s, the one-player
  `calculate_*` paths.

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
- **To add:** the `potential` profile, calibration once stats exist, and
  ledger-based stage diffs.

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
- **2b, eval reports:** `--parity`, `--explain <player>` and the signal
  inventory (`--signals`).
- **2c, the app:** store the ledger and pre-demand fields, show the ledger
  on the player card, and add the engine toggle (default `v2`).
- Delete the dead code in `v2` only.

**3. Talent layer, hitters first**
- Use BABIP / Avoid K / Gap / Power / Eye.
- Fit to season stats (runs per PA), monotone, held to the rules suite. Your
  confirmed rule list comes first.
- Classes without BABIP keep the legacy talent stage, and so does the
  whole stage if the fitted model doesn't beat legacy in the eval yet.

**4. Talent layer, pitchers**
- First, fit how Movement (and Stuff) is built from its parts.
- Then the same approach as hitters. This handles the leftover SP grid,
  RP pitch-map and draft Stuff-stacking items.

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
