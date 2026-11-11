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
