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
