"""Measure the ranking models against outcomes (see ranking-architecture-plan.md).

    python eval_rankings.py                          # both profiles, legacy engine
    python eval_rankings.py --profile draft
    python eval_rankings.py --against HEAD~1         # side by side with another commit
    python eval_rankings.py --against-engine legacy  # side by side with another engine
    python eval_rankings.py --data-dir fly_data      # data pulled from the deployed app

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
def _legacy_scores(profiles, pool, classes):
    from league_snapshot import coerce_gf
    from models.game_players import GamePlayer

    out = {}
    if "current" in profiles:
        from rankers.overall_ranker import OverallRanker

        players = [GamePlayer({**r, "G/F": coerce_gf(r.get("G/F"))}) for r in pool]
        scored = OverallRanker().rank(players, batch_size=max(len(players), 1))
        out["current"] = {s.id: s.overall_score for s in scored}
    if "draft" in profiles:
        from rankers.draft_class_ranker import DraftClassRanker

        out["draft"] = {}
        for name, rows in classes.items():
            scored = DraftClassRanker().rank(
                [GamePlayer(r) for r in rows], batch_size=max(len(rows), 1)
            )
            out["draft"][name] = {s.id: s.raw_overall_score for s in scored}
    return out


ENGINES = {"legacy": _legacy_scores}


def score(engine, profiles, pool, classes):
    with contextlib.redirect_stdout(io.StringIO()):  # rankers print progress
        return ENGINES[engine](profiles, pool, classes)


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
    p.add_argument("--scores-only", metavar="PATH", help=argparse.SUPPRESS)
    p.add_argument("--code-root", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.against and args.against_engine:
        p.error("--against and --against-engine are exclusive")
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
    head = score(args.engine, profiles, rows, classes)
    if args.scores_only:
        Path(args.scores_only).write_text(json.dumps(head))
        return
    base = None
    if args.against:
        base = score_at_ref(args.against, args)
        print(f"comparing {args.against} → working tree ({args.engine})")
    elif args.against_engine:
        base = score(args.against_engine, profiles, rows, classes)
        print(f"comparing engine {args.against_engine} → {args.engine}")

    if "current" in head:
        print_current(head["current"], base and base["current"], pool, snapshot)
    if "draft" in head:
        print_draft(head["draft"], base and base["draft"], classes, snapshot)
    print_watchlist(head, base, pool, classes, snapshot)


if __name__ == "__main__":
    main()
