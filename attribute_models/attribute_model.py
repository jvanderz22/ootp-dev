from abc import ABC, abstractproperty
from sklearn.model_selection import train_test_split
from models.game_players import PLAYER_FIELDS
import xgboost as xgb
import csv


class AttributeModel(ABC):
    def __init__(self):
        self._model = None

    right_hand_only = False

    @abstractproperty
    def model_type(self):
        pass

    @abstractproperty
    def file_path(self):
        pass

    @abstractproperty
    def fields(self):
        pass

    @abstractproperty
    def fields_mapping(self):
        pass

    def run(self, player):
        if self.right_hand_only and player.throw_hand != "Right":
            return 0

        try:
            player_attrs = [
                getattr(player, self.fields_mapping[field]) for field in self.fields
            ]
        except Exception as e:
            print(e)
            import pdb

            pdb.set_trace()

        model_prediction = self.model.predict(xgb.DMatrix([player_attrs], []))[0]
        return model_prediction if model_prediction > 0 else 0

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

        matrix = xgb.DMatrix(independent_variables, y)
        params = {"objective": "reg:squarederror", "tree_method": "hist"}
        X_train, X_test, y_train, y_test = train_test_split(
            independent_variables, y, random_state=1
        )
        # Create regression matrices
        dtrain_reg = xgb.DMatrix(X_train, y_train, enable_categorical=True)
        dtest_reg = xgb.DMatrix(X_test, y_test, enable_categorical=True)

        evals = [(dtrain_reg, "train"), (dtest_reg, "validation")]
        n = 100
        return xgb.train(
            params=params,
            dtrain=matrix,
            num_boost_round=n,
            evals=evals,
        )
