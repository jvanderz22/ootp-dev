# Plan: The chance he gets there, for prospects

The draft board now values a draftee at the WAR he's expected to realize:
his ceiling, taken through odds fit on the league's past classes
(`plans/draft-odds-plan.md`, steps A–C). The prospect board (the `potential`
profile: the league's players with under a year of MLB service) still uses
the legacy draft-day modifiers (`AgeModifier`,
`DraftBatterOverallModifier`, `DraftPitcherOverallModifier`) and the
development factors. This plan does for it what the draft odds did for the
draft board. It's step E of the draft-odds plan.

Sequencing: after the draft board's review (draft-odds D). Anything D turns
up about readiness or role shapes this design too.

## What carries over

- **The ceiling:** the prospect board's potential-ratings WAR (model
  lines).
- **Readiness:** the `FULL_TIME` companion, his current ratings' WAR.
- **The stage and the card:** the profile's `odds` flag, the ledger
  sections (Ceiling, Reaching his ceiling, Adjustments), and Range /
  Regular / Breakout under the band.
- **The ceiling panel** (`ranking/fitting/ceiling_panel.py`): it already
  holds every prospect export as a look.

So it's mostly a second artifact and a refit, not new plumbing.

## What's different (2026-11-10)

You: the age curves and the already-developed players are "at least quite
different" for prospects.

- **Readiness carries far more.** Draftees are nearly all OVR 20.
  Prospects' median OVR is 25–30 and spans Rookie ball to AAA, with 185 in
  the majors in the 2038 export. The draft fit's readiness is a multiplier
  on the ceiling, capped at +3 WAR, and for a developed prospect that's the
  wrong shape: it can push him past his own ceiling.
- **Age means something different.** For a draftee, age is runway given
  readiness. For a prospect it's age for his level: 21 in AA is ahead, 24
  in A ball is behind.
- **Role:** a 23-year-old still starting in AA is far likelier to stay a
  starter than a drafted teen. The draft's SP ×0.62 doesn't carry over.
- **The legacy modifiers were built for draftees,** at OVR 20. They'd be
  replaced, as on the draft board.

## The data

Four exports (`datasets/yfmlb-2038..2041-prospects.csv`, the own-scout
files), judged on the December 2042 snapshot:

| Export | Prospects | Age p10 / p50 / p90 | Settled (25+ now) | Gone |
|---|---|---|---|---|
| 2038 | 3,643 | 18 / 21 / 24 | 44% | 20% |
| 2039 | 4,241 | 18 / 21 / 24 | 40% | 14% |
| 2040 | 4,302 | 18 / 21 / 25 | 33% | 7% |
| 2041 | 4,802 | 17 / 21 / 24 | 25% | 3% |

The settled ones skew old. A prospect who was 18–20 in 2038 is 22–24 now,
so no export settles a teen. The fit can see how 21+ prospects turn out,
not how teens do.

## The model

**Model the remaining gap, not the ceiling.**

    E[v] = his WAR now + P(he closes the gap) × (ceiling − his WAR now)

The gap is floored at 0. A prospect in AAA already near his ceiling gets
nearly all of it, and a Rookie-ball teen gets odds on most of it. The odds
of closing the gap are fit on:
- the gap itself
- readiness
- age for level, or age and level apart (see open question 3)
- role
- makeup and adaptability, tapered as today

"Closing the gap" is the realized share of it: (A − now) / gap, clipped to
0–1. A Poisson or binomial fit on that share, whichever holds out better.

**Growth,** from the panel, starting from a prospect look instead of draft
day. A prospect who has already outgrown his draft ceiling keeps the odds
his traits earn, but gets no credit for growth he's already shown.

**The distribution and the card** are as on the draft board: bust, short
of ceiling, outgrows. The rest's mean is set so the whole matches E[v].

## On track (2026-11-11)

You: define an "on track" model for prospects and draftees both, that sets
how much to weigh the POT − CUR difference by age. Judgment calls are fine
where the data is thin; don't overfit it.

A draftee is a prospect on draft day: Jordan Tapia at 22 (draft-odds D,
"Advanced college draftees") and a 22-year-old in AA ask the same question.
So both boards share one piece:

- **The gap:** ceiling WAR − WAR now (both full-time, model lines).
- **Expected gap by age:** the typical gap, at each age and ceiling, of
  players who went on to reach their ceiling. Smoothed across age; a
  judgment shape where the data is thin.
- **On track:** expected gap − his gap, in WAR. Positive is ahead of
  schedule.
- **The odds** of closing the gap are fit on on-track and the gap,
  replacing the draft fit's flat Age and Readiness lines. Readiness then
  barely matters at 18, when everyone is raw, and a lot at 22–24.
- **The card:** one line, e.g. "On track +0.8 WAR ahead · ×1.18".
- **Fallback:** if the pooled data can't size it, the judgment from D:
  readiness halves the 22+ age penalty (none at −1 WAR now, half at 0+).

Order:
1. **Describe,** pooled: every prospect per export (2038–41) and every
   draftee per class (2033–41), judged on outcome A. Expected gap by age
   and ceiling; realized share of the gap by on-track bins, by age.
2. **Fit on-track** into the draft odds and check held out. Tapia is the
   test case.
3. **The prospect board** is built on it (order of work below).

### Step 1 findings (2026-11-11)

`ranking/fitting/prospect_odds.py`. Pooled: settled rows with a 0.5+
ceiling, about 2,700 draftee looks and 6,400 prospect looks.

- **The shape holds.** Ahead of the typical gap for his age and ceiling
  (WAR), by age, ceiling 2+, the share who became regulars:

  | Age | 1.5+ behind | 0.5–1.5 behind | typical | 0.5–1.5 ahead | 1.5+ ahead |
  |---|---|---|---|---|---|
  | ≤20 | 13% | 24% | 17% | 17% | — |
  | 21 | 11% | 11% | 19% | 24% | 44% |
  | 22 | 6% | 6% | 16% | 27% | 53% |
  | 23 | 4% | 8% | 19% | 36% | 61% |
  | 24 | 8% | 10% | 19% | 36% | 64% |

  Flat for teens, steep from 21 on.
- **Peers have to be the same stage.** A 22-year-old pro has had years of
  development: with Tapia's 5.84 ceiling he's typically 4.6 WAR short.
  Tapia is 5.7 short, so against the pooled curve he's 1.1 behind. On
  track is measured against draftees on the draft board, and against
  prospects (by age, likely level too) on the prospect board.
- **Draftees alone, the readiness weight by age** (classes 2033–37, 90%
  ranges): ≤20 ×1.21 a WAR (1.10–1.32), 21 ×1.51 (1.38–1.67), 22+ ×1.44
  (1.19–1.90), against the flat ×1.34. With it, the 22+ age line reads
  ×0.50 (×0.54 flat).
- **It doesn't lift Tapia.** On 2042 the data version moves him 6th → 7th:
  his readiness (+0.1) sits at the reference, so the steeper weight doesn't
  touch him, and the teens' raw readiness costs them less. Pat Calhoon
  (+1.6) goes 2nd → 1st. Settled 22+ draftees well ahead of their draft-age
  peers realized 0.22 of the ceiling and 11% became regulars (36 of them).

### Steps 2–3 findings (2026-11-11)

`ranking/fitting/prospect_odds.py`. Settled prospects with a 0.5+ ceiling:
6,422 looks, 2,538 players. Held out by player (all of a player's exports in
one fold), each export ranked on its own. Unsigned amateurs (level "-") are
left out, and A+ reads as A, as in the snapshot.

- **Prospects often end below their WAR now.** 45% finish 0.25+ WAR under
  it, 47% of those already in the majors, and more the more developed they
  are. The plan's "WAR now + odds on the gap" with now as a floor would
  overshoot, so his WAR now gets its own odds (keep).
- **The gap form wins at the top.** A multiplier in the draft fit's shape
  ranks as well (rho 0.65) but puts half its top 25 past their own ceiling.
  They realized 0.76 of predicted. The gap form is calibrated there (0.96)
  and everywhere else: 0.95–1.05 by rank, level, age and age for level.
  Relievers come out 1.18.

  | Held out, mean per export | rho | Top 25 | Top 50 | Top 100 |
  |---|---|---|---|---|
  | Today's prospect board | 0.42 | 2.07 | 1.96 | 1.67 |
  | The draft fit as it is | 0.57 | 2.62 | 2.36 | 2.04 |
  | Multiplier, refit | 0.65 | 2.96 | 2.53 | 2.19 |
  | Gap form | 0.66 | 2.95 | 2.53 | 2.14 |

- **The fit:** E = keep × WAR now + close × (ceiling − WAR now).
  - keep: about 45% at three years out. It rises with WAR now (2 WAR now
    keeps about two-thirds) and falls with age.
  - close: about 30% from 20 to 22, 21% at 24, 18% at 25. Readiness weighs
    more each year (the on-track shape).
  - Role: SP closes less (log-odds −0.89), RP −0.30.
  - Makeup: WE H +0.41, fragile −0.70.
- **Level drops out** (open question 3): once age and readiness are in,
  level adds nothing held out, and age for level comes out ×0.95 a year.
  keep on level instead of WAR now does no better. Short-season A
  realizes 0.89 of predicted, the only level off.
- **Pitchers:** unbalanced, the buckets are 41 / 61 / 52 / 61 / 56% held
  out. The draft's balance (50% on average) would cut them ×0.92 and drop
  the top 25 to 33%. So the balance is the factor that keeps the worst
  bucket nearest 40–60%: ×0.99.
- **Ceiling matters little for the young, and the data backs it.** In
  close, E grows with about ceiling^0.1–0.2 at 21–23, against ceiling^1.17
  in the draft fit. Held out, it's calibrated even for young high ceilings
  (under 21 with a 4+ ceiling: 1.24 realized, 1.25 predicted, n = 10). The
  draft fit predicts 2.39 for them. But the cells are thin, and a
  21-year-old in the 2038 export is judged at 25. Draftees with 3+ ceilings
  realized 22% of the ceiling at 25 and 37% at 28, though class confounds
  that.

**On the 2042 snapshot** (scratch, not the stage yet: 9,614 prospects under
a year of service):
- The top 8 are all MLB rookies (Isaiah Ghant 3rd → 1st, Chris Metzen 25th
  → 4th). Oscar Canas goes 1st → 14th.
- Held at 21, teens nearly vanish. The top 100 has 2 under 20, against 26
  on the board, and Harvey Sanchez (18, POT 80) goes 18th → 1,864th: an
  18-year-old at −3 WAR now reads as a 21-year-old at −3, a bust profile.
  Two bridges:

  | Bridge | 20 and under in top 100 | Sanchez | Morrison | Lang | Canas |
  |---|---|---|---|---|---|
  | Held at 21 | 2 | 1,864 | 758 | 219 | 14 |
  | On track (readiness moved to 21's typical) | 10 | 292 | 175 | 127 | 16 |
  | The draft fit under 20, blended to 22 | 15 | 152 | 69 | 25 | 9 |
  | Today's board | 26 | 18 | 11 | 4 | 1 |

- Pitchers are 20% of the live top 25 (the board: 12%). The live pool's
  MLB rookies are mostly hitters.
- The pool runs past the exports' age 26. The fit holds 27+ at 25.

### Step 5, the stage (2026-11-11)

`ranking/prospect_odds.py`, `prospect_odds_v1.json`. The `potential`
profile has `odds="prospect"` (the draft profile `odds="draft"`) and the
readiness companion. The ceiling companion is gone: the odds carry the
ceiling, as on the draft board. The development factors and the draft
odds' REPLACES are off. Kept: scouting accuracy, the hit profile, a switch
hitter, velocity as an upside, and pitchers ×0.99.
- **The ledger:** Ceiling → "WAR now" (keeps X%) → "Gap" (closes Y%) →
  "Runway" (the teen bridge's difference, under 22) → the kept lines. A
  prospect whose WAR now is past his ceiling gets a "Past his ceiling" line
  first. There's no distribution yet (step 4), so the card shows no range
  strip and no 1-100 score; the board stays in WAR.
- **Readiness by side.** The companion keeps each side's model WAR, and the
  prospect odds read the side's own WAR now (the table is rebuilt that
  way). Before, a side read the WAR now of whichever side he was judged on
  now: Esteban Ricalde, a 3.3 WAR bat, was valued as a reliever on his
  bat's readiness. The draft board still reads the judged side, as it was
  fit. Per side, 942 of 970 in the 2042 class move and 39 change sides
  (Chad Steedley 25th → 48th), so it waits for a draft refit.
- **On the 2042 snapshot:** 9,614 prospects score in about 15 s.
  - 15 MLB rookies in the top 25.
  - 15 aged 20 and under in the top 100 (the board: 26).
  - Pitchers are 20 / 26 / 25% of the top 25 / 50 / 100, against 40–61%
    held out. The live pool's MLB rookies are mostly bats.
  - Harvey Sanchez is 220th, Mike Morrison 60th, Marc Lang 21st and Oscar
    Canas 8th.
- **The goldens** for the potential board, its evals and the org rankings
  are regenerated. The org rankings' curve is still in potential WAR (step
  6).

### Upside (2026-11-11)

You, on the movers: Montano very overrated; Calhoon punished too hard for
being 23; Blankenship, Englund too low; Mass, Thacker dropped too far; Canas
up to 2nd–3rd. "Probably still weighting present production a little too
much over upside."

- **The data backs the fit on outcome A**, so these are judgment:
  - Montano is graded as a 187-inning starter (3.0 WAR now). Held out,
    relievers with WAR now realized more than predicted.
  - A readiness × ceiling term is real in the data (−0.30), but it moves
    the named players the wrong way.
  - Outcome A sees at most 4.4 years, and young prospects are judged at
    about 25, before a high ceiling usually pays off.
- **Decided** (in `ranking/fitting/prospect_odds.py`, held to the value by a
  tight prior, the rest refit around it):
  - **Neutral ceiling slope:** the share of the gap he closes doesn't fall
    as his ceiling rises (the data: −0.80 in log-odds per log ceiling).
  - **Upside ×2:** the board ranks on what he keeps of his WAR now, plus 2
    × what he's expected to add by developing. It's an "Upside" ledger
    line after the expectation's lines.
  - **The starter penalty is reworked,** −0.93 → −0.40. You: at least 5
    starters in the top 25 (10–12 is fine), about 30–35 pitchers in the
    top 100. One penalty can't reach 10–12 at the top without passing 35
    in the top 100, so it's set at 6 / 36. The pitcher balance is off
    (×1.00).
- **Held out**, what the board ranks on realizes 2.58 WAR in its top 25
  and 2.29 in its top 50. The expectation alone: 2.87 / 2.48. The legacy
  board: 2.07 / 1.96.
- **On 2042** (legacy rank → new):
  - Canas 1 → 8, Thacker 12 → 20, Calhoon 10 → 21, Mass 2 → 23.
  - Blankenship 9 → 85, Englund 16 → 112, Montano 436 → 46.
  - 6 starters in the top 25; 34 starters and 2 relievers in the top 100.
- **Canas tops out around 5th–8th** under every setting tried. The players
  ahead of him gain from upside too.

### On schedule (2026-11-11)

You: still too punishing on Blankenship and Englund, 22 in AA at about
replacement.
- **The neutral ceiling now holds at every age.** Held alone, the refit
  had moved the ceiling penalty into the age × ceiling terms (−0.20 to
  −0.26 in log-odds near 21), so those are held at 0 too. Canas goes to
  2nd.
- **Why 22s still lagged.** On the same live players, the draft fit's
  expectation is 2.4× the prospect fit's at 19, 2.2× at 20, 1.3× at 21 and
  1.0× at 22. A raw 22 competes with teens still valued partly on the draft
  fit.
- **Levers that barely moved them** (Blankenship / Englund):

  | Lever | Ranks | Side effect |
  |---|---|---|
  | An age-22 knot held at 21's level | 54 / 78 | — |
  | A lighter readiness weight | — | The refit moves it into the age-25 term |
  | Upside ×3 / ×4 | 51 / 73, 48 / 72 | Montano 118 / 207 |
  | The bridge anchored at the prospect fit's level | 37 / 59 | No teens in the top 25 |

- **Decided: on schedule.** Near replacement, the closing odds and the
  bridge read the age curve as flat from 21.5 to 23.5. The age catches up
  to his own by 24.5. The relief is in full at 0 WAR now and none from 1
  WAR (`ON_TRACK`). A raw 22- or 23-year-old reads as 21.5; Calhoon, at 1.0
  WAR now, gets none. The card's Gap note reads "on schedule".
- **Held out**, value rho 0.62 → 0.56, top 25 2.53 → 2.48, top 50 2.29 →
  2.25.
- **The judgment's optimism, on settled raw 22–23s** (WAR now ≤ 1, 2,336
  looks): they realized 0.46 WAR on average. The fit alone predicted 0.44
  (calibrated, 1.04); with on schedule it predicts 0.60, so they realized
  0.77 of it. With 4+ ceilings (61 looks): realized 1.28, fit 1.29, with
  the judgment 1.55 (0.83).
- **On 2042** (legacy → new):
  - Blankenship 9 → 32, Englund 16 → 36, Mass 2 → 6, Thacker 12 → 7,
    Calhoon 10 → 19, Canas 1 → 2.
  - Montano 436 → 62, Morrison 11 → 43, Sanchez 18 → 208.
  - The top 25: 6 starters, 6 aged 20 and under, 8 aged 22–23.
  - The top 100: 37 pitchers (5 relievers), 23 aged 20 and under, 49 aged
    22–23.

## Open questions

1. **The gap form.** *Recommend it.* The draft's multiplier form overshoots
   developed players. Confirmed held out (steps 2–3), with keep fit rather
   than 1.
2. **Unsettled teens.** Either:
   - bridge them with the draft fit's teen factors (judgment) until the
     season snapshots settle them, or
   - leave the legacy treatment on teens until then.

   *Recommend the bridge,* refit at each new season snapshot (draft-odds
   F; the first is April 2043).

   *Decided 2026-11-11:* the draft fit's expectation under 20, blended
   linearly into the prospect fit by 22.
5. **Past the exports' ages** (decided 2026-11-11). Players past 25 stay
   on the board, but by then much more development is hard to get, even
   short of his potential. The closing odds taper from 25's to none at 27.
   From 27 he's valued at the WAR now he holds.
6. **The card** (decided 2026-11-11): the lines, e.g. "WAR now · keeps X%"
   and "Gap · closes Y%". Their breakdown into drivers comes second, but
   the model keeps its components visible (keep, close, WAR now, the gap)
   so the card can show them.
3. **Age for level, or age and level apart.** Test both; the held-out
   check decides. Neither: level drops out once readiness is in (steps
   2–3).
4. **Overlap with the draft fit.** The 2033–37 draftees appear in the 2038
   export as pros. Fit them in both, or keep each player in one? *Recommend
   both:* the two boards ask different questions on different days.

## Order of work

1. **The prospect table:** one row per prospect per export (2038–41), with
   his ceiling (potential profile, model lines), readiness (`FULL_TIME`,
   model lines), level, age, role, makeup, adaptability, and outcome A on
   the snapshot (`FULL_TIME`, 0 once gone, settled at 25+). It goes in
   `ranking/fitting/prospect_odds.py`, sharing `draft_odds.py`'s helpers.
2. **Describe it** before fitting: the realized share of the gap by level,
   age for level, readiness and role. Show where the draft fit's shape
   breaks.
3. **Fit the gap odds** (open questions 1 and 3), held out one export at a
   time, against today's prospect board. Run the ship checks:
   - top 50 no worse than the board
   - pitchers 40–60% in every bucket, with a refit balance
4. **Growth and the distribution:** refit from the panel's prospect looks,
   then the B4/B7 checks (P90, P(regular), P(breakout) by decile).
5. **The stage:** the `potential` profile gets `odds` and the readiness
   companion. Its development factors and draft-day modifiers go; the
   teens' bridge applies if decided (open question 2). Velocity as an
   upside carries over.
6. **Review:** the movers on the league's prospect board. The org rankings
   (`web/org_rankings.py`, whose curve is in potential WAR) get rechecked.
7. **Refit at each season snapshot** (from April 2043), dropping the bridge
   as the teens settle.
