"""One component rate as a function of its rating, fit on every level at once.

logit(rate) = f(rating) + g(term) + ... - f monotone in the rating, and each
extra term (level, role) its own additive part: they never share a tree. The
extra terms soak up competition, run environment and role, so the low-rated
players in the low minors pin down the bottom of f. A fitted rate is kept as a
table over ratings 20-80 with the terms held at given values (MLB, a role).
"""
import numpy as np
import xgboost as xgb

LOW, HIGH = 20, 80
RATINGS = np.arange(LOW, HIGH + 1)
PARAMS = dict(
    objective="reg:logistic", n_estimators=300, max_depth=2, learning_rate=0.05,
    min_child_weight=100, reg_lambda=1.0,
)


class Rate:
    def __init__(self, rows, rating, num, den, sign, terms):
        rows = rows[rows[den] > 0]
        self.terms = list(terms)
        columns = [rating, *self.terms]
        self.model = xgb.XGBRegressor(
            **PARAMS,
            monotone_constraints="(" + ",".join([str(sign)] + ["0"] * len(self.terms)) + ")",
            interaction_constraints=str([[i] for i in range(len(columns))]),
            base_score=float(rows[num].sum() / rows[den].sum()),
        )
        self.model.fit(rows[columns].to_numpy(float), rows[num] / rows[den], sample_weight=rows[den])

    def table(self, **at) -> list:
        """The rate at every rating, with the terms held at `at`."""
        held = [np.full(len(RATINGS), at[t]) for t in self.terms]
        return self.model.predict(np.column_stack([RATINGS, *held]).astype(float)).round(5).tolist()


class Additive:
    """Runs (not a rate) as a sum of one monotone part per rating plus the
    terms: target = base + f_1(r_1) + ... + g(term). Kept as the value at
    `REFERENCE` ratings plus, per rating, its change from the reference."""

    REFERENCE = 50

    def __init__(self, rows, ratings, target, weight, signs, terms):
        self.ratings, self.terms = list(ratings), list(terms)
        columns = self.ratings + self.terms
        self.model = xgb.XGBRegressor(
            **{**PARAMS, "objective": "reg:squarederror"},
            monotone_constraints="(" + ",".join([str(s) for s in signs] + ["0"] * len(self.terms)) + ")",
            interaction_constraints=str([[i] for i in range(len(columns))]),
            base_score=float((rows[target] * rows[weight]).sum() / rows[weight].sum()),
        )
        self.model.fit(rows[columns].to_numpy(float), rows[target], sample_weight=rows[weight])

    def _predict(self, values: dict, at: dict) -> np.ndarray:
        n = len(next(iter(values.values())))
        columns = [values.get(r, np.full(n, self.REFERENCE)) for r in self.ratings]
        columns += [np.full(n, at[t]) for t in self.terms]
        return self.model.predict(np.column_stack(columns).astype(float))

    def tables(self, **at) -> dict:
        """{"base": value at the reference ratings, rating: [change from the
        reference at every rating 20-80]} with the terms held at `at`."""
        base = float(self._predict({r: np.array([self.REFERENCE]) for r in self.ratings}, at)[0])
        out = {"base": round(base, 4)}
        for r in self.ratings:
            out[r] = (self._predict({r: RATINGS}, at) - base).round(4).tolist()
        return out
