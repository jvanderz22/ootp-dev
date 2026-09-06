from abc import ABC, abstractmethod, abstractproperty
from sklearn.model_selection import train_test_split
from models.game_players import PLAYER_FIELDS
import xgboost as xgb
import csv


class AttributeModel(ABC):
    def __init__(self):
        self._model = None

    debug = False
    right_hand_only = False
    separate_test_train = False # prefer to separate test and train in new models

    @property
    @abstractmethod
    def model_type(self):
        pass

    @property
    @abstractmethod
    def file_path(self):
        pass

    @property
    @abstractmethod
    def fields(self):
        pass

    @property
    @abstractmethod
    def fields_mapping(self):
        pass

    @property
    def test_data(self):
        return None

    def run(self, player):
        return self.predict_many([player])[0]

    def predict_many(self, players):
        """Vectorised `run`: build one `DMatrix` for the whole list and predict
        in a single call instead of once per player. Returns a list of plain
        floats aligned with `players` - 0.0 where a `right_hand_only` model
        doesn't apply or the raw prediction is <= 0 (same clamp `run` used).

        A per-player `xgb.DMatrix([row], [])` + `predict` costs tens of
        microseconds of Python/C boundary overhead each; at ~12 models x ~10k
        players per ranking pass that dominated the run. One matrix per model
        per batch collapses ~18k calls into ~12.
        """
        scores = [0.0] * len(players)
        mapping = self.fields_mapping
        fields = self.fields
        rows = []
        row_index = []
        for i, player in enumerate(players):
            if self.right_hand_only and player.throw_hand != "Right":
                continue
            rows.append([getattr(player, mapping[field]) for field in fields])
            row_index.append(i)
        if rows:
            predictions = self.model.predict(xgb.DMatrix(rows))
            for j, i in enumerate(row_index):
                value = float(predictions[j])
                scores[i] = value if value > 0 else 0.0
        return scores

    @property
    def model(self):
        if self._model is None:
            self._model = self.create_model()
        return self._model

    def create_model(self):
        model_properties = self.fields
        independent_variables = []
        y = []
        with open(self.file_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for line in reader:
                independent_line_variables = [
                    int(line[prop]) for prop in model_properties
                ]
                independent_variables.append(independent_line_variables)
                y.append(int(line["Ovr"]))

        params = {
            "objective": "reg:squarederror",
            "tree_method": "exact",
            "verbosity": 0,
            "monotone_constraints": tuple([1 for i in model_properties]),
        }
        if self.test_data is None:
            x_train, x_test, y_train, y_test = train_test_split(
                independent_variables, y, random_state=1
            )
        else:
            x_train = independent_variables
            y_train = y
            y_test = [test_item[0] for test_item in self.test_data]
            x_test = [test_item[1] for test_item in self.test_data]
        all_x = x_train if self.separate_test_train else x_train + x_test
        all_y = y_train if self.separate_test_train else y_train + y_test

        # Create regression matrices
        dtrain_reg = xgb.DMatrix(all_x, all_y)
        dtest_reg = xgb.DMatrix(x_test, y_test)

        evals = [(dtrain_reg, "train"), (dtest_reg, "validation")]
        n = 40
        model = xgb.train(
            params=params,
            dtrain=dtrain_reg,
            num_boost_round=n,
            evals=evals,
            verbose_eval=self.debug,
        )
        if self.debug:
            self.__print_test_results(model)
        return model

    def __print_test_results(self, model):
        pass
