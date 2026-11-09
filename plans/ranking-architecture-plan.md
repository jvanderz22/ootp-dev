# Plan: Ranking redesign

Replace the stack of hand-tuned multipliers with layered models in one unit
(WAR). Each layer answers one question with one stated method. The models are
fit from data, held to the general rules your grids encode. Every step's
contribution is recorded so a
ranking explains itself. It's built in parallel to the current code (engine `v2`
next to `legacy`) and judged by `eval_rankings.py` at every step.

The work that waits on more archived seasons (talent refits with a season
holdout, value calibration, the hypotheses re-check, development fit on
rating growth) is tracked in `plans/ranking-archive-plan.md`.

## Decisions

| Date       | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-11-04 | **Unit is WAR.** Every layer outputs WAR or a WAR distribution.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| 2026-11-04 | **Ranking rule: expected value, with upside favored at equal EV** (see "Uncertainty and the ranking rule").                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-11-05 | **The decision layer is your existing demand modifier, applied as the very last step.** It already handles signability the way you want. Every draft run records each player's value both before and after it. No slot amounts or budget modelling (this replaces the 2026-11-04 slot-based design).                                                                                                                                                                                                                                                                                                                 |
| 2026-11-05 | **The scoring models are fit from data instead of your handcrafted grids, but the same general rules apply.** The grids' rules (skill floors, power needs contact, all three pitching ratings need a floor, ...) become constraints and a rules suite every fitted model must pass. Details and the draft rule list are in `ranking-v2-technical-plan.md`.                                                                                                                                                                                                                                                           |
| 2026-11-04 | **Your tuned values are priors and may stay** (superseded for the attribute grids on 2026-11-05; still holds for the modifier tables). They push things the direction you want. Fitted layers start from them, and explicit judgment adjustments remain as their own visible step.                                                                                                                                                                                                                                                                                                                                   |
| 2026-11-04 | **Build in parallel** (engine `v2`) and compare side by side before switching.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-11-04 | **Current scoring is judged on performance stats**, with OVR as the fallback and the watchlist as a sanity check. **Draft scoring is judged on holding potential**: OVR from age 25, POT now before; gone from the league = bust; baseline = draft-day POT order.                                                                                                                                                                                                                                                                                                                                                    |
| 2026-11-04 | **Batting inputs are OOTP's base ratings** (BABIP, Avoid K, Gap, Power, Eye), not Contact. Contact ≈ ½ BABIP + ½ Avoid K.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-11-04 | The signal inventory is a report only and never fails the suite.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-11-07 | **The rules list is confirmed**, then **the four Power rules become hypotheses**: the Power 40 / 30 floors, "power without contact is much less valuable" and "archetypes land at similar values". The 2041–42 stats disagree with all four (see "Findings so far"). They're reported, not enforced, and re-checked as the archive grows.                                                                                                                                                                                                                                                                            |
| 2026-11-07 | **Hitter talent is built from one rate per rating** (Avoid K → K%, Eye → BB%, Power → HR per contact, BABIP → hits on balls in play, Gap → extra bases per hit), chained into a PA and valued with linear weights fit to the league's runs. It's fit on every level at once with a level term, and committed as lookup tables.                                                                                                                                                                                                                                                                                       |
| 2026-11-08 | **Pitcher rule 5 (a 30 in Stuff, Movement or Control means emergency value) becomes a hypothesis.** The stats can barely test it, and the few cases weren't worthless.                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-11-08 | **Pitchers ship on the fitted model even though OVR disagrees.** The stats back it: held-out runs allowed and career MLB WAR. The OVR / POT outcome looks worse, so **the draft eval now also reports career MLB WAR** next to OVR / POT.                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-11-08 | **v2 ranks on WAR internally but shows points on screen** (the value layer maps WAR back onto a 0–100 display scale).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-11-08 | ~~**Reliever value and playing time are open.**~~ Settled the same day (next row). Plain StatsPlus WAR leaves a reliever at about a third of a comparable starter, and lets playing time weigh too much.                                                                                                                                                                                                                                                                                                                                                                                                             |
| 2026-11-08 | **5b values every player at a full-time role** (607 PA, a starter's 173 IP, a reliever's 73 IP, from the stats), not at expected playing time. **Relievers count their runs at 0.9 of full leverage** (runs saved × (1 + 0.9 × (LI − 1))), with leverage given by talent as an optimal manager would (closer ≈ 2.1–2.5 LI). StatsPlus's own WAR counts about 0.42 of it. This replaces RP ×0.82 / ×0.72. Your judgment: 2–3 relievers in the top 100 and not many more in the top 250. With the role shift in, the prototype on the live league gives 1 in the top 100 and 5 in the top 250 at 0.9 (Moya #53, Sennett #101, Yamada #111), 4 and 5 at full leverage, none at StatsPlus's 0.42; you chose 0.9. Rechecked end to end (with split scoring and the two-way ramp): 0 in the top 100 at 0.9 (Moya #132), 1 at full leverage (#94), 2 only at 1.2; the stats don't support more than full (top-leverage relievers pitch fewer innings: 64 IP vs 78), so **you chose full leverage, 1.0**. A pitcher can start with stamina 40+ and 3+ pitches (95% of MLB starters). |
| 2026-11-08 | **5b open items settled:** starter-capable relievers are valued as starters, at innings set by stamina (35 is borderline, not out); the two-way rule is primary role plus a small share of the secondary role's WAR above replacement; platoon value needs a model of arm slot and pitch-mix profiles before any reliever tilt; injury proneness becomes a blanket development-layer rule (odds of never developing or a shorter career), not a per-season games-lost term. |
| 2026-11-08 | **Defense: your position grids stay the shape; the stats translate them into runs.** StatsPlus `arm` runs are opportunity-driven (poor-range outfielders pile them up; always 0 for catchers), so they aren't fit against. OF assists per chance do track OF Arm cleanly. `opps_0`–`opps_5` are plays by difficulty (routine → impossible), a clean range signal. Infield Arm / Error / Turn DP have no stat, so they come in through the grids and position floors.                                                                                                                                                 |
| 2026-11-08 | **Position floors, as a steep penalty over the last 5 points above the floor** (full credit from floor + 5, half at the floor, nothing a step below): SS IF Arm 45, IF Error 45, Turn DP 45; 3B IF Arm 45, IF Error 40; 2B Turn DP 40; RF OF Arm 45; CF OF Range 55; C Blocking 40, Framing 40. A 10-point ramp was tried first and moved good everyday MLB shortstops with a 50 Error or Turn DP off SS.                                                                                                                                                                                                            |
| 2026-11-08 | **Your grids are the cross-position scale.** The best position is the highest floored grid score (as in legacy), and one line, the same at every position, turns that grid into fielding runs including the position adjustment. A 70 Range outfielder is worth more at CF than at LF, even though he'd be further above the LFs. Per-position curves (each matched to its own regulars) were tried first and valued good CFs and SSs more at easier spots.                                                                                                                                                          |
| 2026-11-08 | **Exports without BABIP are scored on the BABIP Contact implies** (`RatingsView.implied_babip`): 2 × Contact − Avoid K, held to 20–80, since OOTP's Contact is about half each. On the live snapshot, where both are exported, it's within 5 of the real BABIP for 99% of hitters (current) and 95% (potential). No draft-class export has BABIP, so every class hitter had been on the legacy batting grid. Hitters only, 2033–40 classes: rank against outcome beats the grid in every class (pooled 0.459 → 0.467). The career-WAR top 100 drops in 2034–35, mostly Russ Knight (a contact bat with Power 45). The ledger says "BABIP from Contact". |
| 2026-11-08 | **Below replacement, a hitter is valued at his full-time WAR, and only his personality counts, in reverse.** A hitter below replacement on both sides gets no starts. He was floored at 0 WAR, so ~330 per class and ~11,600 on the live board tied at 50.0. Now he keeps his full-time WAR, so the bottom stays ordered, and that's his final score. The development factors (work ethic, intelligence, durability) and the legacy personality modifiers divide the deficit instead of scaling value above replacement, so good makeup shrinks it. Age, draft, demand and floor factors still count only above replacement. Pitchers' negative WAR follows the same rule. |
| 2026-11-08 | **CF is graded on Range, in v2 only** (`fielding_talent.cf_grid`; legacy keeps its grid). MLB CF zone runs are nearly all Range (+2.2 runs a point; Arm −0.1, Error +0.2), and the legacy grid stepped evenly in Range while paying a good Arm and Error up to +19. Your rule: Range 60 or less can't start in CF, 65 is playable but below average, 70 good, 75 very good. Arm adds or takes a grid point per 5 outside 45–60, Error takes one per 5 at 30 or below. Calibrated runs by Range 60 / 65 / 70 / 75: −18 / −5 / +7 / +13 (MLB actual −22 / −7 / +8 / +11). The architecture behind it (hand-labelled grids as the cross-position scale) is up for revisiting (TODO below). |
| 2026-11-08 | **Baserunning assumes optimal managing:** steals at the attempt rate the most aggressive teams use for that Stealing grade, valued at zero (not negative) for runners below break-even. Slow runners still lose extra-base runs. Not tuned on opportunity-based stats.                                                                                                                                                                                                                                                                                                                                               |
| 2026-11-08 | **PBABIP has little impact.** The pitcher model keeps a third of the fitted PBABIP → hits-in-play effect, and a rule enforces that PBABIP 35 → 65 is worth at most half of the same step in Stuff, Control or HRA. MLB BABIP spread is about what luck alone gives, so the stats can't size it.                                                                                                                                                                                                                                                                                                                      |
| 2026-11-07 | **Until the value layer, fitted batting goes onto the legacy points scale by matching percentiles** over the league's hitters. Hitters keep their legacy points distribution, so phase 3 only reorders hitters among themselves; the hitter-vs-pitcher balance moves in phase 5 (WAR).                                                                                                                                                                                                                                                                                                                               |

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

| Layer              | Question it answers                                                                                                                                                         | Method                                                                                                                                          | Replaces                                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **1. Talent**      | ratings → expected rate stats (hitters: runs per PA from BABIP / Avoid K / Gap / Power / Eye; pitchers: runs per 9 innings from base components; fielding runs by position) | regression fit to StatsPlus season stats against ratings, weighted by PA / IP, monotone in each rating, held to the rules suite from your grids | the attribute grids, SP / RP pitch mix, velo, HR risk, hit profile, handedness                  |
| **2. Value**       | rates → WAR for a season                                                                                                                                                    | expected playing time (role, stamina, injury proneness as expected games lost) + positional adjustment + replacement level                      | RP ×0.82, the 0.73 / 0.22 / 0.05 weights, injury multipliers, two-way bonus                     |
| **3. Development** | a prospect → distribution of peak WAR                                                                                                                                       | fit on past classes + archived snapshots: rating growth given age, POT, work ethic, intelligence, scouting accuracy                             | age, personality, secondary personality, scouting accuracy, the draft overall / Stuff modifiers |
| **4. Decision**    | draft board: how does signability change it?                                                                                                                                | your `DraftDemandModifier`, unchanged, run last on the pre-demand order (see "Draft decision layer")                                            | nothing: it moves to the end                                                                    |

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
  | ------- | ------------ | ------------- | ----------- |
  | 40–45   | −6.8         | −1.4          | +2.3        |
  | 50–55   | −6.7         | +3.0          | +6.4        |

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
    current Contact _and_ Avoid K, so current Avoid K counts twice too.
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
  | ----- | ---- | ------ | ------ |
  | MLB   | 522  | 0.693  | 0.583  |
  | AAA   | 373  | 0.563  | 0.506  |
  | AA    | 292  | 0.606  | 0.532  |
  | A     | 339  | 0.503  | 0.523  |
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

    | Level, role | Rows | Fitted         | Legacy         |
    | ----------- | ---- | -------------- | -------------- |
    | MLB RP      | 353  | 0.500 \| 0.433 | 0.385 \| 0.318 |
    | MLB SP      | 251  | 0.477 \| 0.335 | 0.446 \| 0.374 |
    | AAA RP      | 231  | 0.306 \| 0.234 | 0.287 \| 0.184 |
    | AAA SP      | 204  | 0.418 \| 0.312 | 0.385 \| 0.291 |
    | AA RP       | 185  | 0.228 \| 0.187 | 0.258 \| 0.228 |
    | AA SP       | 143  | 0.387 \| 0.323 | 0.350 \| 0.291 |
    | A RP        | 244  | 0.384 \| 0.272 | 0.270 \| 0.194 |
    | A SP        | 145  | 0.243 \| 0.186 | 0.150 \| 0.139 |

    The MLB SP charged-runs gap is within noise: legacy's SP score doesn't
    correlate with the fitted model's residual (−0.02), and neither do
    stamina or pitch count.

  - **No support for the other legacy talent factors.** Extreme-GB starters
    allow 3.4% _more_ runs than their components predict (legacy gives them
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

  - **PBABIP shrunk to a third (2026-11-08).** At full strength PBABIP
    35 → 65 moved a starter's ERA by 0.63, about Control's 0.69, though only
    0.08 spearman with actual MLB BABIP. Now it's 0.21. Cross-validated MLB
    holds (SP 0.477 → 0.482, RP 0.500 → 0.498); AA / A drop about 0.01,
    where PBABIP still carried some signal.
  - **Player by player against MLB 2040–42** (spearman, legacy → v2):
    starters (83, 250+ IP) vs FIP 0.669 → 0.709, vs ERA 0.630 → 0.602, vs
    WAR per 180 IP 0.697 → 0.747; relievers (119, 100+ IP) vs FIP 0.521 →
    0.604, vs ERA 0.317 → 0.387, vs WAR per 65 IP 0.510 → 0.610. Modeled vs
    actual rates: K 0.79, BB 0.85, HR per contact 0.66. Page:
    https://claude.ai/artifact/YU9irL57XgK14YLAHuf3Lj

- **Phase 5a, fielding and baserunning talent (2026-11-08).**
  - **Fielding stats:** zone rating + framing only. StatsPlus `arm` runs
    follow opportunities, and assists depend on chances. True fielding
    spread per season (SD × √ year-to-year r): C 6.6, 1B 3.9, 2B 12.0, 3B
    5.2, SS 12.8, LF 8.4, CF 13.3, RF 9.7 runs.
  - **Position adjustments from StatsPlus's own WAR** (runs a season against
    the average of all nine): C +9.2, 1B −6.2, 2B +4.0, 3B +3.7, SS +6.0,
    LF −3.5, CF +2.3, RF −3.3, DH −12.3; 0.109 WAR per fielding run.
  - **One line fits as well as eight:** fielding value = −11.5 + 0.362 ×
    floored grid (R² 0.59 vs 0.58 for per-position curves). A grid of 0
    lands at −11.5, next to DH's −12.3, without being forced there. Your
    grids rate 3B regulars about 5 runs below their stats + adjustment, and
    CFs about 4 above.
  - **Player by player against MLB 2040–42** (spearman, prod → 5a): picks
    the position he plays most 198 → 197 of 311 regulars; fielding points vs
    actual runs + adjustment 0.801 → 0.803; baserunning vs runs per 600 PA
    0.830 → 0.868; whole score vs WAR per 600 PA 0.589 → 0.590. Fielding is
    mostly your grids plus the floors; its change is the unit (runs), which
    5b needs. Page: https://claude.ai/artifact/MmBdj6gJuiFSvvZkrqwQ1X
  - **Baserunning:** extra bases (UBR) from Speed and Baserunning; steal
    success rises with Stealing (52% → 84%); aggressive teams attempt about
    1.25× the league curve with no loss of success; +0.2 a steal, −0.4
    caught, break-even about 67%. Cross-validated against baserunning runs:
    MLB 0.784 vs legacy 0.743, AAA 0.641 / 0.591, AA 0.670 / 0.660, A 0.661
    / 0.610.
  - **Both prod and 5a put many everyday 3Bs at 2B (14) and LFs at RF
    (17):** that's the grids' call, not the model's.
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
    - 0.49·`K P`, matching StatsPlus. The snapshot uses the same names.
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
  - Since 2026-11-08 that's nobody with Contact and Avoid K: no draft-class
    export has BABIP (`HT` is height), so every class hitter had been on the
    legacy grid. They're now scored on the BABIP Contact implies (decision
    row).
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
- ✅ Rules: pitcher rule 5 is now a hypothesis. One enforced pitching rule
  since 2026-11-08: PBABIP matters least. Hypotheses: H1 holds (Movement + Control carry weak Stuff;
  Control alone doesn't); H2 isn't supported (80 / 40 / 40 is a decent
  starter, 92, and a so-so reliever, 94); H3 holds only barely (Stuff is
  worth −16.0 in relief vs −15.9 starting, since role is an additive term).
- The test fixtures' BABIP / HRA / PBABIP are now derived from Contact and
  Movement, as in a real export. The legacy goldens are byte-identical.

**5a. Talent layer, fielding and baserunning: done** (2026-11-08)

- ✅ `ranking/fielding_talent.py` (artifact `fielding_talent_v1.json`, fit by
  `python -m ranking.fitting.fielding_talent --data-dir fly_data`): your
  grids, floored, pick the position; one line prices it in runs including
  the position adjustment. Legacy's utility bonus on the floored grids.
- ✅ `ranking/running_talent.py` (artifact `running_talent_v1.json`, fit by
  `python -m ranking.fitting.running_talent --data-dir fly_data`): extra
  bases plus steals under optimal managing, runs per 600 PA.
- ✅ Both bridged onto legacy fielding / running points until 5b. Ledger
  lines: "fielding talent (POS, runs, value with position)", "utility",
  "baserunning talent (runs)".

**5b. Value layer** (in design, 2026-11-08)

- Playing time, the injury → games model, positional adjustment and
  replacement level → WAR.
- Framing (decided 2026-11-08): value each player at a full-time role
  (everyday player, full-time starter, full-time reliever), not at his
  expected playing time; relievers' runs count at full leverage (1.0, was 0.9) in
  place of RP ×0.82 / ×0.72; two-way = primary role plus a small share of the
  secondary role's WAR above replacement (confirmed; the share is set
  below, under the two-way TODO).
  - Injury proneness is not a per-season games-lost term here: it moves to
    the development layer as a blanket rule (see phase 6).
- Pitcher role (2026-11-08):
  - **Built: Stuff shifts by role with the pitch mix, measured in the game.** The
    SD org's 145 pitchers were exported once all set to SP and once all set
    to RP (`fly_data/role_reference/`, gitignored). Only Stuff changes:
    Movement, Control and the pitch grades are identical. As a reliever,
    Stuff rises 0 / 5 / 10 points (83 / 57 / 5 pitchers; mean +2.3 current,
    +5.0 potential), the same whichever role he was listed in. OOTP's
    formulas, fit on the pairs (best, 2nd, 3rd, 4th pitch):
    starter Stuff = −0.6 + 0.47 / 0.28 / 0.07 / 0.03, reliever Stuff =
    −3.1 + 0.55 / 0.35 / 0.03 / 0.01 (R² 0.96 each). The shift (reliever
    minus starter) = −2.50 + 0.077 / 0.076 / −0.039 / −0.020 for current
    Stuff, −3.59 + 0.072 / 0.137 / −0.050 / −0.055 for potential
    (cross-validated error 2.3 / 2.5 points against 2.8 / 3.5 for a flat
    shift; ratings round to 5). Velocity adds almost nothing. A listed RP
    scored as a starter loses the shift; a listed SP in relief gains it.
    The stats agree: listed relievers who start strike out ~1% fewer per BF
    than the model expects, and listed starters in relief ~1% more. Without
    the shift, 16 listed relievers ranked in the top 100 as starters; with
    it, 6. In the talent layer (`PitcherTalent.role_stuff`): a reliever scored
    as a starter loses the shift plus a margin, the 75th percentile of what
    the formula misses (1.0 current / 1.75 potential), since you'd rather
    take too much Stuff away than too little. The pitcher fit moves each
    line's Stuff into the role it was pitched in, and refits read the two
    exports from `<data dir>/role_reference/`.
  - **Platoon weighs more on starters: needs research first** (2026-11-08).
    Build a model of platoon value from profiles of arm slot and pitch mix
    before setting any reliever tilt (the 10-point tilt proposal is shelved).
    What's known: the handedness mix faced follows the throwing hand (RHP
    45% / LHP 25% LHB as starters, 43% / 27% as relievers, MLB lines
    2030–2042), and AI managers barely tailor it to a pitcher's own splits
    (< 0.1% per rating point). OOTP's combined ratings are already that
    blend of the splits (vL weighs 44% for a RHP, 28% for a LHP).
  - **Built: current pitchers are scored on their vL / vR splits**
    (2026-11-08). Each side's events are scored apart and blended at the
    mix his role and throwing hand face (`platoon_mix` in the pitcher
    artifact), so a weak side the rounded combined rating hides costs what
    it should: Ben Hodge (LHP, Stuff 40 combined but 35 vs RHB) goes from
    4.55 to 4.76 ERA as a starter. Potential and draft ratings have no
    splits and stay on the combined ratings until the arm slot / pitch-mix
    model exists. On the live board pitchers move a median 30 places (90th
    percentile 119); the leverage map is refit on the same scoring.
  - **Starter-capable relievers are valued as starters (option A, decided
    2026-11-08)**, at innings set by stamina: starters with more stamina
    pitch deeper (5.0 IP a start at 40–44, 5.8 at 70+). No hard cutoff at
    40: 35 stamina is borderline viable and shouldn't be totally discounted
    (it's 5% of MLB starters), so it gets the bottom of the innings curve;
    3+ pitches still required.
- Retires RP ×0.82, the batting / fielding / running weights and the two-way
  bonus.
  - TODO: figure out _something_ for the two way bonus. I don't want a decent batter to end up
    ranked above better batters just because they could be a decent AAA pitcher. We need a way to weight two way players so their secondary skillset doesn't give too much of a boost
  - **Built (2026-11-08): the share ramps with the secondary side's WAR.**
    Nothing at 1.75 WAR or less (a back-end starter, a bench bat), the
    full 20% from 2.5 WAR (about a league-average full-time starter), a
    straight line between (`ranking/value.py` `two_way_share`). A balance
    of counting from replacement and from average: Pat Farrell (2.7 WAR as
    an SP) keeps +5.5, Wallick / Mullins +6.9; Russ Knight (1.0) and Jeff
    Davis (0.6) lose theirs, Chris Grady (2.2) gets +2.9, Ben Hodge (1.8)
    +0.3.

**6. Development layer**

- **Injury proneness as a blanket rule (decided 2026-11-08).** Not games lost
  in a season, but the odds that injuries keep a player from ever developing,
  or end his career earlier (out of the league by 27 instead of 32). Fit
  Prone against career outcomes (reaching MLB, peak WAR, last season) on
  past classes and the archive; it punishes fragile and rewards durable
  players in the potential and draft class rankings.

- Distributions of peak WAR from past classes and the archive.
- Retires the age, personality, scouting accuracy and draft modifiers, keeping
  your values as priors / judgment.
  - I don't think there's a better way to do this, but happy to be wrong here
  - Age = more development runway (players get less good and have less time to TCR the older they are)
  - Good Personality = more chance to meet potential
  - Good leadership = better to have in org even if they don't have high likelihood of making ML
  - Accuracy = hedging on unknowns, don't want to take risks on someone we have low confidence in
- **Built (2026-11-08): makeup and durability factors** (`ranking/development.py`,
  evidence from `python -m ranking.fitting.development --data-dir fly_data`).
  Each 2033–2042 draftee is scored by v2 on draft day (model lines only) and
  on the 2042 snapshot (current ratings at 25+, potential before, 0 once
  gone; players who leave almost never had an MLB career: 8% played, 0.6%
  had a 2-WAR season). With potential WAR held fixed, on classes 2033–36:
  - Work ethic H ×1.24 / L ×0.75, intelligence H ×1.17 / L ×0.94, Fragile
    ×0.87 on value now; career MLB WAR (2033–34) agrees and is steeper
    (WE H ×1.56, INT H ×1.57, Fragile ×0.28). Durable is ×1.0–1.06, below
    the legacy pitcher bonus (×1.11).
  - Makeup matters most for 1–4 WAR prospects and about half as much at
    4+ WAR (WE H ×1.16, INT ×1.0), the taper you asked for: you don't want
    an otherwise mediocre prospect with maxed makeup flowing above a true
    generational talent without it.
  - In use (judgment, the conservative end): WE H ×1.25 / L ×0.75, INT H
    ×1.15 / L ×0.95, Fragile ×0.75, Wrecked ×0.6, Durable ×1.03, Iron Man
    ×1.05, at full weight up to 2.5 potential WAR, tapering to 35% at 5+.
    They scale WAR above replacement, one ledger line each ("Development"),
    and replace PersonalityModifier and the batter / pitcher injury
    modifiers wherever potential ratings are read.
  - Draft eval vs the 5b commit: about neutral on OVR / POT and career WAR
    (the top 100 gains in 2036–37, loses a little elsewhere); in the 2042
    class the top 13 hold, and makeup moves prospects up to ~50 places
    inside the top 150.
- **Age stays on your legacy table (2026-11-08)**, with the legacy draft-day
  current-ratings modifiers as its balance for older prospects. The data
  says older draftees realize less (22 vs 18: ×0.6 on value now) and that
  current ratings earn some back (×1.12 per WAR of current-ratings value;
  ready 21+ draftees realize 28% vs 20% raw), but the two outcomes disagree
  on age (career WAR: ×2.5, as college picks reach MLB sooner), so fit age
  and readiness together once the archive can measure peak value.
- Scouting accuracy stays judgment: nearly every draftee in this league is
  "Very High", so there's nothing to fit. Leadership stays judgment too
  (org value beyond MLB outcomes).
- **Outcome distributions: tested and dropped (2026-11-08).** You care about
  P90, not P10 (the bottom 25–50% of prospects bust). A P90 curve against
  the board's pre-demand value was well calibrated (7–15% of a held-out
  class above it), but it rises with the board value, so it never reorders
  anyone, and it flattens at 3.6 WAR above a value of 5 (only ~90 past
  draftees that high), so the top of a class all read the same. P75 orders
  2+ WAR prospects like P90 (spearman 0.95), and ranking by P75, P90 or E[v]
  picks no better top 100 than the board value (1.61–1.65 vs 1.65 mean
  WAR). A bust-chance column was skipped for the same reason. The ranking
  stays on the board value; revisit once the archive adds more top
  prospects' outcomes.
- **Stored runs are rescored when the model changes (2026-11-08).** A run
  records the version of the scoring code, artifacts and grids that made it
  (`ranking.manifest.model_version`); one made by another version is stale
  and re-scored on its next read, so a deploy shows up without reprocessing
  classes by hand.
- Platoon items from `my-todo.txt` land here and in talent (vs L / vs R
  ratings per profile).
  - This should apply to the overall model only because undeveloped players don't have enough
    distinction in their overall ratings to know where they'll land and potentials aren't
    split by platoon , but we still need modifiers for expected platoon value for the potential and draft class players
  - TODO: a pitcher's arm slot and his specific pitch mix drive his platoon
    ratings, so expected platoon value for potential and draft class pitchers
    should come from those (which pitches play against which side, and how
    slot changes it), fit against the current split ratings.
- **Splits: what the data says (2026-11-08).**
  - Hitters' combined ratings are OOTP's blend of their splits at about the
    share of PA each batting hand takes vs LHP (R 30%, S 26%, L 23%; all
    MLB PA 26.5% vs LHP). The batting model doesn't under-predict lefties at
    any level (MLB L +0.4 / R −0.8 runs per 600 PA), and left-handed draft
    prospects realize ×0.90–0.95 of what righties do at the same potential:
    the handedness edge is in the ratings, potential included, so the
    legacy ×1.04 lefty bonus double-counts. Switch hitters beat the model by
    ~3 runs a season in MLB but not in AAA / AA.
  - Pitchers' split gaps (same-handed minus opposite-handed batters) are
    predictable from arm slot, velocity and pitch mix: R² 0.49 Stuff, 0.45
    Movement, 0.44 HRA, 0.56 PBABIP, 0.16 Control (hand alone: ~0).
    Sidearm +3 and submarine +5 Stuff gap, over the top −1; a good
    changeup closes it (60 CH ≈ −2.8), a good slider widens it (60 SL ≈
    +4.6); the gap grows with the rating. But in this league the AI doesn't
    act on splits: big-split pitchers don't underperform their combined
    rating (MLB 5+ gap: −2.5 runs per 600 BF, i.e. better), and drafted
    starters with big predicted gaps aren't moved to relief more often
    (odds ratio 0.98 per SD, with stamina 0.82 and pitch count 0.89 doing
    the moving) nor wash out more.
  - The model is for you, and you platoon: so value comes from your usage,
    not the AI's (your call, 2026-11-08).
- **Built (2026-11-08): hitters are platooned the way you use them.**
  - Current hitters are scored on their vL / vR splits, blended at their
    hand's PA mix (`platoon_mix` in the hitter artifact; wRC+ moves up to
    ±7 where the rounded combined rating hid a weak side). Hitters without
    splits (potential, draft) get expected ones: per hand and rating, OOTP's
    weight on vL and the vL − vR gap as a line in the rating's level
    (`expected_splits`; a 50 lefty is ~6–8 points worse vs LHP, a 50 righty
    ~2–4 better, switch hitters about even). Fractional ratings read along
    the line between the tables' 5-point steps (reading the steps instead
    cost lefties 3 wRC+).
  - Against each pitcher hand, a hitter starts in proportion to his WAR rate
    on that side next to an average regular's: every start at average or
    better, none at replacement (your choice: near average, soft). What he
    loses is a "platoon (starts x% vs RHP, y% vs LHP)" ledger line; a
    regular on both sides has none. An all-50 left fielder as a prospect:
    lefty +1.01 WAR (starts 76% vs RHP, 0% vs LHP), righty +0.73 (37% /
    88%), switch +0.64; from 60 up they play every day and come out level.
  - Replaces `BatterHandednessModifier` in every v2 profile. Switch-hitting
    prospects (potential, draft) keep your ×1.07 as a lineup-flexibility
    factor on the batting side, tapered like the makeup factors; current
    switch hitters don't need it (their real splits carry it).
  - Board effect vs the 5b–6 commits: hitters' share of the top 100 barely
    moves; lefties drop a median ~27 places in the top 500 (the ×1.04 gone),
    switch hitters −55 on current ratings, −6 as prospects.
- **Built (2026-11-08): pitchers' matchups follow their split.**
  - A pitcher's split is how much better he is against same-handed batters
    than opposite-handed ones, in runs index, in each role. Current pitchers
    use their real splits. Potential and draft pitchers get one predicted
    from hand, arm slot and pitch mix: a ridge fit on the snapshot's 7,078
    pitchers with splits (`split_gap` in the pitcher artifact,
    cross-validated R² 0.41, 0.47–0.51 for relievers). Sidearm adds ~6
    points, sinker and slider grades widen it, a good changeup closes it.
    Velocity added nothing, so it's left out (old classes export it in
    another format anyway). |split| percentiles: median 0.7, 90th 16,
    95th 20.
  - The tilt is a straight ramp: none for an even split, 20% of the batters
    moved at a split of 20 (about the 95th percentile) and above. A reliever
    gets them on his strong side, the way you'd use him: an "RP matchups"
    ledger line. A starter can't pick his batters and lineups stack his weak
    side, so he gets the mirror (your choice over a share-of-value discount,
    which hit big-split aces hardest): an "SP matchups" line. The cost is
    set by the split and the innings, not by how good he is.
  - The better of SP and RP then moves a big-split back-end starter to the
    bullpen. Current pitchers in the top 1000 don't flip: 180 starter
    innings outweigh 73 relief innings. 6 marginal arms in the 2042 class
    do.
  - Board effect: big-split closers gain up to ~0.4–0.8 WAR (Eddie Graham
    268 → 154, Josh Sennett 153 → 83 on current ratings). The biggest-split
    starters lose up to ~0.4 WAR (90th percentile ~35 places; Andy Godwin,
    a 19-point split, −0.26 WAR). Starters in the top 300: 169 → 164
    current, 101 → 95 potential, 149 → 146 in the 2042 class.

**Open TODOs from the 2026-11-08 reviews**

- ✅ **calibrate hitters against pitchers at the top end** (built
  2026-11-08, see below). Found: v2's full-time
  WAR against 2042 regulars' actual WAR (scaled to the role):
  - Starters are compressed: actual WAR runs 1.37× predicted, and actual
    ERA 1.3× predicted ERA (spread 0.92 vs 0.43). The top 10 predicted
    starters are 0.5 WAR low.
  - Innings per start come from stamina only, but better starters go
    deeper: IP / start correlates 0.53 with WAR.
  - Hitters are spread too wide: actual is 0.85× predicted. The top 10
    predicted are 0.6 WAR high, most at CF (−0.65) and SS (−0.41).
  - Relievers' top 10 are 0.6 high.
  - On potential ratings it's worse, because the tables extrapolate past
    what the data covers. Top hitters reach 8–11 WAR at 185–208 wRC+,
    pitchers top out near 8; the top 25 is 88% hitters (legacy 52%), and
    the 10th-best pitcher ranks 62nd. On current ratings the top 25 is 60%
    hitters against 76% in actual 2042 WAR, so the issue is the spread, not
    the share.
  - Proposed: a calibration step in the value layer. Stretch pitchers' runs
    saved, shrink hitters' WAR above average, let IP / start rise with
    talent, and cap or curve the rate tables beyond the rated range they
    were fit on. Fit it on 2042 regulars now (with the caveat that the
    December ratings came after that season), and refit on 2043
    (`plans/ranking-archive-plan.md`).
  - **Built:** the value artifact's `calibration`, fit by
    `ranking.fitting.value` on 2042 MLB regulars as actual = a + b ×
    predicted:
    - wRC+ (b 0.97), baserunning (0.83), and each role's ERA against FIP
      (SP 1.07, RP 1.10);
    - fielding in two parts (2026-11-08, replacing one line at 0.92): the
      runs within a position against MLB zone runs + framing (one stretch,
      1.24, and a level per position: CFs were credited ~6 runs high, 3Bs
      ~6 low), and a shift per position adjustment from regulars' WAR (3B
      −5.6, 2B −3.1, LF −2.0, the rest within a run);
    - the value stage reads them before turning talent into WAR. Leverage
      still reads the talent-scale index, since its map is by talent
      percentile.
  - Diagnosed on the way:
    - Batting was nearly calibrated already.
    - Fielding and baserunning were spread too wide; CF and 2B came out
      too high.
    - The starters' shortfall at the top was mostly innings and the capped
      tables (next TODO), not ERA spread.
  - Regulars after (predicted vs actual, top 10): starters 5.12 vs 5.47
    (were 5.00), hitters 5.19 vs 5.06 (were 5.65). Means now match for both.
  - Relievers' top end is still high (2.85 vs 2.08). Part of that is your
    full leverage: StatsPlus's WAR counts 42% of it.
- TODO: **Brendan Brewer and Randy Intravaia** (SD, AAA) rank far lower in
  v2 than legacy in production (v2 #611 / #632 at 51.0 / 45.3 points,
  legacy #83 / #204). Locally (2042-11 snapshot, current code) they're
  ~2 WAR regulars:
  - current ratings: v2 #516 / #659, legacy #104 / #187;
  - potential: v2 #407 / #89, legacy #252 / #126 (Intravaia's 126 wRC+
    plus high work ethic and intelligence).
  - The production numbers don't match: check which build and snapshot
    produced them, then re-check both on the live data.
  - Brewer (CF, Range 70 / Arm 55 / Error 50; +14 zone runs a season,
    3.6 WAR in 2042) was 1.75 WAR after the split fielding calibration. Of
    his ~12-run gap, ~2 was the legacy CF grid charging his Arm / Error,
    ~4 its Range curve under-crediting every Range-70 CF, and ~6 him
    beating CFs with his ratings. With v2's CF grade (decision above) he's
    2.14 WAR, #376 current.
- TODO: **revisit the fielding architecture.** v2's defense still rests on
  your hand-labelled grids (an XGBoost fit to ~60 rows per position) as
  the shape within a position and the scale across positions; the data
  only sets one grid → runs line and a calibration that can't reshape a
  position's curve. CF showed the grid can be the wrong shape. Options: fit
  each position's curve on its ratings against zone runs (with your rules
  as constraints, as for hitting), keeping the grids only for ratings with
  no stat (IF Arm / Error, Turn DP); or explicit per-position rules like
  CF's.
- ✅ **pitcher ratings at the extremes** (built 2026-11-08, see the end of
  this item). Two cases:
  - **The top is capped.** The pitcher tables go flat where data run out:
    HR per contact at HRA 68, hits in play at PBABIP 63, walks at Control
    73, while the hitter tables keep rising to 75–80. Andy Spinner (Stuff
    60, Control 65, HRA 80) has had five straight 7–9 WAR seasons at a
    2.4–2.8 ERA over 190–228 IP. The model has him at 2.93 ERA and 5.8 WAR,
    behind Tim Webb (Stuff 65, stamina 70; never above 7.1 WAR).
    - Continuing the flat tails at the slope below puts HRA 80 at 0.025 HR
      per contact (Spinner's actual: 0.024) and him at 2.68 ERA. Doing the
      same for hitters overshoots (David Avelar 6.8 → 8.4 WAR against 5.2
      actual), so tails for pitchers only.
    - Even then, no flat pitcher weight puts Spinner first: Webb stays
      above him at every weight. Your anchor (Spinner is the best player in
      the league, in a tier of his own) needs the model to value command and
      HR suppression more against Stuff and stamina. Spinner also goes
      deeper than his stamina says (6.6 IP / start at stamina 55).
  - **The bottom isn't punished.** Henry MacGregor (2042 class, 18, SP;
    Stuff 65, Movement 55, Control 30 potential; OVR 20 / POT 40) is #63
    pre-demand: 4.15 ERA as a starter, 167 IP, 3.3 WAR. The model charges
    his 14.3% walk rate about 0.6 ERA, his Stuff wins most of it back, and
    nothing shortens a wild starter's outings. Pitcher rule 5 (a 30 means
    emergency value) was demoted to a hypothesis on 2026-11-07 because the
    stats can barely test it (30-Control pitchers rarely reach MLB).
    Options: re-promote it as a floor like the position floors, or tie
    innings per start to walks.
  - Then set the pitcher-vs-hitter balance by feel, anchored on Spinner
    (2026-11-08).
  - **Built (your calls, 2026-11-08):**
    - **Tails, pitchers only.** Flat pitcher table tops continue at the
      logit slope of the 15 points below (`extend_tail` in
      `ranking.fitting.pitcher_talent`).
    - **Starters' depth from efficiency.** You asked whether stamina was
      overrated. The data say no: its slope holds at 0.022 IP / start per
      point with walks in the model. What was missing is efficiency: walks
      correlate 0.51 with pitches per inning. Innings per start now fit on
      stamina plus the starter's predicted strikeouts, walks and home runs
      per PA (R² 0.21 → 0.37); per unit of rate, walks −12.9 IP / start,
      HR −18.7, K +0.6.
    - **A Control floor, like the position floors:** full value from 35,
      half at 30, nothing at 25 (`value.control_floor`, a "Control floor"
      ledger line). A floor at 35 zeroed MacGregor (#492), which you
      judged overkill for a potential rating.
    - **No pitcher-vs-hitter weight.** A weight of ×1.10 on starters would
      have put Spinner first; you chose none.
  - Result on current ratings:
    - Spinner is the best pitcher in the league and #2 overall: 6.29 WAR at
      a 2.72 ERA (actual 2.4–2.8), 193 IP. Webb is 6.22, Avelar #1 at 6.84.
    - The top 25 is 52% hitters.
    - MacGregor is #232 in the 2042 class (1.49 WAR).
- TODO: **legacy logic still running in v2 that nobody has decided on**
  (from the legacy coverage review):
  - `BatterHitProfileModifier`, in every v2 profile: never tested, and it
    reads Power and Speed a second time. Test batted-ball type and pull
    tendencies against wRC+ / baserunning residuals, then fit it, keep it
    as judgment, or drop it.
  - `DraftPitcherStuffModifier` (potential, draft): potential Stuff again
    on top of the talent model, the Aliff stacking item. Test it on the
    draft eval or drop it.
  - `PitcherVelocityModifier` (potential, draft): velocity on top of Stuff,
    untested. `ranking.fitting.development` can test it now, potential WAR
    held fixed.
  - Durability is one table for hitters and pitchers. Legacy was much
    harsher on pitchers (Fragile ×0.6 vs ×0.8, Durable ×1.11 vs ×1.035).
    Fit the factors by side.
  - Legacy weighted makeup more for younger players
    (`PersonalityModifier`'s age weight); the development factors dropped
    that without a test. Fit work ethic / intelligence by age band.
  - The knuckleball ×1.15 was dropped without its own test (9
    knuckleballers in the league, 1 in the 2042 class). Check their
    residuals, or accept it as too thin to fit.
  - Minor: `DraftSecondaryPersonalityModifier` counts low work ethic and
    low intelligence among its "bad traits", which overlaps the
    development factors for players with 4+ bad traits.

**7. Decision layer**

- The demand modifier as the last stage, with pre- and post-demand values and
  ranks stored and shown. Ranking by E[v] plus the upside dial.

**8. Switch the app to `v2`**

- Change `get_ranker_for_method`, regenerate the goldens deliberately, and
  delete `legacy`.
- TODO: **rework the org rankings page for v2** (`web/org_rankings.py`,
  `print_org_summaries.py`). A farm system's score is a convex points curve
  summed over its prospects' `model_score`, tuned to the legacy points
  scale: nothing below 58, steep up to 120. Under v2 that score is
  50 + 10 × WAR, so 58 is ~0.8 potential WAR and the curve's weights mean
  something else. Re-express it in potential WAR, e.g. value above a floor
  with the same top-heavy shape, and check the order of systems against the
  legacy page before switching.
- TODO: **the L/R card's split scores** (`scoring/splits.py`) are legacy
  scorers under both engines. Re-run v2's talent and value on each side.
- TODO: **kept modifiers still key off legacy points.** `AgeModifier` and
  `DraftSecondaryPersonalityModifier` weight by the side's model score
  through `RankGradiatedModel`, which v2 feeds the bridged legacy points.
  Re-express those weights in WAR, or keep the bridges, before legacy goes.
- TODO: **what deleting `legacy` must keep:**
  - your grids in `attribute_models/`: the fielding grids are v2's fielding
    shape, and the batting grid is the fallback for exports without BABIP
    (only rows with no Contact or Avoid K since 2026-11-08);
  - the legacy pitcher scorer, for rows without Stuff / Control / Movement;
  - the modifiers v2 still applies;
  - `DraftDemandModifier`.

## Open questions

- ~~**Replacement level and WAR:** StatsPlus's WAR directly, or our own?~~
  Our own from the counting stats, so positional adjustment and replacement
  level are explicit, calibrated against StatsPlus's WAR (2026-11-05).
- ~~**Web app:** a toggle or the eval report?~~ A toggle, defaulting to `v2`
  (2026-11-05).
