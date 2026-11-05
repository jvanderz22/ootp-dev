# Plan: Ranking redesign

Replace the stack of hand-tuned multipliers with layered models in one unit
(WAR). Each layer answers one question with one stated method. Your tuned values
stay as starting points (priors). Every step's contribution is recorded so a
ranking explains itself. It's built in parallel to the current code (engine `v2`
next to `legacy`) and judged by `eval_rankings.py` at every step.

## Decisions

| Date | Decision |
|---|---|
| 2026-11-04 | **Unit is WAR.** Every layer outputs WAR or a WAR distribution. |
| 2026-11-04 | **Ranking rule: expected value, with upside favored at equal EV** (see "Uncertainty and the ranking rule"). |
| 2026-11-04 | **Draft cost is relative to slot.** Each pick has a slot amount you can always offer. Over-slot only works with budget, which you often don't have. |
| 2026-11-04 | **Your tuned values are priors and may stay.** They push things the direction you want. Fitted layers start from them, and explicit judgment adjustments remain as their own visible step. |
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
- **Ranking and value are mixed together.** "Is he worth his demand at the
  pick where I'd take him" is a decision, but it's implemented as a
  rank-banded distortion of the talent score.
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
| **1. Talent** | ratings → expected rate stats (hitters: runs per PA from BABIP / Avoid K / Gap / Power / Eye; pitchers: runs per 9 innings from base components; fielding runs by position) | regression fit to StatsPlus season stats against ratings, weighted by PA / IP, monotone in each rating, the 2023 grids as priors | the attribute grids, SP / RP pitch mix, velo, HR risk, hit profile, handedness |
| **2. Value** | rates → WAR for a season | expected playing time (role, stamina, injury proneness as expected games lost) + positional adjustment + replacement level | RP ×0.82, the 0.73 / 0.22 / 0.05 weights, injury multipliers, two-way bonus |
| **3. Development** | a prospect → distribution of peak WAR | fit on past classes + archived snapshots: rating growth given age, POT, work ethic, intelligence, scouting accuracy | age, personality, secondary personality, scouting accuracy, the draft overall / Stuff modifiers |
| **4. Decision** | draft board: worth taking at my pick? | surplus value at your next pick (see "Draft decision layer") | `DraftDemandModifier`'s rank bands |

Each **profile** (current, potential, draft) is one declared config: which
ratings to read (current / potential / vs L / vs R), which layers run, and
their settings. That's the `ScoringProfile` idea from the first draft of this
plan, now one config per profile.

### Fitting

- **Priors:** with about 10 classes and a few seasons, data is thin. Each
  fitted layer starts from your values (the grids, the modifier tables) and
  moves away only as far as the data supports. A setting controls how strong
  each prior is.
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

- **Cost:** a player demanding at or under slot costs nothing extra. Over slot,
  the overage counts against this draft's over-slot budget (a setting per
  class). If it's over the budget, he's unsignable at that pick and flagged
  as such. "Impossible" means unsignable.
- **Availability:** the chance he's still there at your next pick, estimated
  from past drafts (draft position vs draft-day ratings, from `drafted_picks`
  / StatsPlus `draftv2`).
- **Board:** order by surplus value at your next pick, and show the overall
  value order alongside. This replaces the rank bands: rank matters only
  through "would I be picking him here".

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
- **A ratings snapshot archive.** Today each refresh overwrites the last one.
  Keep at least one per season (end of season), versioned. Pairing ratings
  with stats and learning development both need ratings history, and
  StatsPlus only serves current ratings.
- **Season stats:** player batting / pitching / fielding by year with L/R
  splits. These are listed in the StatsPlus API (via StatsPlus-MCP's docs)
  but not tried yet. Check whether past seasons and WAR are included.
- **Slot amounts per pick**, and your over-slot budget per draft.
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
- Map BABIP, HRA and PBABIP (current, potential, L/R) into the snapshot.
- Archive snapshots per season.
- Build a StatsPlus season-stats pull, after trying the endpoints and
  checking whether past seasons and WAR are included.
- Get slot amounts and the over-slot budget setting.

**2. `v2` skeleton, built in parallel (no score changes)**
- A `ranking/` package with profiles, the four layers as stages, typed
  results, the ledger and the run manifest.
- Today's logic is moved into the stages unchanged, as "legacy" layer
  implementations, and registered as engine `v2`.
- **Gate:** `v2` matches `legacy` exactly. The ledger shows up in the
  breakdown and player card.
- Add the signal inventory report. Delete the dead code in `v2` only.

**3. Talent layer, hitters first**
- Use BABIP / Avoid K / Gap / Power / Eye.
- Convert the 2023 grid with BABIP ≈ 2·Contact − Avoid K and mark the rows
  whose separate Avoid K penalty needs your review. That converted grid is
  the prior.
- Fit to season stats once pulled; until then, prior only. The output is
  runs per PA. Classes without BABIP keep the legacy talent stage.

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
- The slot / budget / availability board, the E[v] ranking and the upside
  dial.

**8. Switch the app to `v2`**
- Change `get_ranker_for_method`, regenerate the goldens deliberately, and
  delete `legacy`.

## Open questions

- **Slot amounts:** where do they come from? A StatsPlus endpoint, the OOTP
  export, or entered per draft?
- **Over-slot budget:** one number per draft class, entered in the app?
- **Replacement level and WAR:** use StatsPlus's WAR if the stats include it,
  or compute it ourselves for the league?
- **Web app:** show `v2` and `legacy` side by side (a toggle), or is the eval
  report enough?
