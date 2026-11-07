"""Measure the ranking models against outcomes (see plans/ranking-architecture-plan.md).

    python eval_rankings.py                          # both profiles, legacy engine
    python eval_rankings.py --profile draft
    python eval_rankings.py --against HEAD~1         # side by side with another commit
    python eval_rankings.py --against-engine legacy  # side by side with another engine
    python eval_rankings.py --data-dir fly_data      # data pulled from the deployed app
    python eval_rankings.py --engine v2 --against-engine legacy --parity
    python eval_rankings.py --engine v2 --against-engine legacy --explain "Curtis McDonald"
    python eval_rankings.py --signals                # which parts read each rating

current: the overall (current-ratings) ranking of a league snapshot's MLB / AAA
  players against in-game OVR - no performance stats are pulled yet. Residuals
  are grouped by rating bucket to show which kinds of player it misjudges.
draft: every past draft class re-scored, against how its players turned out in
  the snapshot: OVR once they're 25+, POT now before that, and 20 (a bust) for
  anyone no longer in it. The baseline is ordering the class by draft-day POT.
  Model order is pre-demand - demand is about signability, not talent.

An engine is a way of producing scores: `legacy` is today's rankers. A new
ranking architecture registers next to it in ENGINES, so both can be scored from
one checkout and compared. `--against REF` instead scores REF's code and
training grids in a temporary git worktree, always against this checkout's data.
"""
import argparse
import contextlib
import csv
import io
import json
import re
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WATCHLIST = ROOT / "eval_watchlist.csv"

# A draftee has "arrived" - judged on OVR, not POT - from this age; by 25 ~80%
# of players sit within 5 of their POT.
ARRIVAL_AGE = 25
# Outcome for a draftee who's no longer in the league.
BUST = 20
# Smallest draft-POT bucket the within-POT correlation uses.
MIN_BUCKET = 15
TOP_K = 100

RATING_BUCKETS = ["<=40", "45", "50", "55-60", "65+"]
VELO_BUCKETS = ["<=90", "91-93", "94-96", "97+"]
GROUPS = {
    "SP": (lambda r: r["POS"] == "SP", ["STU", "MOV", "CONT", "velo"]),
    "RP": (lambda r: r["POS"] in ("RP", "CL"), ["STU", "MOV", "CONT", "velo"]),
    "Hitters": (lambda r: r["POS"] not in ("SP", "RP", "CL"), ["CON", "POW", "EYE", "K's"]),
}


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ data
def read_snapshot(path):
    with open(path, newline="") as f:
        return {r["ID"]: r for r in csv.DictReader(f)}


def read_classes(datasets_dirs, league, only=None):
    """Every `<league>-*-draft.csv` across `datasets_dirs`; a class in a later
    dir replaces the same-named one from an earlier dir."""
    paths = {}
    for d in datasets_dirs:
        for path in Path(d).glob(f"{league}-*-draft.csv"):
            paths[path.stem] = path
    classes = {}
    for path in (paths[name] for name in sorted(paths)):
        if only and path.stem not in only:
            continue
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if "CONT" not in (reader.fieldnames or []):
                sys.exit(f"{path}: no CONT column - process the class once to normalise it")
            rows = list(reader)
        # Classes before 2039 are from older game versions whose exports carry
        # only `VELO` (current velo); `GamePlayer` reads `VT` (potential velo),
        # so stand in the current one to score them at all.
        if "VT" not in (reader.fieldnames or []):
            for r in rows:
                r["VT"] = r.get("VELO")
        classes[path.stem] = rows
    return classes


def current_pool(snapshot, levels):
    return [
        r for r in snapshot.values()
        if r.get("is_amateur") != "1" and r.get("Lev") in levels and _int(r.get("OVR")) is not None
    ]


def read_watchlist():
    if not WATCHLIST.exists():
        return []
    with open(WATCHLIST, newline="") as f:
        return list(csv.DictReader(f))


def scored_rows(pool, snapshot):
    """The pool plus any `current` watchlist player outside it (say, now a free
    agent), so he's still scored. The metrics use the pool alone."""
    ids = {r["ID"] for r in pool}
    extra = [
        snapshot[e["id"]] for e in read_watchlist()
        if e["profile"] == "current" and e["id"] in snapshot and e["id"] not in ids
        and _int(snapshot[e["id"]].get("OVR")) is not None
    ]
    return pool + extra


# ------------------------------------------------------------------ engines
# The ranking methods each profile runs.
METHODS = {"current": "overall", "draft": "draft_class"}


def _current_players(pool):
    from league_snapshot import coerce_gf
    from models.game_players import GamePlayer

    return [GamePlayer({**r, "G/F": coerce_gf(r.get("G/F"))}) for r in pool]


def _class_players(rows):
    from models.game_players import GamePlayer

    return [GamePlayer(r) for r in rows]


def _run(rank, profiles, pool, classes):
    """`rank(method, players)` over the current pool and every class:
    {"current": results, "draft": {class: results}}."""
    out = {}
    if "current" in profiles:
        out["current"] = rank(METHODS["current"], _current_players(pool))
    if "draft" in profiles:
        out["draft"] = {
            name: rank(METHODS["draft"], _class_players(rows)) for name, rows in classes.items()
        }
    return out


def _legacy_rank(method, players):
    from rankers.get_ranker import get_ranker_for_method

    return get_ranker_for_method(method).rank(players, batch_size=max(len(players), 1))


def _v2_rank(method, players):
    from ranking import get_ranker

    return get_ranker(method).rank(players, batch_size=max(len(players), 1))


ENGINES = {"legacy": _legacy_rank, "v2": _v2_rank}


def results(engine, profiles, pool, classes):
    with contextlib.redirect_stdout(io.StringIO()):  # rankers print progress
        return _run(ENGINES[engine], profiles, pool, classes)


def pre_demand(result):
    """The score before the demand step: v2 has it as a field, legacy as the
    raw score."""
    return getattr(result, "pre_demand_score", result.raw_overall_score)


def scores_of(ranked):
    """The score each profile is judged on: current the final score, draft the
    pre-demand one (demand is about signability, not talent)."""
    out = {}
    if "current" in ranked:
        out["current"] = {r.id: r.overall_score for r in ranked["current"]}
    if "draft" in ranked:
        out["draft"] = {
            name: {r.id: pre_demand(r) for r in rs} for name, rs in ranked["draft"].items()
        }
    return out


def score_at_ref(ref, args):
    """Scores from `ref`'s code + training grids, run in a temporary worktree
    (the attribute models read `./training_data` relative to the cwd)."""
    tmp = Path(tempfile.mkdtemp(prefix="eval-rankings-"))
    wt, out = tmp / "wt", tmp / "scores.json"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(wt), ref],
        cwd=ROOT, check=True, capture_output=True,
    )
    try:
        cmd = [
            sys.executable, str(Path(__file__).resolve()),
            "--scores-only", str(out), "--code-root", str(wt),
            "--engine", "legacy", "--profile", args.profile, "--league", args.league,
            "--snapshot", str(Path(args.snapshot).resolve()),
            "--datasets-dir", ",".join(str(Path(d).resolve()) for d in args.datasets_dirs),
            "--levels", args.levels,
        ]
        if args.classes:
            cmd += ["--classes", args.classes]
        subprocess.run(cmd, cwd=wt, check=True)
        return json.loads(out.read_text())
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt)],
            cwd=ROOT, check=True, capture_output=True,
        )


# ------------------------------------------------------------------ metrics
def spearman(xs, ys):
    from scipy.stats import spearmanr

    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return float(spearmanr(xs, ys).statistic)


def rating_bucket(value):
    v = _int(value)
    if v is None:
        return None
    if v <= 40:
        return "<=40"
    if v <= 50:
        return str(v // 5 * 5)
    return "55-60" if v <= 60 else "65+"


def velo_bucket(velocity):
    m = re.search(r"\d+", velocity or "")
    if not m:
        return None
    low = int(m[0])
    return "<=90" if low <= 90 else "91-93" if low <= 93 else "94-96" if low <= 96 else "97+"


def current_metrics(scores, pool):
    """Per group: spearman(score, OVR) and the mean residual of a linear
    score ~ OVR fit, bucketed by each rating."""
    out = {}
    for group, (member, attrs) in GROUPS.items():
        rows = [r for r in pool if member(r) and r["ID"] in scores]
        if len(rows) < 3:
            continue
        sc = [scores[r["ID"]] for r in rows]
        ov = [int(r["OVR"]) for r in rows]
        mo, ms = st.mean(ov), st.mean(sc)
        var = sum((o - mo) ** 2 for o in ov) or 1
        b = sum((o - mo) * (s - ms) for o, s in zip(ov, sc)) / var
        a = ms - b * mo
        buckets = {}
        for r, s, o in zip(rows, sc, ov):
            for attr in attrs:
                key = velo_bucket(r.get("VT")) if attr == "velo" else rating_bucket(r.get(attr))
                if key:
                    buckets.setdefault(attr, {}).setdefault(key, []).append(s - (a + b * o))
        out[group] = {
            "n": len(rows),
            "rho": spearman(sc, ov),
            "resid": {
                attr: {k: (len(v), st.mean(v)) for k, v in by.items()}
                for attr, by in buckets.items()
            },
        }
    return out


def draft_outcome(snap_row):
    """How a draftee turned out: OVR once he's arrived, POT now before that, and
    BUST once he's gone from the league. None when the row has no ratings."""
    if snap_row is None:
        return BUST
    age, ovr, pot = (_int(snap_row.get(k)) for k in ("Age", "OVR", "POT"))
    if age is not None and age >= ARRIVAL_AGE:
        return ovr
    return pot


def top_k_mean(keys, outcomes, k):
    """Mean outcome of the top `k` by `keys`, with players tied at the cut-off
    counted fractionally (draft POT ties a lot)."""
    order = sorted(range(len(keys)), key=lambda i: -keys[i])
    total, taken, i = 0.0, 0, 0
    while i < len(order) and taken < k:
        j = i
        while j < len(order) and keys[order[j]] == keys[order[i]]:
            j += 1
        tied = [outcomes[order[t]] for t in range(i, j)]
        take = min(len(tied), k - taken)
        total += st.mean(tied) * take
        taken += take
        i = j
    return total / taken if taken else None


def within_bucket_rho(keys, outcomes, buckets):
    """Spearman(keys, outcomes) inside each bucket, weighted by bucket size."""
    by = {}
    for k, o, b in zip(keys, outcomes, buckets):
        by.setdefault(b, []).append((k, o))
    num = den = 0
    for pairs in by.values():
        if len(pairs) < MIN_BUCKET:
            continue
        rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
        if rho is not None:
            num += rho * len(pairs)
            den += len(pairs)
    return num / den if den else None


def draft_metrics(scores, rows, snapshot):
    ids, model, pot, outcome, arrived, busts = [], [], [], [], 0, 0
    for r in rows:
        draft_pot = _int(r.get("POT"))
        if r["ID"] not in scores or draft_pot is None:
            continue
        snap = snapshot.get(r["ID"])
        o = draft_outcome(snap)
        if o is None:
            continue
        busts += snap is None
        arrived += snap is not None and (_int(snap.get("Age")) or 0) >= ARRIVAL_AGE
        ids.append(r["ID"])
        model.append(scores[r["ID"]])
        pot.append(draft_pot)
        outcome.append(o)
    n = len(ids)
    return {
        "n": n,
        "arrived": arrived / n if n else None,
        "busts": busts / n if n else None,
        "rho_model": spearman(model, outcome),
        "rho_pot": spearman(pot, outcome),
        "rho_within_pot": within_bucket_rho(model, outcome, pot),
        "top_model": top_k_mean(model, outcome, TOP_K),
        "top_pot": top_k_mean(pot, outcome, TOP_K),
    }


def rank_of(scores):
    return {pid: i + 1 for i, pid in enumerate(sorted(scores, key=lambda p: -scores[p]))}


# ------------------------------------------------------------------ report
def fmt(value, spec):
    return "-" if value is None else format(value, spec)


def pair(head, base, spec):
    """`head`, or `base → head` when there's a base to compare against."""
    if base is _NO_BASE:
        return fmt(head, spec)
    return f"{fmt(base, spec)} → {fmt(head, spec)}"


_NO_BASE = object()


def print_current(head, base, pool, snapshot):
    hm = current_metrics(head, pool)
    bm = current_metrics(base, pool) if base is not None else None
    print("\n== current: model score vs in-game OVR")
    for group, m in hm.items():
        b = bm[group] if bm else None
        print(f"\n{group} (n={m['n']})  spearman {pair(m['rho'], b['rho'] if b else _NO_BASE, '.3f')}")
        print("  mean residual by rating (+ = model above what OVR predicts)")
        for attr, by in m["resid"].items():
            labels = VELO_BUCKETS if attr == "velo" else RATING_BUCKETS
            cells = []
            for label in labels:
                if label not in by:
                    continue
                n, r = by[label]
                old = b["resid"].get(attr, {}).get(label, (0, None))[1] if b else _NO_BASE
                cells.append(f"{label}: {pair(r, old, '+.1f')} ({n})")
            print(f"    {attr:<5} " + "   ".join(cells))
    if base is not None:
        print_movement("current", head, base, snapshot)


def print_movement(label, head, base, snapshot, top=300):
    common = [p for p in head if p in base]
    changed = [p for p in common if abs(head[p] - base[p]) > 1e-6]
    print(f"\n  movement ({label}): {len(changed)} of {len(common)} scores changed")
    if not changed:
        return
    pct = sorted(
        (head[p] - base[p]) / base[p] * 100 for p in changed if base[p]
    )
    if pct:
        print(
            f"    score change: median {st.median(pct):+.1f}%  "
            f"p10 {pct[len(pct) // 10]:+.1f}%  p90 {pct[len(pct) * 9 // 10]:+.1f}%"
        )
    hr, br = rank_of(head), rank_of(base)
    top_ids = [p for p in common if br[p] <= top]
    moves = [abs(hr[p] - br[p]) for p in top_ids]
    if moves:
        print(f"    base top {top}: median rank move {st.median(moves):.0f}, max {max(moves)}")
    by_move = sorted(common, key=lambda p: hr[p] - br[p])
    for p in by_move[:5] + by_move[-5:]:
        if hr[p] != br[p]:
            name = (snapshot.get(p) or {}).get("Name", p)
            print(f"    {name:<24} rank {br[p]:>5} → {hr[p]:<5} score {base[p]:6.1f} → {head[p]:6.1f}")


def print_draft(head, base, classes, snapshot):
    print(
        f"\n== draft: outcome = OVR at {ARRIVAL_AGE}+, POT now before, {BUST} if gone;"
        f" model order is pre-demand"
    )
    print(
        "class        n  arrived busts | whole class: model    POT-only"
        f" | within POT: model | top {TOP_K} mean outcome: model  POT-only"
    )
    for name, rows in classes.items():
        m = draft_metrics(head[name], rows, snapshot)
        b = draft_metrics(base[name], rows, snapshot) if base is not None else None

        def col(key, spec):
            return pair(m[key], b[key] if b else _NO_BASE, spec)

        year = re.search(r"\d{4}", name)
        print(
            f"{year[0] if year else name:<8} {m['n']:>5}  {fmt(m['arrived'], '4.0%'):>6}"
            f" {fmt(m['busts'], '4.0%'):>5} |  {col('rho_model', '.2f'):>13}  {fmt(m['rho_pot'], '.2f'):>8}"
            f" |  {col('rho_within_pot', '.2f'):>13}  |  {col('top_model', '.1f'):>16}  {fmt(m['top_pot'], '.1f'):>8}"
        )
    if base is not None:
        moved = [
            name for name in classes
            if any(abs(head[name][p] - base[name].get(p, head[name][p])) > 1e-6 for p in head[name])
        ]
        if not moved:
            print("\n  movement (draft): no scores changed")
        for name in moved:
            print_movement(name, head[name], base[name], snapshot, top=TOP_K)


def print_watchlist(head, base, pool, classes, snapshot):
    entries = read_watchlist()
    if not entries:
        return
    print("\n== watchlist")
    for e in entries:
        pid, profile = e["id"], e["profile"]
        note = f"  ({e['note']})" if e.get("note") else ""
        if profile == "current" and "current" in head:
            row = snapshot.get(pid)
            if row is None or pid not in head["current"]:
                print(f"  {e['name']}: not in the snapshot")
                continue
            group = next(g for g, (member, _) in GROUPS.items() if member(row))
            member = GROUPS[group][0]

            def standing(scores):
                peers = sorted(
                    scores[r["ID"]] for r in pool
                    if member(r) and r["OVR"] == row["OVR"] and r["ID"] in scores
                )
                s = scores[pid]
                return s, sum(x < s for x in peers) / len(peers), st.median(peers)

            s, pct, med = standing(head["current"])
            line = (
                f"  {e['name']} ({group}, {row.get('Lev') or '-'}, OVR {row['OVR']}): score {s:.1f},"
                f" {pct:.0%} of same-OVR {group} (median {med:.1f})"
            )
            if base is not None:
                bs, bpct, _ = standing(base["current"])
                line += f"  [was {bs:.1f}, {bpct:.0%}]"
            print(line + note)
        elif profile == "draft" and "draft" in head and e.get("class") in classes:
            cls = e["class"]
            rows = {r["ID"]: r for r in classes[cls]}
            if pid not in rows or pid not in head["draft"][cls]:
                print(f"  {e['name']}: not in {cls}")
                continue
            pots = [_int(r.get("POT")) or 0 for r in classes[cls]]
            draft_pot = _int(rows[pid].get("POT")) or 0
            pot_rank = 1 + sum(p > draft_pot for p in pots)
            snap = snapshot.get(pid)
            now = f"{snap['OVR']}/{snap['POT']} at {snap['Age']}" if snap else "gone"
            line = (
                f"  {e['name']} ({cls}): model #{rank_of(head['draft'][cls])[pid]},"
                f" draft POT {draft_pot} (#{pot_rank} by POT), now {now}"
            )
            if base is not None:
                line += f"  [was #{rank_of(base['draft'][cls])[pid]}]"
            print(line + note)


# ------------------------------------------------------------------ parity
PARITY_EXAMPLES = 3


def _diffs(name, a, b):
    """(field path, a, b) for each place `a` and `b` differ, into nested dicts."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            yield from _diffs(f"{name}.{key}", a.get(key, _MISSING), b.get(key, _MISSING))
    elif a != b:
        yield name, a, b


_MISSING = "(missing)"


def _value(v):
    return format(v, ".10g") if isinstance(v, float) else str(v)


def pool_parity(head, base):
    """Every ScoredPlayer field (breakdowns leaf by leaf) and the order, base
    vs head. {"n", "only_base", "only_head", "rows", "fields", "order_from",
    "ranks_moved"}; `fields` is field -> (count, examples)."""
    from ranking.results import SCORED_PLAYER_FIELDS

    hb, bb = {r.id: r for r in head}, {r.id: r for r in base}
    common = [r.id for r in base if r.id in hb]
    fields, rows = {}, 0
    for pid in common:
        h, b = hb[pid], bb[pid]
        differs = False
        for name in SCORED_PLAYER_FIELDS:
            for path, hv, bv in _diffs(name, getattr(h, name), getattr(b, name)):
                differs = True
                count, examples = fields.get(path, (0, []))
                if len(examples) < PARITY_EXAMPLES:
                    examples.append(f"{b.name}: {_value(bv)} → {_value(hv)}")
                fields[path] = (count + 1, examples)
        rows += differs
    head_order = [r.id for r in head if r.id in bb]
    base_order = common
    order_from = next((i + 1 for i, (x, y) in enumerate(zip(head_order, base_order)) if x != y), None)
    hr = {pid: i for i, pid in enumerate(head_order)}
    return {
        "n": len(common),
        "only_base": len(bb) - len(common),
        "only_head": len(hb) - len(common),
        "rows": rows,
        "fields": fields,
        "order_from": order_from,
        "ranks_moved": sum(hr[pid] != i for i, pid in enumerate(base_order)),
    }


def print_parity(head, base, base_label, head_label):
    print(f"\n== parity: {base_label} → {head_label}, every field (breakdowns leaf by leaf) and the order")
    pools = []
    if "current" in head:
        pools.append((f"current ({METHODS['current']})", head["current"], base["current"]))
    for name in head.get("draft", {}):
        pools.append((name, head["draft"][name], base["draft"][name]))
    same = 0
    for label, h, b in pools:
        m = pool_parity(h, b)
        clean = not (m["rows"] or m["only_base"] or m["only_head"] or m["order_from"])
        same += clean
        line = f"  {label:<20} {m['n']:>6} players  "
        if clean:
            print(line + "identical")
            continue
        notes = [f"{m['rows']} rows differ"]
        if m["order_from"]:
            notes.append(f"order differs from #{m['order_from']} ({m['ranks_moved']} ranks changed)")
        if m["only_base"] or m["only_head"]:
            notes.append(f"only in {base_label}: {m['only_base']}, only in {head_label}: {m['only_head']}")
        print(line + ", ".join(notes))
        for name, (count, examples) in sorted(m["fields"].items(), key=lambda kv: -kv[1][0]):
            print(f"      {name:<44} {count:>6}" + (f"   e.g. {'; '.join(examples)}" if examples else ""))
    print(f"\n  {same} of {len(pools)} pools identical")


# ------------------------------------------------------------------ explain
def _find(ranked, targets):
    """(pool label, method, rows' index, result) for each target - an ID or a
    name, case-insensitive - in every pool it's in."""
    wanted = {t.strip().lower() for t in targets}
    pools = []
    if "current" in ranked:
        pools.append(("current", METHODS["current"], ranked["current"]))
    for name, rs in ranked.get("draft", {}).items():
        pools.append((name, METHODS["draft"], rs))
    for label, method, rs in pools:
        for r in rs:
            if r.id.lower() in wanted or (r.name or "").lower() in wanted:
                yield label, method, r


def _ledger_view(engine, ranked, label, pool_rows, method, pid):
    """(ledger, result) for `pid` under `engine`. An engine without ledgers
    (legacy) gets one from the v2 legacy pipeline, which reproduces it."""
    result = _in_pool(ranked, label, pid)
    if result is None:
        return None, None
    if getattr(result, "ledger", None) is not None:
        return result.ledger, result
    from ranking import get_ranker

    players = _current_players(pool_rows) if label == "current" else _class_players(pool_rows)
    with contextlib.redirect_stdout(io.StringIO()):
        replay = get_ranker(method, pipeline="legacy").rank(players, batch_size=max(len(players), 1))
    mine = next(r for r in replay if r.id == pid)
    if abs(mine.overall_score - result.overall_score) > 1e-6:
        print(f"  (the legacy-pipeline ledger gives {mine.overall_score:.2f}, not {engine}'s {result.overall_score:.2f})")
    return mine.ledger, result


def _in_pool(ranked, label, pid):
    rs = ranked["current"] if label == "current" else ranked["draft"][label]
    return next((r for r in rs if r.id == pid), None)


def _ranks(ranked, label, pid):
    """(pre-demand rank, final rank) in the pool."""
    rs = ranked["current"] if label == "current" else ranked["draft"][label]
    final = next(i + 1 for i, r in enumerate(rs) if r.id == pid)
    pre = sorted(rs, key=lambda r: -pre_demand(r))
    return next(i + 1 for i, r in enumerate(pre) if r.id == pid), final


def _lines(ledger):
    """{(stage, label, side): (delta, counted)} in ledger order."""
    out = {}
    for line in ledger.lines:
        key = (line.stage, line.label, line.side)
        delta, counted = out.get(key, (0.0, ledger.counted(line)))
        out[key] = (delta + line.delta, counted)
    return out


def print_explain(targets, head, head_label, base, base_label, pool, classes):
    engines = [(head_label, head)] + ([(base_label, base)] if base is not None else [])
    engines.reverse()  # base first, as in the other reports
    found = list(_find(head, targets))
    if not found:
        print(f"\n== explain: no player matching {', '.join(targets)}")
        return
    for label, method, r in found:
        rows = pool if label == "current" else classes[label]
        print(f"\n== explain: {r.name} (ID {r.id}, {r.position}, age {r.age}), {label} ({method})")
        views = []
        for engine_label, ranked in engines:
            ledger, result = _ledger_view(engine_label, ranked, label, rows, method, r.id)
            views.append((engine_label, ledger, result, ranked))
        keys = []
        for _, ledger, _, _ in views:
            for key in _lines(ledger) if ledger else ():
                if key not in keys:
                    keys.append(key)
        per_view = [_lines(ledger) if ledger else {} for _, ledger, _, _ in views]
        two = len(views) == 2
        width = max([36] + [len(_line_label(k)) for k in keys])
        print(f"  {'stage':<10} {'line':<{width}}" + "".join(f"{v[0]:>12}" for v in views) + (f"{'change':>10}" if two else ""))

        def row(key):
            cells, values = [], []
            for lines in per_view:
                delta, counted = lines.get(key, (None, True))
                values.append(delta)
                cells.append("-" if delta is None else f"{delta:+.2f}" if counted else f"({delta:+.2f})")
            out = f"  {key[0]:<10} {_line_label(key):<{width}}" + "".join(f"{c:>12}" for c in cells)
            if two and None not in values and abs(values[1] - values[0]) > 0.005:
                out += f"{values[1] - values[0]:>+10.2f}"
            print(out)

        def counted_anywhere(key):
            return any(lines.get(key, (0, False))[1] for lines in per_view)

        for key in filter(counted_anywhere, keys):
            row(key)

        def total(name, values):
            print(f"  {'':<10} {name:<{width}}" + "".join(f"{v:>12}" for v in values))

        total("score", [f"{v[2].overall_score:.2f}" for v in views])
        if label != "current":
            total("pre-demand score", [f"{pre_demand(v[2]):.2f}" for v in views])
        ranks = [_ranks(v[3], label, r.id) for v in views]
        if label == "current":
            total("rank", [str(final) for _, final in ranks])
        else:
            total("rank (pre-demand → final)", [f"{pre} → {final}" for pre, final in ranks])
        other = [key for key in keys if not counted_anywhere(key)]
        if other:
            print("  the side not judged on (not counted):")
            for key in other:
                row(key)


def _line_label(key):
    stage, label, side = key
    return f"{label} [{side}]" if side else label


# ------------------------------------------------------------------ signals
def print_signals(profiles, pool, classes):
    from ranking import get_ranker
    from ranking.signals import inventory

    runs = []
    if "current" in profiles:
        runs.append(("current pool", METHODS["current"], _current_players(pool)))
        runs.append(("current pool", "potential", _current_players(pool)))
    if "draft" in profiles:
        rows = [r for rs in classes.values() for r in rs]
        runs.append((f"{len(classes)} classes", METHODS["draft"], _class_players(rows)))
    for where, method, players in runs:
        inv = inventory(get_ranker(method), players)
        print(f"\n== signals: {method}, observed on {inv.players:,} players ({where})")
        for side in ("batting", "pitching"):
            by, flags = inv.by_rating(side), inv.flags(side)
            print(f"  {side} side - {len(flags)} of {len(by)} ratings flagged")
            ordered = sorted(by, key=lambda rating: (rating not in flags, -len(by[rating]), rating))
            for rating in ordered:
                mark = "!" if rating in flags else " "
                note = f"   [{'; '.join(flags[rating])}]" if rating in flags else ""
                print(f"   {mark} {rating:<17} {', '.join(by[rating])}{note}")


# ------------------------------------------------------------------ main
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", choices=["current", "draft", "all"], default="all")
    p.add_argument("--engine", choices=sorted(ENGINES), default="legacy")
    p.add_argument("--against", metavar="REF", help="compare with this git ref's code")
    p.add_argument("--against-engine", choices=sorted(ENGINES), help="compare with this engine")
    p.add_argument("--league", default="yfmlb")
    p.add_argument(
        "--data-dir",
        help="a copy of a deployed DATA_DIR (e.g. fly_data/): its snapshot, and its"
        " class datasets on top of the local ones",
    )
    p.add_argument("--snapshot", help="snapshot players CSV (default league_snapshots/<league>/players.csv)")
    p.add_argument("--datasets-dir", help="comma-separated dataset dirs, later ones win (default datasets/)")
    p.add_argument("--classes", help="comma-separated class names, e.g. yfmlb-2034-draft")
    p.add_argument("--levels", default="MLB,AAA", help="levels in the current pool")
    p.add_argument("--parity", action="store_true", help="with --against-engine: diff every field")
    p.add_argument("--explain", metavar="ID", help="comma-separated player IDs or names: show their ledgers")
    p.add_argument("--signals", action="store_true", help="which parts of each profile read each rating")
    p.add_argument("--scores-only", metavar="PATH", help=argparse.SUPPRESS)
    p.add_argument("--code-root", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.against and args.against_engine:
        p.error("--against and --against-engine are exclusive")
    if args.parity and not args.against_engine:
        p.error("--parity compares two engines: give --against-engine")
    if args.explain and args.against:
        p.error("--explain compares engines in this checkout: use --against-engine")
    data_root = Path(args.data_dir) if args.data_dir else ROOT
    args.snapshot = args.snapshot or str(data_root / "league_snapshots" / args.league / "players.csv")
    if args.datasets_dir:
        args.datasets_dirs = args.datasets_dir.split(",")
    else:
        args.datasets_dirs = [str(ROOT / "datasets")]
        if args.data_dir:
            args.datasets_dirs.append(str(data_root / "datasets"))

    # `--against` runs this script again inside a worktree of the other ref;
    # its code must win over this checkout's.
    sys.path.insert(0, args.code_root or str(ROOT))

    profiles = ["current", "draft"] if args.profile == "all" else [args.profile]
    snapshot = read_snapshot(args.snapshot)
    pool = current_pool(snapshot, set(args.levels.split(",")))
    only = set(args.classes.split(",")) if args.classes else None
    classes = read_classes(args.datasets_dirs, args.league, only) if "draft" in profiles else {}
    rows = scored_rows(pool, snapshot)

    if args.signals:
        print_signals(profiles, rows, classes)
        if not (args.parity or args.explain):
            return

    head_results = results(args.engine, profiles, rows, classes)
    head = scores_of(head_results)
    if args.scores_only:
        Path(args.scores_only).write_text(json.dumps(head))
        return
    base_results = base = None
    if args.against:
        base = score_at_ref(args.against, args)
        print(f"comparing {args.against} → working tree ({args.engine})")
    elif args.against_engine:
        base_results = results(args.against_engine, profiles, rows, classes)
        base = scores_of(base_results)
        print(f"comparing engine {args.against_engine} → {args.engine}")

    if args.parity or args.explain:
        if args.parity:
            print_parity(head_results, base_results, args.against_engine, args.engine)
        if args.explain:
            print_explain(
                args.explain.split(","), head_results, args.engine,
                base_results, args.against_engine, rows, classes,
            )
        return
    if "current" in head:
        print_current(head["current"], base and base["current"], pool, snapshot)
    if "draft" in head:
        print_draft(head["draft"], base and base["draft"], classes, snapshot)
    print_watchlist(head, base, pool, classes, snapshot)


if __name__ == "__main__":
    main()
