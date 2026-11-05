# Plan: Ranking architecture pass

Make each ranking purpose (current, potential, draft class) one declared thing, so
a tuning change happens in one place. Make each player signal (Stuff, velo, pitch
grades, ...) visible wherever it moves a score, so double counting shows up before
it ships. Give every change a standard measurement.

## Why

Fixing the low-Stuff starters (0ce9a72) showed four problems:

1. **Purpose-specific settings live in five places.** The scorers branch on a
   `type` string (`stuff` vs `stuff_ovr`, `get_pitches` vs `get_ovr_pitches`,
   and now the Stuff lift). The draft RP multiplier is a constructor argument
   (`RP_OVERALL_MODIFIER - 0.1`). Each ranker has its own modifier lists and
   `two_way_player_threshold`. `DraftClassRanker.aggregate_pitcher_batter_scores`
   copies the base version just to change 1.8 to 2.2. `splits.py` kept a hand
   copy of the current modifier list until today. `model_cache.warm()` hardcodes
   every (type, rp_multiplier) pair.
2. **There are two layers of hand-tuned multipliers with no rule about what goes
   where.** The scorers apply pitch mix, stamina, GB type, HR risk, knuckleball,
   the SP↔RP Stuff translation and the RP multiplier. The rankers then apply
   velo, draft Stuff, draft overall, age, personality and more. Nothing records
   which ratings each factor reads. On the draft side, Stuff affects a pitcher
   five times: the SP model, the pitch mix, velo, `DraftPitcherStuffModifier`
   and `DraftPitcherOverallModifier`. Aliff (2039, model #56, taken #19) takes
   ×0.93 twice from that stack.
3. **There's no standard way to evaluate a change.** Today needed a scratch
   script. `print_evals.py` / `eval_model.csv` exist but don't measure against
   outcomes, and the past classes would allow that:

   | class | joined to today's snapshot | spearman(model rank, OVR now) |
   |---|---|---|
   | 2034 | 705 / 1184 | 0.52 |
   | 2036 | 940 / 1184 | 0.52 |
   | 2038 | 1142 / 1183 | 0.59 |
   | 2040 | 1216 / 1217 | 0.37 |
   | 2041 | 975 / 975 | **0.00**: look into this |

4. **Results come back as loose lists, and the breakdown goes through a side
   channel.** Scorers return positional lists (`[score, sp, rp]`, a 5-item
   list for batters). The breakdown is written through a ContextVar
   (`write_runtime_component`) with string paths. Modifier names are read with
   `__name__` on the pitcher side but `__class__.__name__` on the batter side, so
   an instance modifier on the pitcher side would crash.

There's also dead code: `PitcherScorer.apply_adjustment` (commented out),
`Pitcher/BatterDistanceFromOverallModifier` (unused), the one-player
`calculate_*_score` / `calculate_rank_adjusted_score` paths, and no-op
`filter_players` overrides.

## Target shape

```
GamePlayer
  └─ RatingsView(profile.ratings)        current | potential: one place that picks *_ovr vs potential
       ├─ attribute models (XGB)        "what is this skill set worth" (hand-labeled grids)
       ├─ role value (scorers)          pitch mix, stamina, GB/HR, SP↔RP, fielding aggregation
       │                                 parameterized by profile.role
       ├─ context modifiers (pipeline)  age, scouting, personality, injury, draft development
       ├─ aggregate                     two-way bonus from profile.aggregate
       └─ rank modifiers                demand
```

**`ScoringProfile`**: a frozen dataclass, one for each of `CURRENT`, `POTENTIAL`
and `DRAFT`, holding:

- `ratings`: `"current"` | `"potential"`
- `role`: `rp_multiplier`, `sp_pitch_grade_lift`, SP→RP Stuff deltas, ...
  (the constants that live in `pitcher_scorer.py` today)
- `modifiers`: `shared` / `batting` / `pitching` / `rank` tuples
- `aggregate`: two-way threshold and bonus

`BaseRanker` and its three subclasses become one `Ranker(profile)`. `get_ranker`
maps a method name to a profile. `splits.py` scores with
`CURRENT.without(BatterHandednessModifier)`. `model_cache` keys on the profile,
and `warm()` loops over profiles.

**Signal inventory**: each modifier and role factor declares `reads = {"stuff",
"velocity", "pitch_grades", ...}`. A report (part of the eval tool, not a
test) prints, for each profile, every stage that reads each signal, and marks
signals read in several places. It never fails anything: some stacking is
deliberate, e.g. velo and pitch count for draftees. It would have shown Stuff
on current (model + pitch mix + velo) and still shows it on draft today.

**Typed results**: scorers return small dataclasses (`PitcherResult(score,
starter, reliever, factors)`) instead of lists. The ranker builds the breakdown
from returned `factors`, with no ContextVar. This one's optional: the breakdown
works today, so do it only if phase 2 makes it cheap.

## Phases

### Phase 0: evaluation harness (no score changes)
**Status (2026-11-04): built.** `eval_rankings.py` + `eval_watchlist.csv` +
`tests/test_eval_rankings.py`. `--against REF` (git worktree) and
`--against-engine NAME` print every metric as `old → new`. It has the `current`
and `draft` profiles; `potential` isn't built yet. A full run takes ~8 s, and
~18 s with `--against`. Still to do:
- **Data lives on Fly.** New class datasets (2042 onward) and the live snapshot
  are on the deployed app's volume (`DATA_DIR=/data`). A copy is in
  `fly_data/` (git-ignored, pulled 2026-11-04), laid out like the volume.
  `eval_rankings.py --data-dir fly_data` reads its snapshot and lays its
  classes over the local ones; Fly's raw 2042 export replaces the local
  processed copy. To refresh it (the machine auto-stops, so start it first):

  ```
  fly machine start 82543df731e478 -a ootp-draft
  fly ssh sftp get -a ootp-draft /data/league_snapshots/yfmlb/players.csv fly_data/league_snapshots/yfmlb/players.csv
  fly ssh sftp get -a ootp-draft /data/datasets/<class>.csv fly_data/datasets/<class>.csv
  ```

  The volume also has a second league, `wbf` (snapshot plus `wbf-2121-draft`),
  pulled too. Use `--league wbf`.
- `current` metrics use the MLB + AAA pool. Watchlist players are scored
  wherever they are now (McDonald and Perello are offseason free agents).
  Putting every FA in the pool swamps it with released low-OVR arms.
- First live run, against the commit before 0ce9a72: SP 0.884 → 0.887,
  RP 0.849 → 0.846 (likely velo dropped for RPs too; watch it), McDonald
  36.0 → 45.2.
- Classes before 2039 come from older game versions with different export
  formats. For example, they have only `VELO` (current velo) and no `VT`, and
  the app doesn't support them, which is expected. The eval tool stands in
  `VELO` so they can still be scored. Keep that in mind when reading their
  rows.

Original spec:
- Turn the scratch `sp_eval.py` into `eval_rankings.py`:
  `--profile current|potential|draft`, `--league` / `--classes`, and
  `--against <git-ref>` to compare two versions.
- Metrics:
  - Current: performance stats (FIP / WAR) for players with enough IP / PA,
    in-game OVR as the fallback. Report the residual grouped by attribute
    (Stuff, Control, velo; Contact, Power, ...) for each position group. This
    needs a StatsPlus stats pull, which the client doesn't have yet.
  - Draft: success means holding your potential, not becoming a star. A
    45/50 player taken at #50 beats a 35/35 one taken at #200. Outcome =
    OVR once the player is **25+**, POT now before that. In the `yfmlb`
    snapshot, 81% of 25-year-olds are within 5 of POT (26: 95%, 22: 45%), so
    an 18-year-old draftee is judged on OVR after ~7 years and a 22-year-old
    after ~3. Players who have
    left the league count as busts; don't drop them. Measure against
    **ranking by draft-day POT** as the baseline, compared before the demand
    adjustment:
    - whole class: model vs POT-only
    - within the same draft POT: does the model order similar prospects correctly?
  - Rank-movement summary and score-change percentiles between two versions.
- `eval_watchlist.csv`: players you know the model misses (McDonald, Perello,
  Aliff, ...), each with the direction you expect. Every run reports them.
- First pass (2026-11-04, outcome = POT now, players still in the league only):

  | class | whole class: model | whole class: POT-only | within same draft POT: model |
  |---|---|---|---|
  | 2034 | 0.42 | 0.43 | 0.19 |
  | 2035 | 0.39 | 0.48 | 0.15 |
  | 2036 | 0.37 | 0.48 | 0.15 |
  | 2037 | 0.43 | 0.46 | 0.12 |

  The model adds signal within a POT level but loses to plain POT across
  levels: its calls to rank a lower-POT player over a higher one don't pay off
  on average. Classes from 2040 on are circular (POT has barely moved). The
  2041 "0.00" on OVR is just undeveloped draftees, not a bug.

### Phase 1: profiles + one Ranker, built in parallel
Build the new architecture next to the old one rather than in place, so results
can be viewed side by side. The old code stays the default until you switch.
- Put the new code in its own package (e.g. `ranking/`) with `ScoringProfile`,
  `RatingsView` and the generic `Ranker`. Reuse the attribute models and
  modifier classes; don't copy them. `rankers/` and the `type ==` branches in
  `scoring/` stay untouched.
- Register it as engine `v2` in `eval_rankings.ENGINES`.
  `eval_rankings.py --engine v2 --against-engine legacy` is the side-by-side
  view.
- **Gate**: `v2` matches `legacy` exactly ("no scores changed" for every
  profile) before anything is tuned on it. The goldens keep pinning `legacy`.
- Then switch the app to `v2` (one place: `get_ranker_for_method`). The goldens
  must stay byte-identical, then delete `rankers/` and the dead code listed
  above.
- Open: should the web app also show both side by side (e.g. a per-league
  toggle), or is the eval report enough?

### Phase 2: signal inventory + typed results
- Add `reads` declarations and the signal inventory report.
- Make scorer results dataclasses. Building the breakdown from returned factors
  is optional.
- **Gate**: no scores change, against the previous commit (`--against`).

### Phase 3: tuning on top (score changes, one at a time)
Each change gets an eval run against the previous commit and a golden regen in
the same commit.
- Draft, across POT levels: find which modifiers drive the model's departures
  from POT order, since those calls lose to POT-only on average (see phase 0).
- Draft Stuff stacking (Aliff): fold `DraftPitcherStuffModifier` and the Stuff
  part of `DraftPitcherOverallModifier` into one factor.
- RP side: the RP pitch maps grade raw pitch grades the same way SP did.
- Base SP grid: review the command-arm labels (`[22, [40, 40, 80]]`,
  `[10, [35, 35, 80]]`). Even after 0ce9a72, the 45–50-Stuff group sits +3 to
  +7 above OVR and ≤40 Stuff sits -3.
- Platoon items from `my-todo.txt`. They need `RatingsView` to expose vs-L/R
  ratings per profile.

## Open questions

- Decided (2026-11-04): current scoring is judged on performance stats, with
  OVR as the fallback and the watchlist as a sanity check. Draft scoring is
  judged on holding potential, measured against draft-day POT.
- Decided: a draftee is judged on OVR from age 25 and on POT now before that,
  by the player's age rather than the class's age.
- Decided: the signal inventory is a report only. It never fails the suite.
