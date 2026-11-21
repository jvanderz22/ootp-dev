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
plan was to replace it. The playing-time factor that ships keeps it.

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

## The model, as built: a playing-time factor (2026-11-21)

The split below was built and failed its ship checks (next section). What
ships instead is your reframe: how much bat a player needs to get on the
field depends on his glove. A good glove makes a weaker bat playable, and a
1B or DH needs more bat than a shortstop.

    E[v] = today's odds (glove at half) × playing time ^ ½
    playing time = P(he plays | his bat, glove, run, age)
                 / P(he plays | his bat, an average glove and run, age)

- **The chance he plays** is a logistic fit of his share of a 600-PA season
  at 24–26, on his bat's ceiling, bat now, glove and run at potential, and
  draft age. Held out it comes out flat by glove share (bat only 0.166
  predicted / 0.154 observed, 45%+ glove 0.118 / 0.103). Position adds
  nothing once the glove and bat are in.
- **Run** counts as much as the glove per typical player (one SD of each).
  Speed reads as athleticism, which gets a player on the field. That settles
  open question 1.
- **At equal bat:** the factor compares him to a draftee with the same bat,
  so it never counts the bat twice. Over the whole chance, the top 25 fell
  (4.39 → 3.75 MLB WAR among hitters).
- **At half strength (the square root):** at full strength it over-rewards
  gloves (45%+ glove realized 0.65 of predicted) and pulls the top 25 toward
  hitters.
- **The glove stays at half in the ceiling** (`GLOVE_WEIGHT`). With the
  glove in full, the factor ranks about as well but values glove-first
  ceilings at 0.59 of what they realize.
- **The card:** one "Playing time" line after the odds' lines.
- **Catchers get no factor** (you, 2026-11-21). The catcher adjustment in
  a catcher's glove read as "he'll play" and lifted Lorenc 17 → 5. A catcher
  term in the fit (−0.30) only took back part of that. Catchers are to be
  revisited another way. A catcher factor read off MLB WAR (×0.41) fixes
  them on average but ranks worse at any strength, so it's reported, not
  applied.
- **Capped at ×1.5** (about its 95th percentile). Elite speed on a weak bat
  is where the fit extrapolates (Maruri ×2.32, Bernier ×2.07).
- **The pitcher balance ramps with value:** ×0.99 × (value / 1 WAR)^0.3.
  The factor spreads hitters' values, so one balance factor left the top 25
  at 38% pitchers. Ramped: 48/52/45/50/55% by bucket. On MLB WAR to 26,
  held out: rho 0.321 (board 0.313), top 25 4.80 (4.92), top 50 3.52
  (3.62), top 100 2.47 (2.37).
- **A soft cap on the share of his ceiling** (2026-11-21, folded into the
  base rate): s / √(1 + (s / 0.8)²). Each factor is calibrated alone, but
  stacked they overshoot. Held out, draftees predicted to realize 50%+ of
  their ceiling realized 0.64 (value now) / 0.73 (MLB WAR to 26) of it, and
  70%+ realized 0.38 / 0.67. Most had high work ethic on a modest ceiling,
  like Nakasone (89% of 2.62; WBF 2122 6 → 11). With it, on MLB WAR to 26:
  rho 0.320, top 25 4.86, top 50 3.65, top 100 2.48; pitchers 48/50/46/50/55%
  (ramp 0.25).
- **An upside weight** (2026-11-21, you; open question 2): the board ranks
  on value^0.85 × ceiling^0.15, as an "Upside" line over a typical top-100
  draftee's ratio (ceiling 3.4× his value) so the top keeps its scale. WBF
  2122: Figueroa 8 → 5, Nakasone 11 → 15. On MLB WAR to 26: rho 0.321, top
  25 4.71, top 50 3.61, top 100 2.41 (0.1 raised the top 10, 6.06 → 6.22).
  Tracked with `print_draft_watch.py` (draft_watchlist.csv).
- **The card's range respects the ceiling** (2026-11-21). Short of
  outgrowing, a draftee lands at most 0.5 WAR past his ceiling (a cut-off
  gamma, its mean held to his value; near the ceiling he busts less
  instead). Outgrowing starts 1 WAR past it, in real WAR. The card reads his
  value before the pitcher balance and Upside, which rank him and don't
  change his outcomes. Above P90 on the past classes: 12% (top 100 9%), as
  before. WBF 2122: Nakasone 0.1–3.1 → 0.1–2.9, Mosegi 0.0–7.6 → 0.0–5.8.

Held out one class at a time, on MLB WAR to 26:

| | rho | Top 25 | Top 50 | Hitters' rho | Bat only | 0–25% | 25–45% | 45%+ | Catchers |
|---|---|---|---|---|---|---|---|---|---|
| Today (glove at half) | 0.363 | 4.65 | 3.63 | 0.303 | 0.73 | 1.38 | 1.23 | 1.05 | 0.38 |
| + playing time ^ ½ | 0.377 | 4.86 | 3.81 | 0.331 | 0.85 | 1.26 | 0.98 | 0.82 | 0.36 |
| Full glove + playing time ^ ½ | 0.383 | 4.82 | 3.83 | 0.342 | 0.92 | 1.29 | 0.87 | 0.59 | 0.30 |

The right-hand columns are hitters' realized over predicted, by glove share.
The pitcher mix stays near 50/50 (45/41/48/56/60% by bucket).

**What's left:** catchers realize 0.3–0.45 of predicted in every version.
Among 2042 MLB regulars a catcher is worth what the model says (within 0.2
WAR per 600 PA). Catchers mostly don't get there by 26, and arriving later
adds little (you, 2026-11-21). A catcher factor is open question 4.

**Why the glove is priced right once he plays:** among 2042 regulars (300+
PA), actual WAR per 600 PA = 0.93 × bat + 0.94 × glove + 0.65 × run on the
model's parts. The miss is in getting there, not in the glove's value.

## The split, as first planned (didn't ship)

Built and checked 2026-11-21. Held out, it ranked worse than today's board
(hitters' rho on MLB WAR 0.300 against 0.313) and catchers fell to 0.33
realized over predicted. It prices the glove on MLB playing time but the bat
and pitchers on ratings, so hitters lost about 27% across the board and
pitchers needed ×0.69 to stay 50/50. Counting more of the glove made it
worse. So did a gate (bat + glove counts only above a bar).

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
- **Run** (baserunning) has no potential ratings either. It counts with
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

1. **Run with the glove or the bat?** Speed has no potential rating, so it's
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
   and run, and his MLB PA through 26. *Done.*
2. **The chance he plays:** fit it, and check it by position and glove share.
   *Done.*
3. ~~**The bat odds:** refit on the bat's ceiling.~~ Dropped with the split.
4. **The stage:** the playing-time factor in the fit and the artifact, and a
   "Playing time" ledger line. `GLOVE_WEIGHT` stays.
5. **Held-out checks and movers,** for your review.
6. **Open questions 2–4** once you've seen the movers. The catcher factor
   first.

## The prospect board

The prospect odds (`plans/prospect-odds-plan.md`) are already partly split.
What carries over, and what doesn't:

    E = keep × his WAR now + close × (ceiling − his WAR now)

- **The gap is already the bat.** A glove has no potential ratings, so it's
  at its ceiling and sits in his WAR now. The gap is what the bat still has
  to add, and the closing odds read how developed the bat is (bat WAR now
  alone, 2026-11-12).
- **The upside weight is already the bat's.** The board weighs what he's
  expected to add by developing ×2, and that's the gap.
- **The glove's blind spot is the same.** His WAR now includes his glove,
  held at the odds of keeping it (about 50–75%). Those odds are fit on value
  now, which credits a glove whether or not he plays. So a glove-first
  prospect keeps his glove's WAR even if his bat never gets him to the
  majors. Maddux and Myers are the cases to watch.
- **The teen bridge doesn't have the interim.** Below 22, a prospect is
  valued partly on the draft odds. The bridge reads them from the full
  ceiling, so `GLOVE_WEIGHT` doesn't reach teen prospects on this board, and
  a glove-first teen is valued higher here than on the draft board.

**The data (2026-11-21):** the same miss as the draft board's. Settled
prospect exports (2038–41, 6,496 rows), held out, hitters' realized over
predicted by glove share:

| | Bat only | 0–25% | 25–45% | 45%+ | Catchers |
|---|---|---|---|---|---|
| Value now (what the fit trains on) | 0.92 | 1.05 | 1.14 | 0.93 | 0.74 |
| MLB WAR after the export | 1.17 | 0.97 | 1.13 | 0.71 | 0.38 |

**The change (2026-11-21, revised):** not the additive split, which failed
on the draft board. What shipped there carries over, through one shared
model so a change lands on both boards (`ranking/playing_time.py`, its fit
`ranking/fitting/playing_time.py`):

1. **The bridge reads the draft board's value**: the glove at half in the
   odds' ceiling, the playing-time factor and the share cap, before the
   pitcher balance and Upside (the prospect board has its own upside ×2).
   A glove-first teen reads the same on both boards.
2. **A prospect playing-time factor**, fit on prospects' share of a 600-PA
   season in the seasons after the export, on the draft terms plus his
   level. It's on his whole value, at half strength, capped at ×1.5, none
   for catchers, as on the draft board.
3. **The upside weight** stays on what he's expected to add by developing.

**Checks:** held out by player, as the prospect fit is now; realized over
predicted flat by glove share on MLB WAR; the named players (Myers, Boyer,
Maddux, Schmidt, Mass, Montano); and the pitcher mix (at least 5 starters in
the top 25, about 30–35 pitchers in the top 100).

**Order:**

1. The prospect table gains each prospect's potential and current lines
   split into bat, glove and run, and his MLB WAR and PA after the export.
   *Done, with the shared playing-time model (6f2a9cc).*
2. The bridge reads the draft board's value. *Done (1c84f00).*
3. Fit the prospect chance he plays, and put the factor on the board, with
   the glove at half in his ceiling and WAR now. *Done.* The fit, on the
   two seasons after the export (2038–40 exports, 5,304 hitter rows): bat
   +0.43, bat now +0.87, glove +0.71, run +0.81, catcher −0.34, level +0.73,
   a small age curve. The factor is read at 21 in A ball: at his own age and
   level, a 27-year-old in AAA has so small a chance that any glove reads as
   a big ratio (Kennedy, 3B, 29: 60 → 20).
4. Checks and movers, for your review. Held out on MLB WAR after the
   export, the board's value: rho 0.450 → 0.438, top 25 5.56 → 5.50, top
   50 4.20 → 4.27, top 100 3.39 → 3.36; glove-first realized 0.83 → 1.00
   of predicted, bat only 1.04 → 1.12, catchers 0.42 → 0.56. On the yfmlb
   snapshot: Mass 48 → 17, Sandoval 95 → 18, Maruri 129 → 45; 1B and corner
   bats fall (Lock 41 → 123, Caudill 25 → 96). 7 starters in the top 25,
   44 pitchers in the top 100 (43 before).
