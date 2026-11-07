# Technical plan: building ranking engine v2

How to build the system described in `ranking-architecture-plan.md` (the
*what* and *why*). This document is the *how*: code layout, data model,
interfaces, storage, testing, and the order of work. Nothing here changes a
score until a step's gate says so.

## Constraints

- **Production box:** Fly, 1 shared vCPU, 512 MB. A league is ~15k players,
  scored in batches of 1,500 (`DEFAULT_BATCH_SIZE`) so the pool is never
  resident at once. v2 keeps that batching and keeps per-player state small.
- **Python 3.11**, in production (`Dockerfile`) and, since 2026-11-05, in
  the local venv (it was 3.9.6). Package versions match the old venv's, so
  scores are unchanged.
- **Parallel build:** `legacy` (today's `rankers/`) stays the app's engine
  until the switch. The goldens keep pinning `legacy` the whole time.
- **Determinism:** the same inputs and config give the same output. Fitted
  models are trained offline and loaded as artifacts, never trained at
  request time.
- **Old data formats:** classes before 2039 lack some columns (`VT`, `BABIP`,
  ...). Expected, not a bug. Stages fall back per player when an input is
  missing; they never crash.

## Package layout

```
ranking/
  __init__.py          Ranker, PROFILES, get_profile()
  profiles.py          ScoringProfile + CURRENT / POTENTIAL / DRAFT
  ratings.py           RatingsView: current / potential / vs L / vs R reads
  state.py             PlayerState, SideState: per-player working state
  ledger.py            Ledger, LedgerLine
  results.py           RankedResult (ScoredPlayer's fields + v2 fields)
  manifest.py          RunManifest: engine, config hash, data / artifact hashes
  signals.py           the signal inventory: reads traced per model / modifier
  ranker.py            Ranker: batching, running stages, sorting, results
  stages/
    base.py            BatchStage / PoolStage interfaces
    legacy.py          LegacyModel, LegacyModifiers, TwoWay (today's logic)
    demand.py          Demand (rank-adjusted modifiers, last)
    hitting.py         (phase 3) talent: hitters
    pitching.py        (phase 4) talent: pitchers
    value.py           (phase 5) rates -> WAR
    development.py     (phase 6) prospect -> WAR distribution
  fitting/             (phase 3+) offline training scripts -> artifacts
    datasets.py        ratings x stats joins, grouped CV folds
    ...
  artifacts/           (phase 3+) fitted parameters, JSON, committed
```

**Status (2026-11-05): step 2a is built** (`profiles`, `ledger`, `state`,
`results`, `manifest`, `stages/{base,legacy,demand}`, `ranker`;
`eval_rankings.ENGINES["v2"]`; `tests/test_ranking_parity.py`). The parity
gate passes:
- **Unit tests:** every profile, 3 seeded classes plus the snapshot fixture,
  a batch size that splits the class, all fields identical. Dropping one
  modifier from a profile makes all 160 rows differ, so the test does detect
  a change.
- **Live `fly_data`:** 31,629 rankings (the snapshot under `overall` and
  `potential`, plus all ten `yfmlb` classes 2033–2042), 0 rows differing in
  any field, breakdowns included. Ledger totals match scores within 3e-14.
- **Memory:** a full 10.9k-player league peaks at 360 MB on v2 vs 340 MB on
  legacy (local macOS). Re-measure on the production machine before the
  switch.
- **Known coarseness:** the legacy pitcher scorer applies pitch mix,
  stamina, GB and HR risk internally, so the ledger shows them as one "SP /
  RP role adjustments" line until phase 4 replaces that stage.

**Status (2026-11-06): step 2b is built.** `eval_rankings.py` has
`--parity`, `--explain` and `--signals` (see "Evaluation and reporting").
- **Pipelines:** `Ranker(profile, pipeline)` takes `"v2"` (the default, what
  later phases change) or `"legacy"` (today's scoring as stages, kept for
  good). The parity tests hold both to the legacy rankers. `--explain` uses
  the legacy pipeline to give a legacy score its ledger. The manifest records
  the pipeline.
- **`--parity` on live `fly_data`:** 11 of 11 pools identical (the current
  pool plus the ten classes), every field with breakdowns leaf by leaf, and
  the order.
- **`reads` are measured, not declared:** the plan had each stage declare a
  `reads` set. Instead `ranking/signals.py` traces every rating read off a
  `GamePlayer` (and the result fields demand reads) and attributes it to the
  model, scorer or modifier whose code read it. Declared sets would drift
  from the code; traced ones can't. The cost: a branch the data never reaches
  isn't seen, so it runs on whole pools (about 25 s for the ten classes).
  The `reads` attributes are gone from `stages/base.py`.

**Status (2026-11-06): step 2c is built.** The app keeps runs per engine and
has a v2 / legacy toggle, defaulting to v2. Where it differs from the sections
below:
- **The engine travels as a request header, not a query argument.** The
  top-bar toggle sends `X-Ranking-Engine` on every GraphQL request (and the
  CSV download); `web/app.py`'s `RankingEngineScope` scopes it to the request
  (`ranking_engine.using`), and storage, the class index and the league rows
  cache read it from there. No resolver signature changed. `RankingSource`
  reports the engine a row came from, and `RankingSourceInput.engine` can
  override it. Switching reloads the page (table state is in the URL), so
  two tabs can show the two engines side by side.
- **Scoring:** processing a draft class scores it under both engines (a class
  is small). A league refresh scores only the default engine; the other is
  scored the first time it's viewed, through the existing freshness check.
  A class processed before 2c (legacy runs only) is scored under v2 the first
  time its rows are read (`pipeline.class_results`).
- **Migration 3** (`db._runs_by_engine`) rebuilds the run tables with
  `engine` in both keys and tags existing runs `legacy`. It's idempotent, and
  migration 1 applies it before importing a pre-SQLite install. On a copy
  built with HEAD's code (two league methods + two classes, 23,679 rows) it
  ran in 0.3 s with every row identical and integrity / foreign keys clean.
- **Ledger storage:** `{"side", "lines": [[stage, label, delta, side]]}`,
  deltas to 4 places, both sides kept (the card lists the uncounted side
  separately). About 410 bytes a player: 4.5 MB per league method.
- **Card:** a "Score ledger" waterfall under the model section (bars from
  the running total, grouped by stage, no-effect lines counted but hidden),
  the uncounted side in a collapsed panel, and the pre-demand score and rank
  for draft-class rows. **Draft table:** "Pre-dem" and "Pre-dem #" columns,
  sortable, in place of a separate sort toggle (dropped in the league view).
- The `rankingRun(source)` manifest query wasn't added; the manifest is
  stored on `model_runs` and its `unit` is on `ScoreBreakdown`.

## Core data model

### `ScoringProfile` (`profiles.py`)

A frozen dataclass, one per ranking purpose, keyed by ranking method
(`overall`, `potential`, `draft_class`) like `rankers/get_ranker.RANKERS`.

| Field | Legacy source today |
|---|---|
| `ratings`: `"overall"` / `"potential"` (the scorers' `type`) | scorer `type` branches |
| `rp_multiplier` | `RP_OVERALL_MODIFIER`, draft `- 0.1` |
| `shared_modifiers`, `batting_modifiers`, `pitching_modifiers` | ranker properties |
| `demand_modifiers` (rank-adjusted, run last) | `rank_adjusted_modifiers` |
| `two_way_threshold`, `two_way_bonus` | 1.8 / 2.5 / 2.2 and the overridden `aggregate_*` |
| `stages` (phase 3+): which stage implementations run | n/a |

Helpers:
- `without(*modifiers)`: used by `splits.py`.
- `describe()` / `config_hash()`: used by the manifest.

### `RatingsView` (`ratings.py`)

The single place that maps "the profile's view of a player" to the ratings
read. It replaces `stuff` vs `stuff_ovr`, `get_pitches()` vs
`get_ovr_pitches()`, and the scorer `type` branches:

- `view.contact`, `view.babip`, `view.avoid_k`, `view.stuff`,
  `view.pitches()`, ... resolve to current, potential, or a vs-L / vs-R split
  according to the profile (and an optional `split` argument).
- `view.has("babip")` lets a stage fall back per player when a dataset lacks
  an input.
- Legacy stages don't use it (they call the legacy scorers, which keep their
  own `type`). It arrives with the first new stage in phase 3.

### `PlayerState` (`state.py`)

Per-player working state while a batch flows through the stages. Discarded
after the batch, except for what `RankedResult` keeps:

```
PlayerState
  player: GamePlayer
  batting:  SideState(score, components{batting, fielding, running}, best_position)
  pitching: SideState(score, components{starter, reliever})
  value: float              # combined, pre-demand
  ledger: Ledger
  breakdown: dict           # legacy-compatible tree (see "Breakdown vs ledger")
  # phase 5+: war_rate, playing_time
  # phase 6+: distribution (P10 / P50 / P90 or samples)
```

### Stages (`stages/base.py`)

Two kinds, because demand needs the whole pool's ranking:

- **`BatchStage.run(states, profile)`** runs per batch, player-local, and
  mutates `PlayerState`s. Examples: model, modifiers, two-way, and later
  talent, value and development.
- **`PoolStage.run(results, profile)`** runs once on every result, after the
  pre-demand sort. Example: demand.

Every stage:
- adds ledger lines for what it changed;
- has its reads measured by the signal inventory (`ranking/signals.py`),
  rather than declaring them;
- reads ratings only through `RatingsView` (new stages) or the legacy
  scorers (legacy stages).

### `Ledger` (`ledger.py`)

- `LedgerLine(stage, label, delta, side)` is a NamedTuple, kept small because
  a league holds ~15k ledgers of ~10–20 lines.
- `Ledger.side` is the side the player is judged on, set by the two-way
  stage. Counted lines are combined lines plus that side's lines, and they
  sum to the final value.
- Multiplicative steps are recorded as `value × (factor − 1)`, applied in
  order.
- The **unit** is legacy score points until the value layer, then WAR. The
  manifest records which.
- **Floating point:** legacy computes `base × (f1 × f2 × …)`, while the ledger
  applies the factors one at a time. The final value always comes from the
  stage's own arithmetic (so parity is exact), and the ledger total matches it
  to within 1e-9. A test checks that.

### `RankedResult` (`results.py`)

Every `ScoredPlayer` field (a subclass, so existing consumers work) plus:
- `pre_demand_score`, `pre_demand_rank`: the value and rank before the demand
  step, as first-class fields.
- `rank`: final, post-demand.
- `ledger`: the `Ledger`.

### `RunManifest` (`manifest.py`)

`{engine, profile, config_hash, unit, training_data_hash, artifact_versions,
source_version, scored_at}`.

- `training_data_hash` covers `training_data/*.csv` (the legacy grids).
- `artifact_versions` (phase 3+) lists each fitted artifact's id and hash.

Two runs with the same manifest are interchangeable, so the eval tool and the
app can tell exactly what produced a ranking.

## Pipeline for each profile

Legacy-parity version (phase 2):

```
for each batch of GamePlayers:
  LegacyModel      PositionPlayerScorer / PitcherScorer.score_many (cached, per profile)
                   ledger: batting x0.73 / fielding x0.22 / running x0.05;
                           SP or RP model + role adjustments
  LegacyModifiers  shared + side modifiers, each fed the *unmodified* model
                   score, product then multiply (legacy arithmetic)
                   ledger: one line per modifier per side
  TwoWay           high side = batting if batting > pitching else pitching;
                   bonus = low x two_way_bonus when high - low < high / threshold
                   ledger: Ledger.side = high side; bonus line
  -> RankedResult (ScoredPlayer fields rounded exactly as legacy)
sort all by pre-demand value (stable)
Demand             rank-adjusted modifiers on the pre-demand rank
                   ledger: one line per modifier; pre_* fields kept
classify / prune breakdown, final sort by post-demand value, assign rank
```

Legacy details parity depends on (all from `rankers/base_ranker.py`):
- **Modifier inputs:** modifiers receive the unmodified model score, not the
  running value.
- **ScoredPlayer rounding:** fields are rounded to 2 dp, but
  `raw_overall_score` uses the unrounded side scores.
- **Ties:** stable sorts, and on equal side scores the high side is pitching.
- **Classification:** `classify()` runs on the *rounded* side scores.
- **Demand breakdown:** written with `set_path` and 2-dp rounding, and only
  when a factor isn't 1.
- **`filter_players`:** a no-op everywhere, so it's dropped.

## Breakdown vs ledger

- **Until the switch:** v2 writes the legacy breakdown tree (same paths, same
  rounding, via `scoring/runtime_components`) so that switching the app is
  byte-identical. The legacy scorers write into that ContextVar store anyway.
  The ledger is built alongside and is the new explanation.
- **After the switch:** the player card shows the ledger (a waterfall). The
  breakdown tree stays for diagnostics until the legacy scorers are gone,
  then it and the ContextVar go too.

## Storage

Schema v3 migration (`db.py`):
- `model_runs`: add `engine TEXT NOT NULL DEFAULT 'legacy'` and
  `manifest TEXT` (JSON).
- `run_results`: add `pre_demand_score`, `pre_demand_rank INTEGER` and
  `ledger TEXT` (compact JSON, a list of `[stage, label, delta, side]`).

Legacy runs leave them NULL. `results_store.result_from_scored` /
`load_results` pass them through.

**Both engines run side by side in the app** (decided 2026-11-05): `engine`
joins the primary key of both tables, which means a SQLite table rebuild in
the migration. A refresh stores runs for both engines, and the API takes an
`engine` argument that defaults to `v2`.

## API and frontend

**An engine toggle in the app, defaulting to v2** (decided 2026-11-05).
The default flips to v2 only once v2 passes its parity gate (2a), so until
then v2 is identical to legacy anyway.
- **GraphQL `RankedPlayer`:** add `preDemandScore` and `preDemandRank`.
- **`ScoreBreakdown`:** add `ledger: [LedgerLine!]!` (`stage, label, delta,
  side, counted`) and `unit`.
- **Optional `rankingRun(source)` query:** returns the manifest.
- **Player detail card (`player-detail-card.ts`):** a waterfall from the
  ledger, grouped by stage, with uncounted lines (the side the player isn't
  judged on) shown dimmed.
- **Draft class table:** a pre- / post-demand toggle for the sort and the
  score column.

## Evaluation and reporting (`eval_rankings.py`)

- **Engine registration:** `ENGINES["v2"]` builds a `Ranker(PROFILES[...])`.
  Current uses the final score; draft uses `pre_demand_score`.
- **`--parity`** (with `--against-engine`): compare *every* field (scores,
  components, best position, type, breakdown leaf by leaf, order) between
  two engines, per pool, with counts and examples of each difference. ✅
- **`--explain ID[,ID…]`:** IDs or names. A player's ledger under each engine
  side by side, with a change column, the score, the pre-demand score and the
  pre-demand → final rank. Lines for the side the player isn't judged on are
  listed separately. A legacy score's ledger comes from the legacy pipeline,
  with a warning if it doesn't reproduce the score. ✅
- **`--signals`:** the signal inventory. For each profile (current, potential,
  draft class) and side, which readers read each rating, flagged when a
  rating has several readers on a side, when a composite and its part are
  both read (Contact = BABIP + Avoid K, Movement = PBABIP + HRA), when OVR /
  POT is read, or when a current profile reads a potential rating. Alternative
  models (fielding positions, SP / RP) count as one reader, and the SP / RP
  Stuff-shift copies aren't reads. Report only, never a failure. ✅
- **Later:** calibration (predicted vs actual WAR by decile) once the value
  layer exists.

## Parity testing

- **Unit (`tests/test_ranking_parity.py`):** for each profile, rank the same
  players with the legacy ranker and v2 and assert identical `ScoredPlayer`
  fields, breakdowns and order. Also assert that every ledger total equals
  `overall_score` (±1e-9) and that the pre-demand fields equal the legacy
  `raw_overall_score` and pre-rank.
  - Data: the seeded OOTP-format class (`tests/e2e_fixtures.make_draft_class_csv`,
    several seeds, including demands and "Impossible") and the snapshot
    fixture (for `overall` / `potential`).
- **Real data:** `eval_rankings.py --engine v2 --against-engine legacy
  --data-dir fly_data --parity` shows "no differences" for current and for
  every draft class 2033–2042.
- **Goldens:** untouched until the switch.

## Fitted layers (phases 3–6)

### Training data (`fitting/datasets.py`)

- **Talent:** archived snapshot ratings (and the end-of-season snapshot for
  2042), joined to `league_stats/<league>/<kind>/<year>.csv` by `player_id`
  and season. Overall split, plus vs L / vs R for platoon. Weighted by PA /
  IP.
- **Development:** draft classes (draft-day ratings) joined to later
  snapshots / stats. Outcome per the decided rule: OVR at 25+, POT before
  that, bust if gone.
- **Validation folds are grouped by season or class,** never random rows, so
  a season can't leak into its own test.
- **The ratings-history gap:** clean ratings ↔ stats pairs exist only for
  2042 until the archive grows, plus 2041 for age-stable veterans. Priors
  carry most of the weight at first.

### How the models are built (decided 2026-11-05)

The talent and development models are **fit from data**, not from your
handcrafted grids. **Your grids' general rules still apply.** They become
constraints and acceptance tests, not training labels:

- **Fixed directions:** monotone constraints in XGBoost, so a higher rating
  never lowers value.
- **Rules suite** (`tests/test_model_rules.py`, run against every fitted
  artifact): the behaviors your grids encode, written as checks rather than
  exact values, in two groups:
  - **Rules:** a model that fails one doesn't ship, whatever its fit metrics
    say.
  - **Hypotheses:** your theories that haven't been tested. They're never
    enforced. `eval_rankings.py --hypotheses` re-checks each against the stats
    (actual FIP- / WAR of matching players vs their peers) and reports whether
    the data supports it and whether the fitted model agrees. A hypothesis is
    promoted to a rule only once the data backs it, and only if you agree.
- **Scale anchors:** your grids' own mappings (batting: 55s ≈ 100 wRC+, 60s ≈
  130, 65s ≈ 160, 70s ≈ 180; SP: 50s = average starter ≈ FIP- 100) are
  sanity checks on the fitted output.
- **Thin data:** until the snapshot archive grows, clean ratings ↔ stats
  pairs exist for about one season. With that little data, the rules and
  monotone constraints do most of the shaping, and the eval tool decides
  whether a fitted model beats legacy. If one doesn't yet, that stage keeps
  the legacy model (per-stage fallback) until the data catches up.

**Talent:** XGBoost on base ratings → runs per PA / per 9 innings, weighted by
PA / IP. Monotone; few rounds, chosen by CV grouped by season.

**Value:** mostly deterministic formulas, with parameters fit from the stats:
- WAR = (runs above average + positional adjustment + replacement runs) ×
  expected playing time / runs per win. This is our own WAR, calibrated
  against StatsPlus's `war` (decided 2026-11-05).
- Playing time (role, stamina, injury proneness → expected games) is fit
  from the stats.

**Development:** quantile models (XGBoost quantile objective, or the
empirical residual distribution around a mean model) give P10 / P50 / P90 of
the outcome. E[max(WAR, 0)] is computed from the quantiles.

**Judgment adjustments:** any of your modifier tables you want kept as
opinion run as a separate `judgment` stage with its own ledger lines.

### Rules suite: draft list from your grids (to confirm)

Hitting (from `batting_attribute_model.py`, restated in BABIP / Avoid K
terms):
1. **Steep drop below skill floors:** BABIP / Contact around 40; Eye 40;
   Power 40, and again at 30, regardless of other skills; Avoid K 35 hurts
   regardless, while 40 can be carried by other elite skills.
2. **Power without contact is discounted:** Power 50 is worth much less
   without good contact skills.
3. **Archetypes are comparable:** balanced, power and contact archetypes of
   equal overall quality land at similar values (the grid's wRC+ ladders).
4. **One weak tool costs less than two:** a single 35 next to 65s still
   rates as an above-average bat.

Pitching (from the SP / RP grids):
5. **All three need to clear a floor:** Stuff, Movement or Control at 30 or
   below means emergency or no value, whatever the others.

Pitching **hypotheses** (untested theories, not enforced; first evidence
from 2040–42 stats, pitchers 27+, FIP- against their own level and season):
- **H1. Elite Movement + Control can carry weak Stuff as a starter**
  (35 / 80 / 80 ≈ a #2/3), but elite Control alone can't (40 / 40 / 80 ≈
  little value).
  - *Evidence (thin, supportive):* 5 MLB starter seasons with Stuff ≤ 45,
    Movement ≥ 55, Control ≥ 65 had a median FIP- of 78 vs 95 for all MLB
    starters. They may be only 2–3 distinct pitchers (McDonald alone: FIP-
    78, 3.9 WAR / 180 IP in 2042, the median for OVR-65 starters). One AAA
    case: 105.
- **H2. Elite Stuff alone isn't enough as a starter** (80 / 40 / 40 ≈ a spot
  starter) **but is probably a good reliever** (your note, 2026-11-05).
  - *Evidence (thin, against the reliever half so far):* 9 MLB reliever
    seasons with Stuff ≥ 65 and Movement, Control ≤ 45 had a median FIP- of
    107 vs 99 for all MLB relievers. AAA: 2 seasons at 70. No such pitcher
    got an MLB rotation look, so the starter half is untested.
- **H3. Relievers lean more on Stuff than starters do:** an elite-Stuff
  reliever with weak Movement / Control is "untrustworthy", not useless.
  Same evidence as H2.

Fielding (from the position grids):
6. **Position floors:** below a position's floor (e.g. SS range / arm /
   error, C framing / blocking / arm, CF range) the fielding value at that
   position is zero.
7. **Harder positions are worth more,** at equal grades.

### Artifacts (`ranking/artifacts/`)

- Each fitted model is saved as JSON (XGBoost's JSON model plus metadata:
  training-data hash, folds, CV metrics, rules-suite result, created at). They're
  committed, small, and versioned by filename.
- The manifest lists the artifact versions used.
- The app loads artifacts at startup instead of training anything. That
  also cuts `model_cache.warm()`'s cost on the 512 MB box once the legacy
  grids are retired.
- Training runs locally through `ranking/fitting/*.py` scripts and prints
  the CV report. A new artifact only replaces the old one if the eval tool
  agrees.

## Order of work and gates

| Step | Work | Gate |
|---|---|---|
| **2a** ✅ | `profiles`, `ledger`, `state`, `results`, `manifest`, `stages/legacy`, `stages/demand`, `ranker`; `ENGINES["v2"]`; parity tests | v2 = legacy on every field, unit and real data; ledger totals exact |
| **2b** ✅ | `--parity`, `--explain`, `--signals` (reads traced, not declared) | report only |
| **2c** ✅ | schema v3 + `results_store` fields; GraphQL ledger / pre-demand fields; card waterfall (behind v2) | goldens unchanged (legacy rows write NULLs) |
| **3** | `RatingsView`; `fitting/datasets.py`; rules suite; hitter talent stage (BABIP / Avoid K / Gap / Power / Eye, fit to stats, monotone) with per-player legacy fallback when BABIP is missing | rules suite passes; eval vs legacy: hitter residuals by rating flatten; watchlist; draft metrics no worse |
| **4** | Movement / Stuff composition fit; pitcher talent stage | same, pitchers |
| **5** | value stage (WAR); retire RP multiplier, batting weights, two-way bonus | calibration vs StatsPlus WAR; ranking metrics |
| **6** | development stage (distributions, E[v], upside dial); judgment stage | draft metrics vs legacy and POT-only baseline |
| **7** | demand stays last; pre / post in the UI | already in place from 2a / 2c |
| **8** | switch `get_ranker_for_method` and `splits.py` to v2; regenerate goldens deliberately; delete `rankers/` and dead code | a full test pass; one release with both engines' outputs saved for comparison |

## Risks

- **Floating-point parity:** handled by keeping the legacy arithmetic for the
  final value and checking the ledger against it.
- **Memory:** tuple ledger lines, per-batch state discarded, and compact JSON
  in the database. Measure peak memory on a full league before the switch.
- **Sparse training data:** about one clean season of ratings ↔ stats pairs
  at first. The rules suite and monotone constraints shape the models, eval
  gates every artifact, and a stage keeps the legacy model until its fitted
  one wins.
- **Unpinned production packages:** `requirements.txt` has no version pins,
  so production installs whatever's newest at build time (possibly numpy 2 /
  XGBoost 3) while local tests use XGBoost 1.7.6. Production scores can drift
  from what the goldens check. Pin versions before the switch.
- **Old class formats:** per-player fallback in every stage, and the eval
  tool's `VELO` stand-in.

## Decisions (2026-11-05)

1. **Web side-by-side:** yes, an engine toggle in the app, defaulting to v2.
   `engine` joins the run tables' primary key.
2. **Local Python:** upgraded to 3.11.16 (pyenv), with the same package
   versions as before. All 166 tests pass.
3. **Artifacts:** committed to the repo (`ranking/artifacts/`).
4. **WAR target:** our own WAR from counting stats, calibrated against
   StatsPlus's `war`.
5. **Models are fit from data, not your grids.** The grids' general rules
   become constraints and the rules suite (see above, to confirm).
