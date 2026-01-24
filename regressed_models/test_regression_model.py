from regressed_models.base_regression_model import BlendScenario
from regressed_models.base_regression_model import BaseRegressionModel


def test():
    """Run with pytest"""
    model = BaseRegressionModel()

    def assert_rounded_exponential(overall, potential, blend, expected):
        result = model._exponential_interpolation(overall, potential, blend)
        rounded = round(result / 5) * 5
        assert (
            rounded == expected
        ), f"Expected {expected}, got {rounded} for overall={overall}, potential={potential}, blend={blend}, reult={result}"

    assert_rounded_exponential(20, 35, BlendScenario.LOW, 25)
    assert_rounded_exponential(20, 40, BlendScenario.LOW, 30)
    assert_rounded_exponential(35, 60, BlendScenario.LOW, 45)
    assert_rounded_exponential(30, 40, BlendScenario.LOW, 35)
    assert_rounded_exponential(35, 45, BlendScenario.LOW, 40)
    assert_rounded_exponential(40, 50, BlendScenario.LOW, 45)
    assert_rounded_exponential(40, 55, BlendScenario.LOW, 45)
    assert_rounded_exponential(50, 60, BlendScenario.LOW, 55)
    assert_rounded_exponential(60, 70, BlendScenario.LOW, 65)
    assert_rounded_exponential(20, 70, BlendScenario.LOW, 45)
    assert_rounded_exponential(40, 60, BlendScenario.LOW, 50)
    assert_rounded_exponential(45, 80, BlendScenario.LOW, 65)
    assert_rounded_exponential(20, 75, BlendScenario.LOW, 50)
    assert_rounded_exponential(20, 80, BlendScenario.LOW, 50)
    assert_rounded_exponential(30, 80, BlendScenario.LOW, 55)

    assert_rounded_exponential(50, 65, BlendScenario.LOW, 55)
    assert_rounded_exponential(50, 70, BlendScenario.LOW, 60)
    assert_rounded_exponential(20, 60, BlendScenario.MEDIUM, 50)
    assert_rounded_exponential(30, 60, BlendScenario.MEDIUM, 50)
    assert_rounded_exponential(45, 60, BlendScenario.MEDIUM, 55)
    assert_rounded_exponential(40, 60, BlendScenario.MEDIUM, 55)
    assert_rounded_exponential(50, 60, BlendScenario.MEDIUM, 55)
    assert_rounded_exponential(50, 65, BlendScenario.MEDIUM, 60)
    assert_rounded_exponential(50, 70, BlendScenario.MEDIUM, 65)

    assert_rounded_exponential(30, 50, BlendScenario.MEDIUM, 45)
    assert_rounded_exponential(30, 50, BlendScenario.MEDIUM, 45)


if __name__ == "__main__":
    main()
