"""How OOTP builds Contact: fit Contact ~ BABIP + Avoid K (+ Power) on a raw
StatsPlus ratings export. Usage: python fit_contact.py <ratings.csv>

Ratings are 20-80 and rounded to 5, so even an exact formula leaves residual
noise around +-2.5; a term "matters" if it lifts R^2 or cuts RMSE clearly.
Pitchers are excluded (their batting ratings are mostly floor values)."""
import csv
import sys

import numpy as np


def col(header, *names):
    low = {h.lower(): h for h in header}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def fit(rows, y, xs, label):
    data = []
    for r in rows:
        try:
            data.append([float(r[y])] + [float(r[x]) for x in xs])
        except (TypeError, ValueError, KeyError):
            continue
    a = np.array(data)
    if len(a) < 50:
        print(f"  {label}: too few rows ({len(a)})")
        return
    yv, xv = a[:, 0], a[:, 1:]
    # drop floor rows (every input at 20) - they say nothing about the weights
    keep = ~(xv <= 20).all(axis=1)
    yv, xv = yv[keep], xv[keep]
    for name, design in (
        ("linear", np.column_stack([xv, np.ones(len(xv))])),
        ("+ squares", np.column_stack([xv, xv ** 2, np.ones(len(xv))])),
    ):
        coef, *_ = np.linalg.lstsq(design, yv, rcond=None)
        pred = design @ coef
        rmse = float(np.sqrt(np.mean((yv - pred) ** 2)))
        r2 = 1 - float(np.sum((yv - pred) ** 2) / np.sum((yv - yv.mean()) ** 2))
        terms = ", ".join(f"{x} {c:+.3f}" for x, c in zip(xs, coef[: len(xs)]))
        extra = f"  [{terms}, const {coef[-1]:+.1f}]" if name == "linear" else ""
        print(f"  {label:<34} {name:<10} n={len(yv):5d} R2={r2:.3f} RMSE={rmse:.2f}{extra}")


def main(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    print(f"{len(rows)} rows; BABIP-ish columns: {[h for h in header if 'bab' in h.lower()]}")
    pos = col(header, "Pos", "POS")
    if pos:
        rows = [r for r in rows if r.get(pos) not in ("1", "P", "SP", "RP", "CL")]
    for label, c, b, k, p in [
        ("current", ("Cntct",), ("BABIP", "Babip"), ("Ks",), ("Pow",)),
        ("potential", ("PotCntct",), ("PotBABIP", "PotBabip"), ("PotKs",), ("PotPow",)),
        ("vs L", ("Cntct_L",), ("BABIP_L", "Babip_L"), ("Ks_L",), ("Pow_L",)),
        ("vs R", ("Cntct_R",), ("BABIP_R", "Babip_R"), ("Ks_R",), ("Pow_R",)),
    ]:
        cc, bc, kc, pc = col(header, *c), col(header, *b), col(header, *k), col(header, *p)
        if not (cc and bc and kc):
            print(f"{label}: missing columns (contact={cc}, babip={bc}, ks={kc})")
            continue
        print(f"{label}: {cc} ~ {bc} + {kc} (+ {pc})")
        fit(rows, cc, [bc, kc], "BABIP + Avoid K")
        if pc:
            fit(rows, cc, [bc, kc, pc], "BABIP + Avoid K + Power")
            fit(rows, cc, [kc, pc], "Avoid K + Power (no BABIP)")


if __name__ == "__main__":
    main(sys.argv[1])
