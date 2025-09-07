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
        if self.right_hand_only and player.throw_hand != "Right":
            return 0

        player_attrs = [
            getattr(player, self.fields_mapping[field]) for field in self.fields
        ]
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
