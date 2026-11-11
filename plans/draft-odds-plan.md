# Plan: The chance he gets there (draft odds)

The v2 draft board values a prospect at the WAR his **potential** ratings are
worth in a full-time role. That's his value *if he gets there*. The draft
modifiers are how it guesses whether he will:
- `AgeModifier`
- the draft-day current-ratings modifiers
- the Stuff and velocity modifiers
- the makeup and durability factors

Each one is a hand-set multiplier, and none of them starts from a measured
**base rate**: how much of his potential WAR a prospect like this one
actually realizes. This plan fits that base rate from the league's own past
draft classes and replaces the guesses with it. Expected value stays the
ranking rule (your call, 2026-11-09). This makes the expectation an honest
one.

It's the development layer from `plans/ranking-architecture-plan.md`
(phase 6), which only got as far as the makeup factors.

## Restart on the full-time scale (2026-11-10)

The current-ratings work landed in 7f34e1a, so the hold is lifted. This
restarts the work from first principles, on top of that model. The findings
and decisions from 2026-11-09 below still stand as evidence. Every fitted
number in them was made on the old model, though, and gets redone.

### Two WAR scales

The current-ratings WAR now does two jobs:
1. **Ratings → WAR at a full-time role.** Talent and value only: an
   everyday hitter, a starter at the innings his stamina carries, or a
   reliever at the leverage his talent earns (the talent map, at weight 1.0).
2. **Roster pricing.** It subtracts the league's own replacement price for
   his spot (YFMLB: hitter 1.26, SP 1.90, RP 0.21). It also applies the
   part-time taper for bats 8–12, and uses each bullpen spot's leverage at
   0.418.

The draft and potential boards only ever used the first. This plan calls it
the **full-time scale** and builds everything on it:

| | Ratings | Scale |
|---|---|---|
| The ceiling | potential, draft day | full-time |
| Readiness | current, draft day | full-time |
| Outcome A | current, 2042 snapshot | full-time |
| The new "Max Potential" list | current, the snapshot | full-time |
| "Expected Value" (today's Current list) | current, the snapshot | full-time, then roster pricing |

One profile produces it: `CURRENT` with `league_replacement=False`. On the
yfmlb snapshot (2026-11-10, scratch):
- It has no "league replacement" or "playing time" lines, so it gives the
  convention the shelved fit needed. The shelved script dropped the league
  replacement line by label, which missed playing time and the leverage
  change. Scoring on this profile replaces that.
- It orders the league much like the roster-priced list (rank correlation
  0.987). The two differ in three places:
  - **Relievers:** 111 in the top 500 when priced by roster spot, 14 on the
    full-time scale. Their price is only 0.21, so pricing lifts them (Mike
    Avey is #216 priced, #731 full-time).
  - **Starter-capable relievers:** 840 of them are valued as SP on the
    full-time scale.
  - **Hitters near replacement:** priced, a 1.1 WAR full-time hitter sits
    under the hitter price, behind 0.7 WAR relievers.
- A scoring pass of the whole league takes about 8 s, so a second one is
  cheap.

### Decisions (2026-11-10)

7. **The board's scale: full-time, with a distribution.** The draft board
   stays on the full-time scale, and the odds model predicts the spread of
   what he realizes, not only the mean. See "The distribution". What it
   changes on the board is open question 1.
8. **Hitter platoons stay in the full-time scale.** A platoon cuts playing
   time too, but it's how you use hitters, and the prospect ceilings carry
   it. It's small: 253 of the full-time top 1,000 lose WAR to it, a median
   of 0.09.
9. **Full potential for every player, kept out of the way.** Each league
   player gets his potential ratings' full-time WAR: model lines only, with
   no development factors or modifiers. It's a general mapping of what
   reaching his potential means. It goes on the card and in a column outside
   the default view, not in a tab.
10. **Names.** Today's Current list becomes **"Expected Value"** and the
    full-time list **"Max Potential"** (see open question 2).
    **Revised 2026-11-10: the Current tab stays "Current"** (you: "it
    should be Current or Current Production").

### Open questions

1. **What the distribution changes on the board.** The fit already floors
   busts at 0 (its outcome is max(A, 0)), so the mean model already predicts
   E[v] on the full-time scale. A distribution adds:
   - the card's range (P10–P90) and the chance he becomes a regular, which
     phase 6 wanted to show
   - ranking rules that need more than the mean: surplus over the league's
     price, E[max(v − price, 0)], or the γ dial

   Phase 6 found ranking by P75 or P90 no better than E[v].
   *Recommend: fit it, keep E[v] as the default, and have step B4 compare
   E[v], the surplus and γ = 1.5 side by side, held out. You choose on the
   movers.*
   **Decided: as recommended.**
2. **"Max Potential" next to "Potential".** The league view already has a
   Potential tab, the rookies' prospect board on potential ratings, and
   decision 9 adds a potential column. "Max Potential" on a current-ratings
   list could be read as either. *Suggest: tabs "Expected Value", "Max
   Potential" and "Prospects", and the column "Ceiling".*
   **Decided: the column is "Ceiling", and the Potential tab becomes
   "Prospects".** The tabs are "Expected Value", "Max Potential" and
   "Prospects".
3. **Stuff and velocity.** Decision 2 said to test them as inputs before
   deciding. Step 2 did, and neither helped (Stuff is already priced a
   little high). *Recommend replacing both, unless you'd rather keep either
   as judgment.*
   **Decided: keep both as judgment.** Your reasoning: a pitcher with high
   Stuff or velocity has more upside, and needs less from his other traits
   to develop past what's scouted as his ceiling into a useful MLB pitcher.
   That's a claim about the upper tail, not the mean, so step B4 checks it
   in the distribution (see there). The check informs the judgment; it
   doesn't replace it.

   Your examples (2026-11-10). In all three, the *ceiling itself* grew:
   potential Stuff rose well past the draft-day scouting, and velocity
   tended to rise first.

   | | Drafted | Draft day: Stuff P / velocity | Later | Now (2042 snapshot) |
   |---|---|---|---|---|
   | Andy O'Neal | 2035, age 18 | 45 / 94–96 | 2039: Stuff P 55, 99–101 | RP, OVR 60, Stuff 70 (P 75) |
   | Hedbert Linger | 2034 at 18; 2037 at 21 | 40 / 91–93; 50 / 97–99 | 2040: Stuff P 70, CL | RP (MLB), OVR 65, Stuff 60 (P 65) |
   | Hector Lujan | 2034, age 18 | 45 / 89–91 | 2038: Stuff P 55, 96–98 | SP (MLB), OVR 55, Stuff 55 |

   - The 2034 export is an old format, with current velocity standing in
     for potential, so Linger's and Lujan's draft-day velocity reads low.
   - Two of the three found their value in the bullpen. That fits the
     plan's finding that most drafted starters end up relieving.
   - The plan's outcome A asks whether he *reaches* his ceiling. These are
     cases of the ceiling *moving*, which outcome A only sees in the
     result. Steps B5–B7 test that directly (see there).
4. **Stuff and velocity counted twice?** Once the growth outcome carries
   velocity and Stuff (B6), keeping the judgment modifiers on top counts
   them twice. That happens through the growth odds, and again through
   tables that mostly penalize (velocity 87 or less ×0.88, SP Stuff 40 or
   less ×0.93). The options:
   - keep the modifiers on top as they are
   - let the growth fit carry both and drop the modifiers
   - shrink the modifiers to what the fit leaves unexplained

   *Recommend deciding after B7, with the two sets of factors side by
   side.* **Agreed: decide after B7.** Until then the modifiers stay on top
   as they are.
   **Decided 2026-11-10, after B7** (you: "I like your recommendations"):
   - **The growth odds can't carry velocity.** Realized growth is about 2%
     of draftees, so the velocity term barely reaches E[v].
   - **Velocity becomes upside only**, in `ranking/draft_odds.py`
     (`VELOCITY_STEPS`), in place of `PitcherVelocityModifier`. By the
     bottom of his range: ≤93 ×1.00, 94–95 ×1.05, 96–97 ×1.10, 98–99 ×1.12,
     100+ ×1.15. That's about half of what B4's finer bands showed with the
     mean held fixed: tops of 96–97 +16% (226 pitchers), 98–99 +59% (36).
   - **`DraftPitcherStuffModifier` is dropped.** Low Stuff beat the odds,
     and high Stuff added nothing.
   - The legacy engine keeps both modifiers as they are.
5. **Growth against the makeup taper.** Growth helps low ceilings most,
   which is where the makeup factors are at full weight. A mid prospect
   with WE H, INT H and 97 mph could climb a lot. The taper exists so a
   mediocre prospect with maxed makeup can't pass a generational one. D
   checks that case explicitly. If it fails, the growth outcome's makeup
   terms get the same taper. **Decided: keep checking the taper's scaling
   here.** D checks it, along with whether the taper's weights (full up to
   2.5 potential WAR, 35% from 5.0) still suit both the mean factors and
   the growth odds once they're refit.

### The distribution

Three outcomes, not two (revised 2026-11-10; see "Outgrowing the ceiling"):
- **Bust:** A = 0, including players gone from the league.
- **Short of or at his ceiling:** 0 < A, up to his draft-day ceiling plus a
  margin.
- **Outgrows it:** A past that margin. This is rarer than either of the
  others, but it has its own drivers (velocity, Stuff, age, makeup), which
  one spread around the mean would wash out.

The fit:
- **Which outcome:** a multinomial logistic fit on the mean model's inputs,
  plus the growth inputs.
- **How far, within each non-zero outcome:** log(A / ceiling) as a normal,
  with its spread by side (hitter, SP, RP). Or a gamma GLM, whichever holds
  out better.
- **Together** they give E[v] (the outcomes' chances × their means),
  P10 / P50 / P90, P(A ≥ a regular's price) and P(outgrows his ceiling) for
  the card.

The makeup taper applies to both parts. The pitcher balance factor scales
the whole distribution, as it scales the mean.

Checks, held out one class at a time:
- The hurdle's E[v] ranks no worse than the Poisson mean. If it does worse,
  the Poisson model keeps the mean and the hurdle only supplies the shape.
- P10–P90 holds about 80% of outcomes, overall and in the board's top 100.
- P(stick) is calibrated by decile.
- The step 2 ship checks pass for each ranking rule in open question 1.
- P(outgrows) is calibrated by decile, held out on both the outcome-A
  classes and the ceiling panel (B5).

### Outgrowing the ceiling (2026-11-10)

You: a draftee outgrowing his ceiling "is definitely a thing that can
happen, influenced also by the personality traits", and should show up
regularly in the data, though much more rarely than a draftee falling short.
The board can't see it today. It values a draftee at his draft-day ceiling
or less, and the mean fit can only fold growth into an average.

**A first look (2026-11-10, scratch).** This is in-game POT, a rough stand-in
for potential WAR, on classes 2033–38 against the 2042 snapshot.
- A low ceiling (draft POT 45 or less) became a useful player (POT 55+ now)
  for **2.5%** of 6,058 draftees. Among draft POT 45+ draftees, **65%** fell
  10+ POT or left the league. So it happens regularly, and it's far rarer
  than falling short, as you said.
- Plain "POT rose 10+" (17% of all draftees) is mostly 20–30 POT draftees
  drifting up, which looks like scouting noise. Growing into a useful
  player is the event that matters.
- Odds of a low ceiling becoming useful, with draft POT held fixed (90%
  ranges):

  | | Odds |
  |---|---|
  | pitcher vs hitter | ×5.5 (3.6–8.1): 3.4% against 1.0% |
  | drafted 19 or younger | ×2.4 (1.8–3.2) |
  | WE H / L | ×1.33 (0.95–1.75) / ×0.91 (0.59–1.30) |
  | INT H / L | ×1.29 (0.85–1.85) / ×0.69 (0.40–1.02) |
  | WE H and INT H together | 6.4%, against 2.6% for normal/normal |
  | pitchers 2035–38: velocity, per mph | ×1.11 (1.01–1.23); 95+ 6.6%, 92 or less ~3% |
  | pitchers 2035–38: potential Stuff, per 10 | ×1.48 (1.1–2.0) |

- Stuff points the other way here from the mean fit, where it was ×0.91
  per 10 with potential WAR held fixed. **Stuff and velocity are tail
  effects:** they don't raise the average outcome, they raise the chance of
  outgrowing the ceiling. That's your reasoning for keeping them (open
  question 3), and the plain mean model can't see it.
- The exports also carry adaptability (AD), leadership and loyalty.
  Adaptability is a candidate growth input. The other two aren't
  development traits.

**How it's modelled.** A ceiling can grow two ways, and the data can't tell
them apart:
- the ratings really grow
- the scout's read was wrong and later corrects upward

For the board that doesn't matter: both are upside nobody can see on draft
day. Growth is measured in potential WAR (the Ceiling profile), not POT, so
it counts what the WAR model values.

There are two sources for it:
- **Outcome A, classes 2033–37:** settled, but only one look per player.
- **The ceiling panel:** each draftee's potential WAR at every later look,
  from the prospect exports (2038–42) and the snapshot. It covers the
  2038–41 classes too, which outcome A can't use yet, and it's the modern
  export format, with potential velocity. Once a player is 25+, current and
  potential mostly agree (81% within 5 POT), so where his ceiling ends up is
  most of his outcome A.

The growth odds are fit on both and checked for agreement. They become the
"outgrows" outcome of the distribution. They're fit jointly with the rest,
so makeup, velocity and Stuff aren't counted twice inside the model.

### Ledger wording (2026-11-10)

*Revised 2026-11-10 after C (you: "you're always way too verbose in the
UI"): the labels below were cut to a word or two, and most notes dropped.*
- **Reaching his ceiling:** Base rate (44%), Readiness (+0.5 WAR now),
  Age 19, Starter (most end up relieving), Reliever, Work ethic,
  Intelligence, Fragile / Durable, Switch hitter, and Breakout (3%; "age 19,
  work ethic").
- **Adjustments:** Pitcher balance; the scouting and leadership notes are
  just the grade.
- **Under the band:** "Range 0.5–5.1 · Regular 54% · Breakout 3%".
- **Current card:** the reference row reads "Full-time RF 2.08 WAR".

Every line the draft card shows should read as plain English to someone
who doesn't know the model. A card row has four parts: a label, a stat
beside it, a note underneath, and the WAR it adds on the right.

**Rules:**
- **The label says what it is about,** in words: "High work ethic", not
  "WE H"; "Starters often end up relieving", not "SP". No codes, symbols
  or model terms (E[v], readiness, taper, potential WAR).
- **The stat is a percentage change** ("+25%", "−38%"), not a multiplier
  ("x1.25"). This is a display change only: the card formats the stored
  `x1.25`, so the fit script's parsing is unaffected. It applies to every
  multiplier line on the card, old ones included, so they all read the same
  way.
- **The note says why,** in one short clause that names the rating behind
  it ("97 mph", "Stuff 40"). It never repeats the stat.
- **The WAR on the right is unchanged.**
- **Section headings:** "Talent & role" stays. The odds get their own
  heading, **"Reaching his ceiling"**, in place of "Development".
  "Adjustments" keeps the judgment lines.

**Talent & role.** The potential-ratings lines (batting, fielding,
pitching…) are worded as today. They end in a subtotal row, **"Ceiling"**,
like the "Value" and "Surplus WAR" rows. Its tooltip: "His WAR as an
everyday player if he reaches his potential ratings." The same wording is
the tooltip for the Ceiling column.

**Reaching his ceiling** (the odds):

| Line | Label | Stat | Note |
|---|---|---|---|
| readiness, ahead | How developed he is | +33% | 0.8 WAR on today's ratings |
| readiness, behind | How developed he is | −40% | −1.5 WAR on today's ratings: a long way to go |
| age, young | Drafted at 18 | +20% | More time to develop; counts for less with a ceiling this high |
| age, old | Drafted at 22 | −46% | Less time to develop; costs less with a ceiling this high |
| starter | Starters often end up relieving | −38% | Most drafted starters don't stay in a rotation |
| reliever | Drafted as a reliever | +13% | Relievers reach the majors more often |
| work ethic | High work ethic / Low work ethic | +45% | (only when tapered) Counts for less with a ceiling this high (60%) |
| intelligence | High intelligence / Low intelligence | +13% | as above |
| durability | Injury-prone / Very injury-prone / Durable / Very durable | −28% | as above (Fragile / Wrecked / Durable / Iron Man) |
| switch hitter | Switch hitter | +7% | Lets you set the lineup either way |
| growth | Could outgrow his ceiling | 7% chance | High velocity (97 mph) and high work ethic |

- No line for age 21 (the reference age) or for normal makeup.
- The growth line adds WAR; it doesn't scale. So its stat is the chance,
  not a percentage change.

**Adjustments** (judgment):

| Line | Label | Stat | Note |
|---|---|---|---|
| pitcher balance | Hitter–pitcher balance | −11% | Keeps the board about half hitters, half pitchers |
| `DraftPitcherStuffModifier` | Stuff | −4% | Potential Stuff 45, low for a starter |
| `PitcherVelocityModifier` | Velocity | +2% | 96–98 mph |
| `ScoutingAccuracyModifier` | Scouting accuracy | −5% | Medium: the ratings may be off |
| `DraftSecondaryPersonalityModifier` | Leadership and personality | +3% | High leadership |

Today these show as their class names ("Draft Pitcher Stuff", "Pitcher
Velocity") with no note. They need a label map and notes: one place for
both (the ledger or the card), decided at build time.

**The verdict band** (the card's summary):
- **Likely range: 0.0–3.4 WAR.** Tooltip: "8 in 10 players like him end up
  in this range."
- **Chance he becomes a regular: 18%.** Tooltip: "an everyday player or a
  rotation spot in this league" (for a reliever, "a regular bullpen
  role").
- **Chance he outgrows his ceiling: 7%.**

### Relievers (2026-11-10, D)

You: the board pushed relievers well above where the league drafts them;
"if I followed this model as San Diego, I'd end up with nothing but
relievers." On 2042: 9 relievers in the top 25, the best at 5th (Brad
Nelson, a 2.8 ceiling, ahead of Mike Mooney's 7.2).

- **Why:** the fit's classes (2033–37) rated almost no draftee reliever
  above 2 WAR at potential: 12 of the 87 it saw. From the 2038 export on,
  14–39 a class are. So the fit's RP ×1.13 was read off low ceilings.
- **What they realized:** the relievers the fit ranked in its held-out top
  200 realized 0.53 of the prediction. The settled 2038–41 relievers
  realized 0.28, against hitters' 0.90 and starters' 0.57 (all short:
  their careers are young).
- **Decided:** refit only the reliever factor, on settled 2038–41
  draftees, relative to hitters: ×1.13 → **×0.35**
  (`reliever_factor`, `RELIEVER_CLASSES`). The rest of the fit stays on
  2033–37. Pitcher balance ×0.87 → ×0.97. The distribution's spreads are
  still read against the fit's own mean.
- **After:** held out on 2033–37, top 25 / 50 / 100 is 1.55 / 1.35 / 1.09
  (was 1.52 / 1.36 / 1.10). On 2042 the top 25 is 15 hitters and 10
  starters, and the best reliever is 90th.
- **Not done:** pricing relievers on the league's roster scale (the
  Current board's bullpen taper: an elite closer about 3.9 → 2.0). Held
  back as a second cut for the same problem.

### Order of work (2026-11-10)

This replaces "Order of work" below. Nothing gets built until you say so.

**A. The full-time scale and the Max Potential list**

*Built and committed 2026-11-10, not deployed.* Revised from the plan below:
- **No Max Potential tab** (you, 2026-11-10: "not sure that's actually
  valuable as a view, but useful as a ledger line"). The tabs stay
  **Current** and **Prospects**. `FULL_TIME` is still a profile, for the fit,
  and a companion of `CURRENT`. The Current card shows it as a reference
  row under Value ("As an everyday player", "As a reliever, at the leverage
  his stuff earns", "As a rotation starter"). It isn't counted, and it only
  appears where the roster gives him a different job: a part-time bat, a
  reliever, or a pitcher moved between the rotation and the pen (e.g. Andy
  O'Neal: RP on the roster, SP full-time).
- **The ceiling is on both league boards,** not on draft classes; C brings
  the draft board's own. `CEILING` is potential ratings, no modifiers, and
  `development=False`. Companions are `Companion` in
  `ranking/stages/companion.py`, keyed on the profile's `companions`.
- **The Ceiling column** is in the Batting and Pitching views, not Modeled.
  On the card it's a cell in the verdict band, after Value.
- **On yfmlb:** the Current pass takes about 17 s with both companions, and
  Prospects about 9 s. On the full-time scale, the rank correlation with
  Current is 0.985, and the top 500 has 14 relievers against 111.

1. **The profile.** `FULL_TIME = replace(CURRENT, name="full_time",
   league_replacement=False)` in `ranking/profiles.py`, added to
   `PROFILES`. A test holds it to no roster lines and to the potential and
   draft conventions: the talent leverage map at weight 1.0, and
   `MATCHUP_TILT` for relievers.
2. **Companion scoring.** One batch stage scores the batch on a second
   profile and keeps that profile's model-line WAR on the state. It's used
   three times:
   - Max Potential: the ceiling, his potential ratings' full-time WAR
     (decision 9)
   - the draft board: readiness (C1)
   - the potential board: readiness (E)

   Two things to get right:
   - **The breakdown store.** `scoring/runtime_components.py` collects each
     player's breakdown by id within one scope. A companion pass would write
     there too and clobber the card, so it runs in its own scope.
   - **The ceiling profile.** `Value` applies the development factors
     whenever it reads potential ratings (`self.develops`). The ceiling
     needs a potential profile without them, so the profile gets a flag.
3. **Storage and API.** A `ceiling_war` result field in `RankedResult` and
   `results_store._RESULT_KEYS`, plus a migration that adds the column (as
   `_migration_4` did for wRC+ and ERA). It also goes in GraphQL's
   `RankedPlayer` and in `web/service.py`'s payload fields.
4. **The league view.**
   - Add `full_time` to `LEAGUE_RANKING_METHODS` in `league_snapshot.py`,
     so a refresh scores three runs (about 8 s more on yfmlb), and to
     `_METHOD_LABELS`.
   - In the frontend: the method toggle in `league-view.ts` and
     `api.types.ts` gets the new labels: "Expected Value" (`overall`),
     "Max Potential" (`full_time`) and "Prospects" (`potential`). The
     method keys don't change, so stored runs and URLs keep working. The "Ceiling" column goes outside the
     default view, and the ceiling goes on the card.
   - The legacy engine has no full-time profile, so the tab is v2 only.
   - Draft-class views don't get the tab. A draftee's current-ratings value
     is his readiness, which reaches the card in C.
5. **Tests.** Cover the third method in `test_league_snapshot`. The
   existing golden flows don't move. Deploy when you ask.

**B. The fit, on the full-time scale**

*Steps 1–3 done 2026-11-10 (script uncommitted, artifact in a scratchpad,
not in `ranking/artifacts/`).*
- **The refit barely moved,** as expected: the full-time profile reproduces
  the values the 2026-11-09 fit was made on. On A, at 3 WAR potential, for a
  21-year-old hitter with 0 readiness:
  - potential exponent +1.16
  - readiness ×1.33 per WAR
  - SP ×0.62, RP ×1.13 (wide)
  - age 18 / 19 / 20 / 22+: ×1.52 / ×1.71 / ×1.47 / ×0.54
  - age ≤19 × potential −0.49, age 22+ × potential +0.23
  - WE H / L ×1.45 / ×0.64, INT H / L ×1.13 / ×0.75
  - fragile ×0.71, durable ×1.05
- **The ship checks now judge the board as it would ship:** the fit times
  the lines it doesn't replace, then the balance. Those lines are Stuff,
  velocity, scouting accuracy, secondary personality, batted-ball profile
  and switch hitter (`KEPT` in the script). With them on, the balance is
  **pitchers ×0.93** (×0.89 without).
- **Pitcher share,** classes 2033–41: 47 / 44 / 49 / 52 / 59%. Every bucket
  passes (the board today: 38 / 55 / 52 / 58 / 58%).
- **Held out, one class at a time:**

  | | rho | top 25 | top 50 | top 100 |
  |---|---|---|---|---|
  | A: board | 0.366 | 1.50 | 1.27 | 1.08 |
  | A: fit | **0.407** | **1.54** | **1.34** | **1.09** |
  | B: board | 0.325 | 4.56 | 3.53 | 2.37 |
  | B: fit | **0.370** | **4.86** | **3.59** | **2.42** |

1. **Restore** `ranking/fitting/draft_odds.py` from the stash. Readiness
   and outcome A come from the `full_time` profile. Drop
   `LEAGUE_REPLACEMENT` and the label exclusion. The ceiling still comes
   from the draft profile's model lines. Discard the old artifact.
2. **Refit the mean.** Rebuild the draftee table with no cache (about
   25 s). Compare the factors with 2026-11-09's: the age × potential terms
   and the SP factor are the likeliest to move.
3. **Rerun the ship checks.** The held-out top 50 on A must be no worse than
   the board's, and every bucket must stay within 40–60% pitchers with the
   balance factor refit. If they fail, retry the step 2 variants first.
   The Stuff and velocity modifiers stay (open question 3) and only move
   pitchers, so the balance factor is fit with them applied. Otherwise the
   buckets would drift off 50/50 once they're on the board.
4. **Fit the distribution.** Run its checks and the ranking-rule comparison
   for open question 1. Also test your Stuff and velocity argument (open
   question 3): do high Stuff or 96+ velocity raise the chance he sticks or
   widen the upside (P90 against the ceiling), with the mean held fixed?
   Steps 5–7 answer the growth half of it. They stay as judgment either
   way, and the result could argue for a bigger upside than they give
   today.

   *Done 2026-11-10 (prototype in a scratchpad; it goes into the script
   with B7, which refits it).* Held out one class at a time, classes
   2033–37, about 2,200 draftees:
   - **The shape:** P(A > 0) by logistic regression, and A given A > 0 as a
     gamma, spread by side. A lognormal was tried and dropped. Hitters'
     log spread is 1.9, which inflates its mean about 5× and needs pitchers
     ×1.83 to balance.
   - **The mean stays Poisson.** The hurdle's own E[v] ties it (rho 0.412
     against 0.407, top 25 1.50 against 1.54, top 100 1.08 against 1.09).
     By this plan's rule, Poisson keeps the mean and the hurdle supplies
     the shape: the positive part's mean is the Poisson mean / P(A > 0).
   - **P10–P90 is the wrong check.** P10 is 0 for nearly everyone, since
     most draftees bust more than 10% of the time, so "the likely range"
     always starts at 0. What can be checked is P90: 12% land above it
     (target 10%).
   - **The tail is thin where it matters.** At 4+ WAR of ceiling, 34%
     became regulars against 21–23% predicted; at 0.5–1.5, 8–13% against
     5%. A spread that varies with the ceiling didn't help: it got tighter
     at high ceilings. This is the upside the growth outcome (5–7) is for.
   - **Ranking rules (open question 1):** neither the surplus over the
     league's price nor γ = 1.5 ranks better than E[v]. The surplus is far
     worse (top 25 1.05 against 1.50) and puts 72% pitchers in the top 25.
     E[v] stays.
   - **"A regular"** on the full-time scale: hitter 1.71 and SP 1.98 (the
     league's prices); RP 0.19, the median team's 8th-best MLB reliever on
     the full-time scale. The bullpen prices are on the slot-leverage scale,
     so they can't be used. P(regular) is calibrated except at the top
     decile (0.34 predicted against 0.41 observed).
   - **Stuff and velocity, the mean held fixed** (the model without those
     two modifiers), pitchers:

     | | n | E[v] pred | A observed | regular, pred / obs |
     |---|---|---|---|---|
     | velo 96+ | 272 | 0.58 | **0.68** | 0.13 / **0.17** |
     | velo 93–95 | 610 | 0.52 | 0.50 | 0.10 / 0.11 |
     | velo ≤92 | 335 | 0.39 | **0.46** | 0.06 / **0.10** |
     | Stuff P 55+ | 279 | 0.70 | 0.71 | 0.19 / 0.21 |
     | Stuff P 45–50 | 770 | 0.45 | 0.48 | 0.07 / 0.10 |
     | Stuff P ≤40 | 168 | 0.36 | **0.46** | 0.06 / 0.07 |

     - **96+ velocity supports your argument, modestly:** about 17% more
       realized than the model expects, and more regulars. The chance he
       sticks is as predicted (0.45 against 0.44): velocity buys upside, not
       survival.
     - **High Stuff adds nothing past the model.**
     - **The low end beats the model too,** and that's where the modifiers
       cut (about ×0.88). It's likely low ceilings growing; B6 separates it.
       It bears on open question 4.
     - The fit classes are old exports, so this is current velocity, not
       potential.
5. **The ceiling panel.** One row per draftee per later look: the draft
   classes joined by ID to the prospect exports (2038–42, the own-scout
   files, not `-osa`) and the snapshot. Each look is scored with the
   Ceiling profile (potential WAR, model lines), with potential Stuff and
   velocity alongside. Then describe it:
   - how often the ceiling grows into a useful player, against how often it
     falls, by side, age, WE, INT, AD, velocity and potential Stuff
   - whether the 2026-11-10 POT numbers hold in WAR
   - O'Neal, Linger and Lujan come out as you remember them

   Set the "outgrows" margin here (for example +1 WAR past the draft-day
   ceiling, and at least a regular's price), and look at who sits just
   either side of it before fixing it.

   *Built 2026-11-10 (scratchpad scripts; they go into the repo with B6).*
   The panel covers 8,771 draftees from classes 2033–41 (a re-entered
   draftee keeps his last class), and 32,375 looks: draft day, the
   2038–42 prospect exports and the snapshot. Every look is scored with
   `CEILING`. "A regular" uses the B4 thresholds (hitter 1.71, SP 1.98, RP
   0.19).
   - **Low ceilings do grow, more often in WAR than in POT.** Of the 4,467
     draftees in classes 2033–39 whose draft-day ceiling was below a
     regular's price, **7.5%** are regulars by the snapshot (3–11% by
     class). On POT the figure was 2.5%, but POT 55+ is a higher bar. Of
     those at or above a regular's price on draft day, 65% fell 1+ WAR or
     left, and 39% are still regulars.
   - **What drives it, in WAR,** with the draft-day ceiling held fixed:
     teens ×2.15 (1.80–2.69), pitchers ×1.38 (1.12–1.68), **adaptability**
     H ×1.41 (1.04–1.73) and L ×0.81 (0.59–0.97).
   - **Work ethic and intelligence show nothing:** WE H ×1.00 (0.78–1.31),
     INT H ×1.19 (0.84–1.66). That's against the POT look and your read.
     WE does move the mean, through outcome A, but not the chance a low
     ceiling grows into a regular.
   - **Velocity: a little; Stuff: nothing,** for pitchers in classes
     2033–39:
     - per mph ×1.01 (0.95–1.07); by band, ≤92 6.7%, 93–95 10.2%, 96+
       10.4%
     - only the 2039 class has potential velocity: ×1.10 per mph
       (0.96–1.38), 25 regulars
     - potential Stuff per 10 ×0.96 (0.79–1.17)
   - **Your examples:**
     - **Linger** (2037, 21): ceiling 1.44 → 3.21 WAR. He outgrew it.
     - **Lujan** (2034, 18): 1.14 → 3.09. He outgrew it.
     - **O'Neal** (2035, 18): 2.85 → 2.89, with a dip to 1.97 in between.
       His POT rose 40 → 60 and his Stuff P 45 → 75, but the WAR model
       already valued his 96 mph at 18 on draft day. His POT moved; his
       WAR ceiling didn't.
   - **Candidate margins** (classes 2033–39, still in the league, a regular
     by the snapshot):

     | past the draft-day ceiling | draftees | share | low ceilings |
     |---|---|---|---|
     | +0.5 WAR | 503 | 7.5% | 286 |
     | +1.0 WAR | 344 | 5.1% | 218 |
     | +1.5 WAR | 225 | 3.3% | 166 |
     | +2.0 WAR | 158 | 2.3% | 119 |

     Either side of +1.0 the WAR change and the POT change don't line up
     cleanly:
     - **Just under (+0.6):** mostly 18-year-old hitters whose POT didn't
       move (Johnny Krinke 45 → 45, Raul Galvan 45 → 45). Ramon Munoz, a
       real grower (POT 35 → 60), also sits there at +0.64.
     - **Just over (+1.3):** clear growers (Chris Haga 45 → 60, J.J. Lennan
       60 → 70, Hugo Gomez 55 → 65), but also flat ones (Dave Carter
       45 → 45).

     *Recommend +1.0 WAR and a regular:* it keeps most of the clear growth
     and drops most of the drift. +1.5 is cleaner, but there are a third
     fewer cases to fit on.
     **Decided 2026-11-10: +1.0 WAR past the draft-day ceiling, and a
     regular** (you: "the +1.0 case is legit").
6. **Fit the growth odds.** A logistic fit of outgrowing on draft-day
   inputs:
   - potential WAR (lower ceilings have more room)
   - readiness, age, side and role
   - WE, INT, AD and durability
   - for pitchers: velocity, potential Stuff and pitch count

   Fit it on the panel (classes 2035–41, the export formats closest to
   potential velocity) and on outcome A (2033–37), bootstrapped, and
   compare the two.

   *Done 2026-11-10.* The panel is `ranking/fitting/ceiling_panel.py`, and
   the fit is in `draft_odds.py` (`growth_design`, `report_growth`; pass
   `--panel` to cache the panel). The two sources measure different things:
   - **Panel:** his *ceiling* outgrew draft day. Classes 2035–41: 348 of
     6,797 (5.1%).
   - **A:** his *value now* outgrew it. Classes 2033–37: 75 of 3,840 (2.0%).

   Odds of outgrowing, with 90% ranges. The reference draftee is a hitter,
   20–21, 3 WAR of ceiling, 7 years on:

   | | panel | A |
   |---|---|---|
   | drafted 19 or younger | **×1.49** (1.18–1.85) | **×2.67** (1.67–4.35) |
   | drafted 22+ | ×0.76 (0.54–1.00) | **×0.44** (0.21–0.77) |
   | adaptability H | **×1.34** (1.06–1.65) | ×1.22 (0.76–1.99) |
   | adaptability L | ×1.01 (0.75–1.28) | ×0.71 (0.37–1.12) |
   | work ethic H | ×1.06 (0.86–1.32) | ×1.18 (0.81–1.74) |
   | work ethic L | ×0.77 (0.54–1.06) | ×0.62 (0.33–1.03) |
   | intelligence L | ×0.96 (0.67–1.25) | **×0.49** (0.26–0.82) |
   | RP (draft day) | **×2.35** (1.71–3.28) | ×1.25 (0.67–2.17) |
   | SP | ×0.82 (0.61–1.11) | ×0.62 (0.35–1.07) |
   | velocity, per mph | ×1.02 (0.97–1.08) | ×1.03 (0.89–1.17) |
   | potential Stuff, per 10 | ×0.97 (0.82–1.09) | ×0.72 (0.48–1.07) |
   | pitch count, per pitch | ×1.01 (0.89–1.14) | ×0.81 (0.51–1.09) |
   | log ceiling | ×1.17 (1.09–1.25) | ×0.98 (0.83–1.11) |
   | readiness, per WAR | ×1.09 (0.94–1.28) | ×1.25 (0.91–1.65) |
   | years on | ×1.19 (1.14–1.26) | ×0.86 (0.74–1.00) |

   - **Both sources agree on age and makeup.** Youth and adaptability help;
     low work ethic and low intelligence hurt. High work ethic barely
     moves it.
   - **Velocity and Stuff don't predict outgrowing in WAR,** in either
     source. On POT (the 2026-11-10 first look) they did: ×1.11 per mph,
     ×1.48 per 10 Stuff. A higher POT doesn't always mean more WAR (see
     O'Neal). With B4, the evidence for open question 3 is: 96+ velocity
     raises what he realizes a little (about +17%); neither raises the
     chance he outgrows his ceiling.
   - **Relievers' ceilings grow** (×2.35 on the panel). A reliever's
     ceiling starts small, and the RP regular bar is low (0.19).
   - **Years cut opposite ways.** The panel's ceilings keep growing with
     time. A's oldest classes lose value to decline and to players
     leaving.
   - **Held out on the panel**, P(outgrows) is calibrated up to the 7th
     decile and runs high at the top (0.13 predicted against 0.085
     observed). Leaving out an end class makes "years on" extrapolate.
7. **Fold growth into the distribution** as its third outcome (step 4's
   model refit with it). Rerun every check in "The distribution" and the
   step 2 ship checks. Then report:
   - how much of each draftee's E[v] comes from the growth outcome
   - the growth fit's velocity and Stuff factors next to
     `DraftPitcherStuffModifier`'s and `PitcherVelocityModifier`'s
     tables, for open question 4

   *Done 2026-11-10* (`Odds` and `report_odds` in `draft_odds.py`).
   - **Borrowed growth** (you: borrow, but keep "the WE bump and probably
     at least some of the velo bump"):
     - **Who outgrows** comes from the panel's growth odds. `WE H` is held
       near ×1.30 and velocity near ×1.06 per mph by a tight prior
       (`GROWTH_JUDGMENT`); the rest is fit.
     - **How often it's realized:** one shift fit on A. Odds ×0.24: about
       a quarter of the ceilings that grow turn into value by 25+.
     - **How far:** A past ceiling + 1 is a gamma with mean 0.65 WAR.
     - **Everything else:** refit on the draftees who didn't outgrow.
   - **Held out on A** (classes 2033–37; this population is joined to the
     panel, so the board's numbers differ a little from B3's):

     | | rho | top 25 | top 50 | top 100 |
     |---|---|---|---|---|
     | board | 0.375 | 1.57 | 1.32 | 1.12 |
     | Poisson | **0.426** | **1.62** | **1.35** | 1.13 |
     | three outcomes | **0.426** | 1.52 | 1.33 | **1.14** |
     | three outcomes, no judgment | 0.426 | 1.52 | 1.33 | 1.14 |

     The three outcomes tie Poisson overall and trail it at the top 25.
     The judgment doesn't cause that: with or without it, the numbers match
     to two decimals.
   - **The judgment barely reaches E[v].** Realized outgrowing is about 2%
     of draftees, so a 6%-per-mph change in its odds moves E[v] almost not
     at all. If velocity is to move the board, the place is
     `PitcherVelocityModifier`, not the growth odds.
   - **The shape got better where B4 was short:**
     - above P90: 13% overall (target 10%), 10% in the top 100, and 10% at
       4+ WAR of ceiling (B4: 15%)
     - P(regular) at 4+ WAR of ceiling: 0.28 predicted against 0.37
       observed (B4: 0.21); at the top decile, 0.37 against 0.43
     - still short at low ceilings (0.04 against 0.09)
   - **P(outgrows) on A barely discriminates:** 1–4% predicted, 0–4%
     observed, with the top decile high (0.04 against 0.02).
   - **E[v] from outgrowing:** a median of 14% of his E[v], and 26% at P90.
   - **Ship checks:**
     - pitcher balance ×0.88; buckets 42 / 44 / 51 / 54 / 59%
     - held-out top 50 1.33, against the board's 1.32
     - both pass
   - **Open question 4, the factors side by side:**
     - **Velocity:**
       - growth odds: ×1.06 per mph (judgment; ×1.02 as fit)
       - `PitcherVelocityModifier` scales his whole value: from ×0.88 at
         ≤87 to ×1.07 at 100+
       - B4: the low end beats the model, and 96+ realizes about 17% more
         than predicted
     - **Stuff:**
       - growth odds: ×0.95 per 10
       - `DraftPitcherStuffModifier` only cuts: SP ≤40 ×0.93 up to 55
         ×0.99; RP ≤45 ×0.93 up to 60 ×0.99
       - B4: low Stuff beats the model, and high Stuff adds nothing
8. **Write the artifact** `draft_odds_v1.json`: the mean, outcome and
   growth coefficients, the spreads, the margin, the balance factor, the
   bootstrap ranges and the held-out tables. The manifest hashes every artifact, so the file
   alone marks stored runs stale. Keep it uncommitted and undeployed until
   C lands, then commit them together.

   *Done 2026-11-10; the file is in the session scratchpad until C copies it
   into `ranking/artifacts/`.* **Decided: Poisson keeps the board's mean**
   (B7's three outcomes trailed it at the top 25). The three outcomes
   supply the card's distribution. The rest's mean there is set so the
   whole matches E[v]: (E[v] − q × what outgrowing is worth) / (1 − q).

   The artifact adds `judgment` (the kept lines, `VELOCITY_STEPS`, what the
   odds replace), `regular`, `distribution` (the growth, sticks and gamma
   coefficients, the realized shift, the outgrown excess) and the
   distribution's checks. With the new velocity steps and no Stuff line:
   - **Pitcher balance:** ×0.87. Buckets 45 / 44 / 49 / 53 / 59%; they
     pass.
   - **Held out on A:** top 25 1.52, top 50 **1.36**, top 100 1.10, rho
     0.408. The board is 1.50 / 1.27 / 1.08 / 0.366, and the legacy
     modifiers gave 1.54 / 1.34 / 1.09.
   - The velocity steps were set from these same classes, so this check is
     partly in-sample for velocity.

**C. The stage**

*Built 2026-11-10, committed with `draft_odds_v1.json`, not deployed.*
- **Readiness:** a companion, `("readiness", FULL_TIME)`, on the draft
  profile. Companions now run before the value stage, and keep his
  model-line WAR (`CompanionValue.model`), as the fit read readiness.
- **The odds:** in `ranking/draft_odds.py` (`DraftOdds`), switched on by
  the profile's `odds` flag. Its columns are held to the fit's `design` and
  `growth_design` by a test, row for row.
- **The ledger, in this order:**
  - the talent lines (his ceiling)
  - "Reaching his ceiling" (the `development` stage):
    - a base line, "Draftees with his ceiling" ("reach 44% of it"), that
      carries the reference draftee's rate
    - one percentage line per factor
    - "Could outgrow his ceiling" as an added line, with its chance and
      what lifts it
  - "Adjustments": the kept modifiers with notes, velocity (upside only)
    and the hitter–pitcher balance
- **Never below replacement.** The deficit branch doesn't apply on the
  draft board.
- **The card:**
  - a "Ceiling" subtotal under the talent lines
  - the section heading "Reaching his ceiling" (the potential board's
    development factors get it too)
  - every multiplier stat as a % change
  - a label map for the kept modifiers
  - under the verdict band, "Likely range 0.5–5.1 WAR · Chance he becomes
    a regular 54% · Chance he outgrows his ceiling 3%"

  These are stored as `war_low`, `war_high`, `p_regular` and `p_outgrows`
  (migration 9). Draft rows also carry `ceiling_war`, so the Ceiling column
  shows on class views too.
- **The fit script's "board"** is now this board. Its factors are parsed
  only from `x…` stats.
- **The draft-class goldens** were regenerated. The league golden didn't
  move.

1. **Readiness** in the draft profile, from the companion stage: his
   current ratings' full-time WAR.
2. **The odds** in `ranking/stages/value.py`. They replace `AgeModifier`,
   `DraftBatterOverallModifier`, `DraftPitcherOverallModifier` and the
   development factors (decision 2). These stay: `ScoutingAccuracyModifier`,
   `DraftSecondaryPersonalityModifier`, the switch-hitter factor and the
   Control floor. `DraftPitcherStuffModifier` and `PitcherVelocityModifier`
   also stay, as judgment applied after the odds (open question 3).
   *Revised 2026-11-10 (open question 4): Stuff is dropped, and velocity is
   the upside-only `ranking/draft_odds.velocity_factor`.*
   - **Ledger:** the talent lines up to the "Ceiling" subtotal, then one
     line per factor under "Reaching his ceiling", summing to E[v]. The
     wording is in "Ledger wording" above.
   - **Growth:** its own line, "Could outgrow his ceiling", worth +x WAR of
     E[v]. Its inputs go in the note, so the card says why he has upside
     past the scouting.
   - **Below replacement:** E[v] is never negative, so for the draft
     profile the deficit branch in `_modified` (personality dividing the
     deficit) goes away. The model orders the bottom of the board.
   - **Two-way:** the odds apply to each side, in that side's role, and the
     two-way share reads the sides after the odds. The fit only used the
     primary side, so check the few two-way draftees by hand.
3. **The card.** The range, the chance he's a regular and the chance he
   outgrows his ceiling go in the v2 verdict band. Readiness and the ceiling
   go in the value build. The percentage stats, the label map for the kept
   modifiers and the new section heading are all in "Ledger wording".
4. **The manifest.** The stage reports the artifact in `artifacts`. The
   draft-class golden flows get regenerated.

**D. Eval and review.** `eval_rankings.py --engine v2 --against HEAD` on
the draft classes. For you to review:
- the movers: who climbs, who falls, and RPs in the top 100
- the pitcher share per bucket, before and after, kept as a permanent part
  of the draft report
- the distribution's coverage
- **growth:** the draftees whose E[v] gains most from the growth outcome,
  and the held-out past draftees who did outgrow their ceilings. Where did
  the new board rank them, and where did today's board?
- **the taper case** (open question 5): no low-ceiling prospect with
  maxed makeup and velocity passes a generational one. Also show how much
  each makeup and growth factor moves prospects at 1, 2.5, 4 and 6 WAR of
  ceiling, so you can judge the taper's scaling.

It ships on your call.

*E now has its own plan, `plans/prospect-odds-plan.md` (2026-11-10): the
remaining gap instead of the multiplier, age for level, and a judgment
bridge for the unsettled teens.*

**E. The potential profile.** B–D again on the 2038–41 prospect exports,
with level as an input. The ceiling panel (B5) already covers these
players' later looks, so their growth odds come from it directly. A
prospect who has already outgrown his draft ceiling keeps the factors his
traits earn, not credit for growth he's already shown. The org rankings read the potential board
(`web/org_rankings.py` has its curve in potential WAR), so recheck them
afterwards.

**F. Refit on peak** once the archive has a second season (April 2043):
step 6 under "Order of work" below. Each season snapshot is also another
look for the ceiling panel. Refit the growth odds then too, since late
growth (after 25) is what the panel sees least.

## What the past classes show (2026-11-09)

The data is the yfmlb 2033–37 classes (about 1,200 draftees each), scored by
v2 as of draft day. They're judged against MLB stats through 2042 and the
December 2042 snapshot.

**The board is the best case, not the expected case.** Here is a draftee's
actual peak (mean of his best 3 MLB seasons) against the WAR the board
gave him, for classes 2033–35:

| Group | Actual peak per board WAR |
|---|---|
| SP, drafted 19 or younger | 0.09 |
| SP, drafted 20+ | 0.21 |
| RP, drafted 20+ | 0.19 |
| Hitter, drafted 19 or younger | 0.19 |
| Hitter, drafted 20+ | 0.32 |

**Starters rarely stay starters.** Of SP draftees who reached MLB, these
shares spent most of their career starting:

| Board rank | Mostly started |
|---|---|
| 1–25 | 45% |
| 26–100 | 33% |
| 101+ | about 21% |

The board values every starter-capable pitcher as a full-time SP.

**RP draftees out-perform their rank.** At ranks 251–500 and draft age
20–21, 83% of RP draftees reached MLB, against 16% of SP draftees.
Their career WAR was 1.10 against 0.10. The sample is small: only about 30
RP draftees ranked in the top 150.

**Readiness is what separates college and high-school draftees, not age
itself.** Raw numbers favour older draftees. Through age 26, top-50 pitchers
drafted at 20–21 produced 5.0 WAR against 2.0 for those drafted at 19 or
younger, and top-50 hitters 9.2 against 4.2. But older draftees arrive more
developed. Once the value of his *current* ratings is held fixed, younger
is better, which is what `AgeModifier`'s "dev runway" says. So the board's
problem with age isn't the age table. It's that it barely credits how
developed a draftee already is.

## The model

A Poisson regression (log link) of what a draftee realizes, on:

| Input | Why |
|---|---|
| log potential WAR (the model lines, before modifiers) | the ceiling; a coefficient under 1 means the best prospects realize a smaller share |
| **readiness**: v2's WAR on his *current* ratings | how far along he is. Draft-day OVR is 20 for 99% of draftees, so it can't be used |
| age at draft | runway, given readiness |
| side / role: hitter, SP, RP (the role v2 values him in) | SPs' potential WAR assumes he starts; most won't |
| work ethic, intelligence, injury proneness | refit jointly, so they don't double-count with the rest |

The prediction is his **expected realized WAR**. It replaces the potential
WAR × modifiers as the board value, and the demand step still runs last.
The ledger shows the potential WAR, then one line per odds factor (e.g.
"age 18 ×1.9", "SP ×0.57"), so the card still says why.

### Feasibility fit (2026-11-09, scratch, not committed)

There are two outcomes to fit on:
- **A — value now:** v2's WAR on his December 2042 *current* ratings, for
  everyone 25 or older now, and 0 if he's left the league.
- **B — MLB WAR through age 26:** only for players whose window is complete.

Multipliers on what he realizes (reference: hitter, age 21, normal makeup):

| | A: value now | B: MLB WAR to 26 |
|---|---|---|
| log potential WAR | +0.81 | +1.46 |
| readiness, per WAR of current value | ×1.48 | ×1.40 |
| SP | ×0.57 | ×0.32 |
| RP | ×0.88 (wide) | ×0.63 (wide) |
| age ≤18 / 19 / 20 / 22+ | ×2.0 / ×2.2 / ×1.5 / ×0.5 | ×1.6 / ×3.6 / ×2.0 / ×0.8 |
| WE H / L | ×1.32 / ×0.67 | ×1.55 / ×0.44 |
| INT H / L | ×1.13 / ×0.81 | ×1.29 / ×0.72 |
| fragile | ×0.78 | ×0.40 |

For comparison, today's factors are WE ×1.25 / ×0.75, INT ×1.15 / ×0.95 and
fragile ×0.75.

Ranking on held-out classes (leave one class out, mean per class):

| | rho | top 25 | top 50 | top 100 |
|---|---|---|---|---|
| A: board today | 0.384 | 1.41 | 1.21 | 1.04 |
| A: fitted odds | **0.436** | 1.38 | 1.23 | **1.11** |
| B: board today | 0.325 | **4.56** | 3.53 | 2.37 |
| B: fitted odds | **0.363** | 4.40 | 3.26 | **2.55** |

The fitted odds rank the class better as a whole and from about rank 50
down. **At the very top they're no better than today's board.** Today's
board keeps something there, probably the velocity and Stuff modifiers.
That's what step 2 tests.

## Decisions (2026-11-09)

1. **The outcome to fit on.**
   - **A (value now)** matches your draft criterion, holding potential,
     and has no playing-time noise.
   - **B (MLB WAR)** is the real result, but it's noisier, and it favours
     players who got MLB chances.
   - *Recommend A for the fit and B as the check, as the makeup factors did.*
   - **Decided: A for the fit, B as the check.**
2. **What it replaces.**
   - *Recommend replacing:* `AgeModifier`, `DraftBatterOverallModifier`,
     `DraftPitcherOverallModifier`, and the makeup / durability factors.
   - *Recommend testing as inputs before deciding:*
     `DraftPitcherStuffModifier` and `PitcherVelocityModifier`.
   - *Recommend keeping as judgment:* `ScoutingAccuracyModifier` (every
     draftee is High or Very High, so it can't be fit) and
     `DraftSecondaryPersonalityModifier`.
   - **Decided: as recommended.**
3. **The makeup taper.** You tapered makeup by potential WAR so a mediocre
   prospect with maxed makeup can't pass a generational one. A potential
   coefficient under 1 already compresses the top. Keep the taper on top,
   or let the fit decide (and check the case you cared about)?
   **Decided: keep the taper.** The fitted makeup factors are tapered by
   potential WAR as they are today.
4. **The SP factor.** It folds the SP→RP outcome into one multiplier. The
   alternative is an explicit blend of P(starts) × SP WAR + (1 − P) × RP
   WAR. That's more honest, but it needs P(starts) by board level, which
   is fit on fewer players. *Recommend the multiplier first.*
   **Decided: the multiplier.**
5. **Risk (the "balance").** Plain expected value is neutral between a sure
   small career and a long shot at a big one. The architecture plan's
   E[v^γ] dial sets that, once the odds are real. **Deferred: stay
   neutral (plain E[v]).** The odds model predicts the mean only, so a
   dial would also need the spread of outcomes, and outcome distributions
   picked no better a top 100 when tried in phase 6. Revisit only if the
   step 4 movers trade floor for ceiling in a way you don't like.
   **Revisited 2026-11-10: see decision 7 and open question 1.**
6. **Scope.** Only the draft-class board, or also the `potential` profile
   (the league's prospects)? Those players have real current ratings and
   more years of data. *Recommend draft classes first.*
   **Decided: both.** Draft classes first. Then the `potential` profile
   from the 2038–41 minor-league prospect exports
   (`datasets/yfmlb-20xx-prospects.csv`, about 4,000 players each),
   judged on the 2042 snapshot. It only has a 1–4 year window, so expect a
   weaker fit. Level (R → AAA) is a readiness input there too.

## Order of work

*Superseded by "Order of work (2026-11-10)" above; kept for the record.*

1. **Fit script** `ranking/fitting/draft_odds.py`: the draftee table (this
   one's scratch version, built properly), the fit for both outcomes, the
   held-out comparison against the board, and an artifact
   `ranking/artifacts/draft_odds_v1.json`. **Done 2026-11-09** (see
   "Steps 1–2 results").
2. **Close the top-of-board gap.** Try velocity, Stuff and pitch count as
   inputs, a potential curve per side, and weighting the top. Ship only if
   the held-out top 50 is no worse than today's board on A, and the pitcher
   share stays within about 40–60% in every bucket, with the side-balance
   factor set (see "Risk" below). **Done 2026-11-09: passes.** None of the
   listed tries closed it. An age factor that changes with potential did.
3. **The stage.** Odds factors are applied in `ranking/stages/value.py` in
   place of the replaced modifiers, with ledger lines, the card, and
   `ranking.manifest` picking up the artifact.
4. **Eval.** `eval_rankings.py --engine v2 --against HEAD` on draft classes,
   and movers for you to review: who climbs, who falls, and RPs in the top
   100. Plus the pitcher share per rank bucket, before and after, as
   a permanent part of the draft report.
5. **The `potential` profile:** steps 1–4 again on the 2038–41 prospect
   exports, with level as an extra input.
6. **Refit** once the season archive has more than one snapshot, so the
   outcome can be peak value rather than value as of December 2042. That's
   also when durability and makeup can be judged on how long a player stays
   at his peak, not only on whether he's there at one snapshot.

## Steps 1–2 results (2026-11-09)

`python -m ranking.fitting.draft_odds --data-dir fly_data` builds the
draftee table (classes 2033–41, about 10,600 draftees), fits A and B, picks
the side-balance factor and runs the held-out check. It writes
`ranking/artifacts/draft_odds_v1.json`. `--table x.pkl` caches the table,
which takes about 25 s to build.

**What didn't close the gap.** These were each tried held out, with pitchers
re-balanced each time:
- velocity as a number, or in bands
- potential Stuff: ×0.91 per 10 with potential WAR held fixed, so v2 already
  prices it a little high
- pitch count
- a potential curve per side
- weighting the top ×3

The top 25 stayed at or below the board. So did folding each legacy
modifier into the ceiling one at a time. Only all of them together (the
board's WAR as the ceiling) matched it.

**What did.** The misses at the top were 22-year-olds who became stars:
Dylan Morgan (board 6, fit 49), Mike Buzzard (6 → 160) and Dan Greenway
(17 → 56). A flat age-22+ factor of ×0.52 sank them. Letting the age factor
change with potential fixed it:
- **Teens:** the runway bonus fades as the ceiling rises. Age ≤19 ×
  potential is −0.48, 90% −0.72 to −0.20.
- **22+:** the penalty shrinks. Age 22+ × potential is +0.24, 90% −0.16 to
  +0.70.

B, fit on its own, agrees on both directions (−0.35 and +0.60).

The fit (A). Factors are read at 3 WAR potential, on a hitter aged 21 with
0 readiness:
- potential: exponent +1.16
- readiness: ×1.33 per WAR
- SP ×0.62, RP ×1.13 (wide)
- age 18 / 19 / 20 / 22+: ×1.52 / ×1.72 / ×1.47 / ×0.54
- WE H / L: ×1.45 / ×0.62
- INT H / L: ×1.13 / ×0.76
- fragile ×0.72, durable ×1.05
- makeup is fit tapered, so these are the full-weight factors

**Side balance:** pitchers ×0.89.

Pitcher share, classes 2033–41:

| | 1–25 | 26–50 | 51–100 | 101–200 | 201–400 |
|---|---|---|---|---|---|
| Board today | 38% | 55% | 52% | 58% | 58% |
| Fit | 55% | 58% | 56% | 55% | 57% |
| Fit, pitchers ×0.89 | 44% | 42% | 52% | 53% | 58% |

Held out, one class at a time, with the balance factor applied:

| | rho | top 25 | top 50 | top 100 |
|---|---|---|---|---|
| A: board | 0.367 | 1.50 | 1.26 | 1.07 |
| A: fit | **0.409** | **1.51** | **1.33** | **1.09** |
| B: board | 0.325 | 4.56 | 3.53 | 2.37 |
| B: fit | **0.372** | **4.81** | **3.60** | **2.43** |

Per class, rho on A is better in all 5 classes, and the top 25 on A in 4 of
5. 2036 is −0.25, about two players. B is noisy at the top class by class.
The top-end gain is modest. What step 2 delivers is that the fit is no
longer worse there.

For step 3:
- **Readiness** is v2's WAR on his *current* ratings. The value stage scores
  one set of ratings per profile, so the draft profile will also need its
  current-ratings model lines.
- **The age factors** become a ledger line like "age 18 ×1.2 at 5.0
  potential WAR", in the same form as the makeup taper.

## On hold: waiting on the current-ratings model (2026-11-10)

*Lifted 2026-11-10: 7f34e1a landed. The full-time profile in "Restart on
the full-time scale" replaces the approach in item 2 below.*

Step 3 waits until two pieces of work in other sessions land.

### Shelved (2026-11-10)

The code is in a git stash, not in the working tree:
- `ranking/fitting/draft_odds.py`, including the league-replacement
  exclusion
- `ranking/artifacts/draft_odds_v1.json`

It was shelved so it can't affect the other session. The artifact alone
changes `ranking.manifest.model_version`, which marks stored runs stale.

To restore, find the stash by its message, since the index shifts as stashes
are added:

    git stash list | grep "shelf: draft-odds"
    git stash apply stash@{N}      # then drop it once it's committed

The artifact is stale anyway once the current-ratings model changes. Restore
the script, rerun the fit and let it write a fresh artifact. The cached
draftee table was in a session scratchpad and is gone, so expect the ~25 s
rebuild.

**What the script does**, so it can be rebuilt if the stash is ever lost:
- **The draftee table:** one row per scored draftee, classes 2033–41,
  built from:
  - the v2 `draft_class` ranking: model-line WAR, side, role, pre-demand
    score and rank, and each modifier's and development factor's value,
    parsed from the ledger's `x1.05` stat
  - the v2 `overall` ranking of the class: readiness
  - the `overall` ranking of the snapshot: outcome A, 0 if he's gone,
    settled at snapshot Age ≥ 25
  - MLB WAR by year (split 1, level 1, bat + pitch): outcome B through age
    26, settled when that season has been played
- **The fit:** a Poisson fit (sklearn `PoissonRegressor`, alpha 1e-4) on
  draftees with potential WAR ≥ 0.5, classes 2033–37. Columns:
  - log(potential WAR / 3)
  - readiness clipped to −4 to 3
  - SP, RP
  - age 18 / 19 / 20 / 22+, plus age ≤19 × log potential and age 22+ × log
    potential
  - WE H/L, INT H/L, fragile, durable, each multiplied by
    `development.weight(potential WAR)`
- **Then:** 200 bootstraps for the 90% ranges; the pitcher balance by
  bisection so the five buckets average 50%; leave-one-class-out held-out
  checks with the balance applied.

### More step 2 findings (2026-11-09)

All of these are held out over classes 2033–37, with pitchers re-balanced.
Board: A top 25 / 50 = 1.50 / 1.26, B = 4.56 / 3.53.

| Variant | A top 25 | A top 50 | B top 25 | B top 50 | Note |
|---|---|---|---|---|---|
| Base, flat age | 1.43 | 1.29 | 4.41 | 3.37 | |
| + velocity (per mph) | 1.42 | 1.25 | 4.41 | 3.39 | ×0.99 per mph |
| + velocity bands | 1.45 | 1.28 | 4.34 | 3.43 | 96+ ×1.34; ≤90 ×1.18 |
| + potential Stuff | 1.40 | 1.33 | 4.19 | 3.43 | ×0.91 per 10 |
| + pitch count (SP) | 1.43 | 1.28 | 4.69 | 3.42 | ×0.97 per pitch |
| Potential curve per side | 1.39 | 1.27 | 4.34 | 3.33 | |
| Top weighted ×3 | 1.43 | 1.31 | 4.56 | 3.48 | |
| Board WAR as the ceiling | 1.50 | 1.28 | 4.52 | 3.49 | legacy modifiers kept |
| Age fixed at B's factors | 1.35 | 1.25 | 3.91 | 3.42 | |
| Age, mean of A and B | 1.39 | 1.33 | 4.15 | 3.45 | |
| **Age × potential (kept)** | **1.51** | **1.33** | **4.81** | **3.60** | |

**One legacy modifier folded into the ceiling at a time.** None closes the
top-25 gap alone:
- `DraftPitcherOverallModifier` helps most: A top 25 1.47.
- `AgeModifier` and `DraftSecondaryPersonalityModifier` help B's top 25:
  4.57.
- Velocity and Stuff don't help.

The board's edge at the top was spread across modifiers. Mostly it was the
age table not sinking 22-year-olds.

**The A check is uneven across classes.** For 2036–37, only draftees who are
25+ in the snapshot count, so drafted teens drop out of that check in those
classes. 2036's held-out top 25 (the one class where the fit trails) is
judged on its college draftees only.

**How the scratch version differs.** The feasibility numbers
(rho 0.384 → 0.436) came from the scratch script, which used draft age plus
years to decide who is 25 now. The script uses the snapshot's own Age, which
moves some 2037 draftees. Both the board and the fit shift. The fit's edge
over the board is the same either way.

**The movers held out**, for step 4 to compare against. The fit climbs
young, high-WE hitters with modest potential (e.g. Gene Craig 33 → 4 and
David Robles 34 → 7 in 2034, both A ≈ 2.5). It drops low-readiness teen
SPs and 22-year-olds at 0 readiness.

1. **Your update to the current-ratings model files.** The ceiling (potential
   ratings through that model), readiness and outcome A all come from it, so
   `draft_odds_v1.json` goes stale when it lands. Then:
   - Refit with `python -m ranking.fitting.draft_odds --data-dir fly_data`,
     *without* a cached `--table`, since the cache holds the old model's WAR.
   - Recheck the step 2 ship checks: the held-out top 50 on A against the
     board, and every pitcher bucket within 40–60% with the balance factor
     refit.
   - The age × potential terms and the SP factor are the likeliest to move.
2. **League replacement level (the pitcher-WAR session).** That session
   changes the current-ratings ("overall") profile only. Its artifact,
   `ranking/artifacts/replacement_v1.json`, exists as of 2026-11-10, so the
   change is live in the working tree, though not committed. Spot-based, it
   brings three changes to that profile:
   - a "league replacement" MODEL line, the first-man-out WAR by role; for
     YFMLB about hitter 1.26, SP 1.90, RP 0.21
   - a "playing time" MODEL line for part-time bats (spots 8–12), scaling
     his WAR to 67–37% of a season
   - relievers' "leverage" line becomes their bullpen spot's leverage (1.86
     down to 0.71) at StatsPlus's fitted weight of 0.418, in place of the
     talent-based map at weight 1.0

   The draft and potential profiles are unchanged: talent map, weight 1.0,
   no replacement. So the ceiling stays on a full-time, StatsPlus scale.
   Outcome A and readiness have to be valued the same way as the ceiling.
   Otherwise:
   - most outcomes clip to 0
   - the SP/RP factors and the pitcher balance skew
   - relievers' readiness moves for reasons that have nothing to do with
     development

   - **Approach (replaces the shelved label exclusion).** Leaving lines out
     by label no longer works: it misses playing time and the leverage
     change. Instead, score outcome A and readiness on a copy of the
     profile with replacement off:
     `dataclasses.replace(CURRENT, league_replacement=False)`, run through
     `Value(profile, replacement=None)`. That's the pitcher-WAR session's
     suggestion. Drop the `LEAGUE_REPLACEMENT` exclusion in the shelved
     `_raw_war`. Before refitting, check that this copy reproduces the
     pre-change values: the talent leverage map at weight 1.0, and no
     playing-time line.
   - That copy also settles the earlier worry about the role choice: a
     pitcher's role, and with it his primary side, is chosen as it was
     before.
   - If the draft profile ever adopts league replacement or spot-based
     playing time, revisit this: either the ceiling and outcomes both carry
     it or neither does. The odds would then be a share of a
     roster-relative value, and the fit would need redoing on that basis.

**How the layers fit together.** This is your framing, with corrections:
1. **The current-ratings model** gives the WAR a set of ratings produces.
2. **The draft and potential profiles** run potential ratings through that
   same model. That's the ceiling: his WAR if he gets there.
3. **The odds** are the expected share of the ceiling he realizes. It isn't
   a probability: busting and topping out partway are folded into one
   number.
   - The biggest factors aren't personality or health. They're role (SP
     ×0.62, because most drafted starters don't stay starters), readiness
     and age.
   - Makeup and durability are factors too, tapered as before.
4. **Demand** runs last.

**Staying at the peak isn't measured yet.** Outcome A is one snapshot
(December 2042), so the fit rewards being good at that moment, not for how
long. The fragile factor says fragile prospects are worth less at the
snapshot, not that their peaks are shorter. Peak length and longevity need
several snapshots per player: step 6.

## Risk: pitcher scores drifting from batter scores

The odds factors differ by side (SP ×0.57, RP ×0.88, hitters ×1 in the
first fit), and readiness and age may not mean the same thing for a
pitcher as for a hitter. So the fit can move pitchers as a whole up or
down against hitters, apart from any change in who's best within a side.
**You want about a 50/50 split of hitters and pitchers in every ranking
bucket** (2026-11-09).

The feasibility fits already move the mix, and in opposite directions
depending on the outcome. Pitcher share by rank within each class,
classes 2033–41:

| | 1–25 | 26–50 | 51–100 | 101–200 | 201–400 |
|---|---|---|---|---|---|
| Board today | 38% | 55% | 52% | 58% | 58% |
| Fitted odds, A (value now) | 60% | 58% | 59% | 56% | 56% |
| Fitted odds, B (MLB WAR to 26) | 22% | 39% | 39% | 50% | 59% |

So the balance can't be left to the fit:
- **It's a ship check.** The eval reports the pitcher share per bucket
  (1–25, 26–50, 51–100, 101–200, 201–400) for the board today and the new
  one. A bucket outside roughly 40–60% blocks shipping until it's balanced
  or you accept it.
- **The lever is one side-balance factor on pitchers.** It's set so the
  buckets average 50/50 across the past classes, and it's the same kind of
  judgment as the hitter/pitcher balance on current ratings (anchored on
  Andy Spinner). If one constant can't level the top and the bottom
  together, i.e. the fit changes the *shape* by bucket and not just the
  level, the factor gets a ramp by potential WAR, like the makeup taper.
- **Within a side, the fit decides.** The balance factor only moves
  pitchers against hitters. SP vs RP, age and readiness stay as fitted.

## Caveats

- Five mature classes, about 6,000 draftees, of whom about 2,000 have the
  potential to matter. Factors for small groups (RP, 22+) have wide ranges.
- Classes before 2039 are older exports, with current velocity standing in
  for potential velocity.
- Outcome A measures 22+ draftees at 27–32, possibly past peak. Outcome B
  gives them fewer seasons. Both lean against older draftees a little, the
  opposite of the raw result.
- The fitted factors are only as good as the current-ratings model under
  them. Refit whenever that model changes (see "On hold").
