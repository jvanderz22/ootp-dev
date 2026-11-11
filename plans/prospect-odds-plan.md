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

## Open questions

1. **The gap form.** *Recommend it.* The draft's multiplier form overshoots
   developed players.
2. **Unsettled teens.** Either:
   - bridge them with the draft fit's teen factors (judgment) until the
     season snapshots settle them, or
   - leave the legacy treatment on teens until then.

   *Recommend the bridge,* refit at each new season snapshot (draft-odds
   F; the first is April 2043).
3. **Age for level, or age and level apart.** Test both; the held-out
   check decides.
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
