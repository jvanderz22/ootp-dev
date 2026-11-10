# Plan: Phase out the XGBoost grids

Your attribute grids (`attribute_models/*.py`) are XGBoost models fit to
~60 hand-labelled rows each (`training_data/`), plus your test anchors,
monotone in every rating. Legacy scores with them directly. v2 has replaced
most of them with fitted talent models, but still leans on them, and on the
legacy points scale around them, in a few places. This plan lists what's
left, what the stats can measure instead, and the order to retire it. The
design is in `plans/ranking-architecture-plan.md`. This is the detail behind
its phase 8 ("switch the app to `v2`") and the "revisit the fielding
architecture" TODO.

**Goal:** v2 uses nothing from `attribute_models/`, `training_data/` or the
legacy scorers, and makes no round trip through legacy points. **Legacy
stays runnable beside it for the foreseeable future** (your call,
2026-11-08). You want to run a few drafts with both models to compare: you
think v2 is better, but legacy has given you reasonable results. So xgboost
stays in the runtime image for legacy, and deleting legacy (step 4) waits
until you decide.

## What's left (2026-11-08)

| Piece | What v2 uses it for | How often it runs |
|---|---|---|
| **Fielding grids** (C, 1B, 2B, 3B, SS, LF, RF) | the shape within each position, the scale across positions, the best-position pick, and the utility bonus (`fielding_talent.grid_scores`) | every hitter, every run. CF was replaced by `cf_grid` on 2026-11-08 |
| **Batting grid** | the fallback for rows without BABIP, Contact or Avoid K | 0 of 138k hitter rows across the 76 local files, since the implied BABIP |
| **SP / RP grids** (`PitcherScorer`) | the fallback for rows without Stuff, Control or Movement, read back as an ERA through the bridges (`Value._legacy_eras`) | 4,404 of 138k pitcher rows, all from three old non-draft exports (`yfmlb-2033.csv`, `yfmlb-2038-prospects-osa.csv`, `yfmlb-sf-2037.csv`). Their header names Control `CON`, the same as batting Contact, so Control reads as missing |
| **Running grid** | nothing at runtime: it's fit against only for the running points bridge | fitting only |
| **The card's L/R scores** (`scoring/splits.py`) | the legacy scorers re-run on each side when a card opens | every card open, on both engines. The card shows only the ratings from it, never the scores |
| **Points bridges** and the legacy scoring shell | each fitted value is mapped onto legacy points so `LegacyModel` can run `PositionPlayerScorer.score_many` (0.73 / 0.22 / 0.05) and the pitcher role factors (legacy stamina maps, `RP_OVERALL_MODIFIER`). The result, `model_score`, feeds the parts below | every player |
| ↳ score-weighted modifiers | `AgeModifier` and `DraftSecondaryPersonalityModifier` set their weight from `model_score` through `RankGradiatedModel` (e.g. age counts fully below 35 points, half at 55, nothing at 130) | prospects |
| ↳ utility bonus | legacy's formula on the grid scores (up to +4 points for CF cover), turned into runs through the fielding bridge | every hitter |
| **Fitting scripts** | `legacy_scores` / `points_bridges` in the hitter, pitcher, running and fielding fits | each refit |
| **Startup** | `model_cache.warm()` trains all 13 grids | 0.4 s, so the cost is the code and the dependency, not the time |

**Dependencies:**
- **xgboost** is used at runtime only by `attribute_models/`. Offline,
  `ranking/fitting/components.py` (the Movement / Stuff composition fit) also
  uses it, so it moves to a fitting-only requirements file rather than going
  away.
- **scikit-learn** stays: the fits use it, and so does `DraftDemandModifier`
  at runtime.
- **The Dockerfile** copies `attribute_models/` and `training_data/`, and
  `tests/test_dockerfile.py` checks those lines.

## What the stats can measure (fielding)

Fielding is the only place where the grids still decide something that
matters. So the first question is which ratings the stats can price. Here
are 2041–42 MLB and AAA lines with 300+ innings at a position, regressed on
the December 2042 ratings. Each number is the change per rating point, over
a 1,350-inning season.

| Pos | Lines | Zone runs (R²) | Other stats |
|---|---|---|---|
| C | 166 | ~0 for all three (0.21) | framing runs: Framing +0.79 (R² 0.72). CS%: nothing (R² 0.01). Passed balls: Blocking −0.11 (R² 0.08) |
| 1B | 146 | Range +0.22 (0.29) | little to price |
| 2B | 156 | Range +1.39, Error +0.19 (0.64) | double plays: Turn DP +0.74 (R² 0.14), not in zone runs |
| 3B | 135 | **Arm +0.64**, Range +0.42, Error +0.30 (0.54) | errors per 100 chances: Error −0.09 (R² 0.36) |
| SS | 151 | Range +1.35, Arm +0.33, Error +0.18 (0.57) | double plays: Turn DP +0.37 (R² 0.05) |
| LF | 147 | Range +1.09 (0.60) | arm runs: Arm +0.16, Range −0.12 (R² 0.11) |
| CF | 146 | Range +2.16 (0.51) | arm runs: Arm +0.19, Range −0.50 (R² 0.21) |
| RF | 159 | Range +0.98, Arm +0.08 (0.53) | arm runs: ~0 (R² 0.00) |

What that says:
- **Zone runs already carry infield Arm and Error where they matter.** At 3B
  Arm is the biggest rating, and at SS it's a quarter of Range. "Infield Arm
  / Error have no stat" (decision, 2026-11-08) isn't quite right: they show
  up inside zone rating.
- **Turn DP moves double plays, but zone runs don't credit it.** Pricing it
  needs a run value per DP (from the league's linear weights), plus a check
  of whether StatsPlus's WAR counts DPs anywhere.
- **Catcher Arm and Blocking barely show in any stat.** Framing is the
  catcher's measurable skill. Arm and Blocking stay judgment (floors today).
- **Outfield arm runs are opportunity-driven:** poor-range outfielders get
  more chances to throw. Arm is worth ~0.2 runs a point in LF and CF, and
  OF assists per chance track it more cleanly (decision, 2026-11-08).
- **The caveats:** one ratings snapshot, taken after the seasons it's paired
  with, and 135–166 lines a position. The 2043 season is the real test
  (`plans/ranking-archive-plan.md`).

## Where it ends up

- **Fielding talent, as lookup tables per position** (your call,
  2026-11-08: like CF, or a full set of lookup values). Each position gets a
  table per rating, giving runs per season against an average fielder there
  at each 5-point step, interpolated between steps. A position's runs are
  the sum of its tables, with the floors as the one interaction. The stats
  seed the tables:
  - zone runs for every position;
  - framing for C;
  - double plays for 2B and SS;
  - arm runs or assists for OF, if they hold up.

  You then adjust them where your read differs, so every number is visible
  and editable. CF moves into the same format, from `cf_grid`. Ratings no
  stat measures get judgment weights: catcher Arm and Blocking.
- **Across positions:** value = runs at the position + its adjustment, and
  the best position is the highest value. Per-position curves were tried
  once and rejected (2026-11-08): they valued good CFs and SSs more at
  easier spots. They were matched to each position's own regulars, which
  extrapolates the easy positions' curves past the range their regulars
  have (few LFs have 70 Range). Two ways around that, to try in order:
  1. Share each rating's effect across a family (OF range across LF / CF /
     RF, IF range across 2B / SS / 3B), with a scale per position, so a
     70-Range LF is read off the same skill as a 70-Range CF.
  2. Cap each position's curve at the top of its observed range.
- **The calibration:** the value calibration's level per position
  (`fielding.by_position`) should mostly vanish once each position is fit on
  its own runs. Keep the within-position stretch only if it still fits.
- **Utility stays, as roster flexibility, not runs** (your call,
  2026-11-08). Its value is in building a roster, not in runs prevented. So
  it becomes its own judgment line in the value layer, read off which other
  positions a player can cover (his tables clear the floors there), and
  sized by you. Today it's legacy's points formula on the grid scores,
  turned into "runs" through the fielding bridge.
- **A native model stage:** v2's talent and value stages build WAR directly,
  with no `LegacyModel` shell, no `PositionPlayerScorer`, no points bridges,
  and no pitcher role factors or RP multiplier. The value stage already
  picks the role on WAR.
- **Score-weighted modifiers in WAR:** `AgeModifier` and
  `DraftSecondaryPersonalityModifier` keep their tables, with their
  `RankGradiatedModel` thresholds converted once from legacy points to WAR
  through today's bridges, then frozen. Boards should barely move.
- **The fallbacks:**
  - Rows the fitted models can't read are scored at replacement level, with
    a ledger line saying why.
  - The old exports' duplicate `CON` header gets read positionally, so their
    pitchers stop falling back.
- **The card's L/R view shows v2's per-side numbers** (your call,
  2026-11-08): wRC+ vs LHP / RHP for hitters and ERA for pitchers, from the
  talent stages, which already compute both sides. The legacy scorer calls
  go.

## Order of work

### 1. Removals that need no judgment ✅ (2026-11-09)

- `scoring/splits.py` stops running the legacy scorers. The card's L/R view
  shows the split ratings, plus v2's per-side wRC+ (hitters) and ERA
  (pitchers) under v2.
- The batting fallback (0 rows) and the pitcher fallback are scored at
  replacement level, and `Value._legacy_eras` goes.
- ~~Fix the reader for the duplicate `CON` header.~~ Not needed:
  `pipeline.normalise_dataset` already renames those columns when a class is
  processed. Only reading the raw files directly hit it.
- ~~`warm()` trains the grids only when the legacy engine is in use.~~
  Dropped: it takes 0.4 s, and legacy stays runnable.
- **Gate:** tests pass; boards are unchanged apart from the fallback rows.

### 2. Fielding, position by position (needs you)

1. Seed each position's lookup tables from the stats, and report them next
   to your grid, the way CF was reviewed: runs by rating step, predicted
   against actual.
   - **Turn DP** (your call, 2026-11-08): priced through double plays, at a
     run value per DP from the league's linear weights. It keeps a floor
     around 35, and the DP data has to validate it: DP rates should fall
     away below it.
   - **Catcher Arm and Blocking** get judgment weights (your call).
2. Go through each position with you: its tables against your descriptions,
   the floors, and the judgment weights. That's the step that took CF from
   the grid to `cf_grid`.
3. Settle the cross-position scale and the best-position pick. Build utility
   as its own flexibility line, and size it with you.
4. Refit the value calibration, and drop the per-position levels if they're
   no longer needed.
- **Gate:**
  - predicted and actual runs line up within each position, by rating step;
  - rule 7 (harder positions are worth more) passes;
  - best-position picks agree with where MLB regulars actually play, at
    least as well as the grids do;
  - the draft eval is no worse;
  - you review the board movers before it ships.

### 3. A native model stage (no points)

- Replace `LegacyModel` and the points bridges with a v2 talent → value path.
- Convert the two score-weighted modifiers' thresholds to WAR.
- Drop the pitcher role factors, `rp_multiplier` and the legacy stamina maps
  from v2.
- Take `legacy_scores` and `points_bridges` out of the fitting scripts.
- Re-express the org rankings curve in WAR (its existing TODO) here.
- **Gate:** v2's boards match the last commit within rounding, except where a
  converted threshold moves someone, and you see those first.

### 4. The cutover (phase 8): deferred

Not for the foreseeable future (your call, 2026-11-08). You want to run a
few drafts with both engines first. Until then, legacy stays runnable
beside v2, with the engine toggle, its goldens and xgboost in the image.
Steps 1–3 only make v2 independent of it. When you decide:

- Switch the app and the CLI to v2 only.
- Delete `rankers/`, `scoring/position_player_scorer.py`,
  `scoring/pitcher_scorer.py`, `scoring/model_cache.py`, `attribute_models/`
  and `training_data/`. `scoring/runtime_components.py` moves into `ranking/`.
- Remove the engine toggle and the legacy goldens.
- Move xgboost to a fitting-only requirements file, and drop the two COPY
  lines and their Dockerfile test.
- Comparisons with legacy then go through `eval_rankings.py --against
  <the last commit with legacy>`.
- Ship one release with both engines' outputs saved first, as the technical
  plan says.
- **Gate:** a full test pass, and the saved comparison reviewed.

Step 1 can start now. Step 2 is the long one, and step 3 follows it. Step 4
waits on your call. Nothing here waits on the archive, but the 2043 season
is the first real test of the fielding tables.

## Decisions (2026-11-08)

1. **Fielding:** like CF, as lookup tables per position and rating, seeded by
   the stats and adjusted by you.
2. **Turn DP:** priced through double plays, with a floor around 35 that the
   DP data has to validate.
3. **Catcher Arm and Blocking:** judgment weights.
4. **Utility:** kept, as roster flexibility, not runs.
5. **The card's L/R view:** v2's per-side wRC+ and ERA.
6. **Legacy stays runnable** for the foreseeable future, so you can compare
   both engines over a few drafts. Git refs alone aren't enough.

Still open:
- the size and shape of the utility line;
- the judgment weights for catcher Arm and Blocking;
- the cross-position scale (the family-shared seeding, or caps).

These get settled in step 2.

## Risks

- **One season of ratings, taken after the season.** The fielding fits may
  be flattered. Refit on the 2043 season before trusting their fine shape.
- **Extrapolation at the easy positions.** This is the failure that sank
  per-position curves the first time. The family-shared fit is the guard.
- **Board churn.** Fielding touches every hitter, so step 2 moves the whole
  board. Each position is reviewed before it ships.
- **Stored runs rescore** when `model_version` changes, and the goldens need
  regenerating at each step.
