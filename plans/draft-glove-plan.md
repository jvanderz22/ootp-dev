# Plan: The bat and the glove, apart

The draft board values a hitter as one ceiling (his potential ratings' WAR in
a full-time role) taken through one set of odds. You (2026-11-21): the bat
has a wide range of outcomes and drives the upside; a glove is static. A
player whose ceiling comes mostly from defense doesn't have that upside, and
his glove only pays if his bat gets him on the field.

This plan splits a hitter's ceiling into the two and values each on its
own terms. Pitchers are unchanged.

Interim (2026-11-21): the odds work from a ceiling with the glove counted at
half (`GLOVE_WEIGHT` in `ranking/draft_odds.py`, a "Glove" ledger line). This
plan replaces it.

## What the data says (2026-11-21)

Past yfmlb classes, hitters with 1.5+ WAR ceilings, MLB WAR through 26 over
the draft-day ceiling, by the glove's share of the ceiling (fielding and
utility at potential):

| Ceiling driven by | n | Mean | P90 | P97 | 10+ WAR by 26 |
|---|---|---|---|---|---|
| Bat only (glove below 0) | 239 | 0.53 | 2.10 | 4.33 | 6% |
| Glove 0–25% | 152 | 0.91 | 3.43 | 6.51 | 14% |
| Glove 25–45% | 63 | 0.67 | 1.75 | 4.58 | 5% |
| Glove 45%+ | 44 | 0.38 | 0.88 | 2.55 | 2% |

- **Glove-first ceilings have a short tail.** Few of them become stars.
- **The fit's outcome can't see it.** The fit trains on value now: full-time
  WAR on 2042 ratings, which counts a glove in full whether or not the bat
  ever plays. On value now, glove-first draftees look as spread out as the
  rest (P97 1.55).
- **Against the fit's prediction** (MLB WAR through 26, realized over
  predicted):

  | Glove counted at | Bat only | 0–25% | 25–45% | 45%+ | Catchers | Hitters' rho |
  |---|---|---|---|---|---|---|
  | 100% | 0.78 | 1.42 | 1.04 | 0.77 | 0.66 | 0.315 |
  | 50% (the interim) | 0.72 | 1.41 | 1.19 | 1.07 | 0.71 | 0.304 |
  | 0% | 0.68 | 1.41 | 1.43 | 1.75 | 0.76 | 0.282 |

- **A flat discount is the wrong shape.** It fixes glove-first players but
  ranks a little worse, so a glove does predict MLB value. Pure bats
  under-realize too, with no glove to fall back on. Bats with a little glove
  over-realize. Catchers stay low either way.

Small samples: 44 glove-first hitters and 86 catchers with a settled MLB
window.

## The model

    E[v] = E[bat part] + P(he plays | bat, glove) × glove

- **The bat part** is the ceiling's batting and platoon lines, through the
  odds as they are now: log bat potential, readiness (already the bat alone),
  age, makeup. The range and the chance he outgrows his ceiling come from
  the bat alone. A glove can't outgrow.
- **The glove** is fielding and utility at potential (already at its
  ceiling: catching ratings rise 1–2 points from the teens, and POT doesn't
  predict more). It's counted in full, times the chance he plays.
- **The chance he plays** is a logistic fit on MLB playing time: a regular's
  share of PA by 26, on the bat's ceiling and readiness, the glove, age and
  position. A glove raises it: managers play a good defender with a weaker
  bat, which is how the glove pays.
- **Legs** (baserunning) have no potential ratings either. They count with
  the glove (open question 1).
- **The card:** the ceiling stays the full WAR. The ledger reads: the bat's
  ceiling through its odds, then the glove times the chance he plays. The
  range and Breakout come from the bat.

## Fitting it

- **The bat part** refits the Poisson fit on value now, on the bat's
  ceiling. Value now credits the bat as the board does.
- **The chance he plays** is fit on MLB PA, the classes with a complete
  window through 26 (as outcome B). Value now can't fit it, since it credits
  the glove regardless.
- **Held out, one class at a time,** on both outcomes, against today's
  board and the interim. Ship checks:
  - realized over predicted on MLB WAR comes out flat across the glove-share
    groups, and closer to 1 for catchers;
  - hitters' rho on MLB WAR doesn't fall below today's 0.315;
  - the pitcher share stays near 50/50 in each bucket.
- **Movers:** WBF 2122 (Lam, Mendoza, Lorenc, Walata) and yfmlb 2042.

## Open questions

1. **Legs with the glove or the bat?** Speed has no potential rating, so it's
   static like the glove. But it helps a weak bat play less than a glove
   does. *Recommend* the glove's side, and check the fit.
2. **An upside weight on the draft board.** The prospect board ranks on
   upside ×2 (`plans/prospect-odds-plan.md`, "Upside"). With the bat's
   range split out, the draft board could weigh the bat's upside the same
   way. It ranks on E[v] now. Your call, after the split.
3. **The prospect board.** Its gap is already the bat (a glove sits in his
   WAR now, held with the odds of keeping it). A glove-first prospect keeps
   his glove whether or not he plays. Does the chance he plays carry over
   there too?
4. **Catchers** realized 0.66 of predicted even before the split. If the
   chance he plays doesn't close it (catchers reach the majors late), a
   catcher factor read from MLB WAR, the way relievers' was.

## Order of work

1. **The table:** each past draftee's potential lines split into bat, glove
   and legs, and his MLB PA through 26.
2. **The chance he plays:** fit it, and check it by position and glove share.
3. **The bat odds:** refit on the bat's ceiling.
4. **The stage:** the split ledger lines, the card's range from the bat, and
   `GLOVE_WEIGHT` removed.
5. **Held-out checks and movers,** for your review.
6. **Open questions 2–4** once you've seen the movers.
