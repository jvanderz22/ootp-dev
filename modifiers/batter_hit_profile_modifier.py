from enum import Enum
from models.game_players import GamePlayer
from modifiers.base_modifier import BaseModifier


# elite: >= 75
# good >= 65
# aabv >= 55
# babv <= 45
# poor <= 35
# vpoor <= 25


class RatingsTier(Enum):
    ELITE = 1
    GOOD = 2
    ABOVE_AVG = 3
    AVG = 4
    BELOW_AVG = 5
    POOR = 6
    VERY_POOR = 7


class BattedBallProfile(Enum):
    NORMAL = "Normal"
    GROUNDBALL = "Groundball"
    FLYBALL = "Flyball"
    LINE_DRIVE = "Line Drive"


class PullTendency(Enum):
    NORMAL = "Normal"
    PULL = "Pull"
    EXTREME_PULL = "Extreme Pull"
    SPRAY = "Spray"


def get_ratings_tier(rating: float):
    if rating >= 75:
        return RatingsTier.ELITE
    elif rating >= 65:
        return RatingsTier.GOOD
    elif rating >= 55:
        return RatingsTier.ABOVE_AVG
    elif rating >= 50:
        return RatingsTier.AVG
    elif rating > 35:
        return RatingsTier.BELOW_AVG
    elif rating > 25:
        return RatingsTier.POOR
    return RatingsTier.VERY_POOR


class BatterHitProfileModifier(BaseModifier):
    def __init__(self, is_overall=False):
        self.is_overall = is_overall

    def calculate_player_modifier(self, player: GamePlayer):
        profile = player.batted_ball_profile
        gb_tendency = player.gb_tendency
        fb_tendency = player.fb_tendency

        modifier = 1

        speed_tier = get_ratings_tier(player.speed)
        # todo: fix into either power or power_ovr
        power_tier = (
            get_ratings_tier(player.power_ovr)
            if self.is_overall
            else get_ratings_tier(player.power)
        )

        # normal hit profile
        # pull gb tendency: .99
        # xpull gb tendency: .97
        # spray gb tendency: 1.02

        # pull fb tendency + aavg power: 1.005
        # pull fb tendency + good power: 1.015
        # xpull fb tendency + aavg power: 1.015
        # xpull fb tendency + good power: 1.025

        # elite speed: 1.035
        # good speed: 1.02
        # aabv speed: 1
        # babv speed: 1
        # poor speed: .98
        if profile == BattedBallProfile.NORMAL.value:
            if gb_tendency == PullTendency.PULL.value:
                modifier *= 0.99
            elif gb_tendency == PullTendency.EXTREME_PULL.value:
                modifier *= 0.97
            elif gb_tendency == PullTendency.SPRAY.value:
                modifier *= 1.02

            if power_tier == RatingsTier.ELITE or power_tier == RatingsTier.GOOD:
                if fb_tendency == PullTendency.PULL.value:
                    modifier *= 1.015
                elif fb_tendency == PullTendency.EXTREME_PULL.value:
                    modifier *= 1.025
            elif power_tier == RatingsTier.ABOVE_AVG:
                if fb_tendency == PullTendency.PULL.value:
                    modifier *= 1.005
                elif fb_tendency == PullTendency.EXTREME_PULL.value:
                    modifier *= 1.015

            if speed_tier == RatingsTier.ELITE:
                modifier *= 1.035
            elif speed_tier == RatingsTier.GOOD:
                modifier *= 1.02
            elif speed_tier == RatingsTier.POOR:
                modifier *= 0.98
            elif speed_tier == RatingsTier.VERY_POOR:
                modifier *= 0.97

        # fb hit profile
        # pull gb tendency: .99
        # xpull gb tendency: .975
        # spray gb tendency: 1.01

        # poor power: .9
        # bavg power: .97
        # aavg power: 1.01
        # good power: 1.025

        # pull fb tendency + aavg power: 1.01
        # pull fb tendency + good power: 1.02
        # xpull fb tendency + aavg power: 1.025
        # xpull fb tendency + good power: 1.05
        if profile == BattedBallProfile.FLYBALL.value:
            if gb_tendency == PullTendency.PULL.value:
                modifier *= 0.99
            elif gb_tendency == PullTendency.EXTREME_PULL.value:
                modifier *= 0.975
            elif gb_tendency == PullTendency.SPRAY.value:
                modifier *= 1.01

            if power_tier == RatingsTier.ELITE or power_tier == RatingsTier.GOOD:
                modifier *= 1.025
                if fb_tendency == PullTendency.PULL.value:
                    modifier *= 1.02
                elif fb_tendency == PullTendency.EXTREME_PULL.value:
                    modifier *= 1.05
            elif power_tier == RatingsTier.ABOVE_AVG:
                modifier *= 1.01
                if fb_tendency == PullTendency.PULL.value:
                    modifier *= 1.01
                elif fb_tendency == PullTendency.EXTREME_PULL.value:
                    modifier *= 1.02
            elif power_tier == RatingsTier.BELOW_AVG:
                modifier *= 0.97
            elif power_tier == RatingsTier.POOR or power_tier == RatingsTier.VERY_POOR:
                modifier *= 0.9

        # gb hit profile
        # pull gb tendency: .98
        # xpull gb tendency: .96
        # spray gb tendency: 1.03

        # poor power: 1.03
        # bavg power: 1.01
        # aavg power: .985
        # good power: .95

        # elite speed: 1.07
        # good speed: 1.04
        # aabv speed: 1.01
        # babv speed: .96
        # poor speed: .9

        if profile == BattedBallProfile.GROUNDBALL.value:
            if gb_tendency == PullTendency.PULL.value:
                modifier *= 0.98
            elif gb_tendency == PullTendency.EXTREME_PULL.value:
                modifier *= 0.96
            elif gb_tendency == PullTendency.SPRAY.value:
                modifier *= 1.03

            if power_tier == RatingsTier.ELITE or power_tier == RatingsTier.GOOD:
                modifier *= 0.95
            elif power_tier == RatingsTier.ABOVE_AVG:
                modifier *= 0.985
            elif power_tier == RatingsTier.BELOW_AVG:
                modifier *= 1.01
            elif power_tier == RatingsTier.POOR or power_tier == RatingsTier.VERY_POOR:
                modifier *= 1.03

            if speed_tier == RatingsTier.ELITE:
                modifier *= 1.07
            elif speed_tier == RatingsTier.GOOD:
                modifier *= 1.04
            elif speed_tier == RatingsTier.ABOVE_AVG:
                modifier *= 1.01
            elif speed_tier == RatingsTier.BELOW_AVG:
                modifier *= 0.96
            elif speed_tier == RatingsTier.POOR or speed_tier == RatingsTier.VERY_POOR:
                modifier *= 0.9

        # ld hit profile
        # base modifier: 1.05

        # pull gb tendency: .99
        # xpull gb tendency: .975
        # spray gb tendency: 1.03

        # spray fb tendency: 1.02

        # pull fb tendency + good power: 1.035
        # pull fb tendency + aavg power: 1.02
        # pull fb tendency + bvg power: .995
        # pull fb tendency + poor power: .975

        # xpull fb tendency + good power: 1.05
        # xpull fb tendency + aavg power: 1.025
        # xpull fb tendency + bvg power: .99
        # xpull fb tendency + poor power: .95

        # elite speed: 1.035
        # good speed: 1.02
        # aabv speed: 1
        # babv speed: 1
        # poor speed: .98

        if profile == BattedBallProfile.LINE_DRIVE.value:
            modifier *= 1.04
            if gb_tendency == PullTendency.PULL.value:
                modifier *= 0.99
            elif gb_tendency == PullTendency.EXTREME_PULL.value:
                modifier *= 0.975
            elif gb_tendency == PullTendency.SPRAY.value:
                modifier *= 1.01

            if fb_tendency == PullTendency.SPRAY.value:
                modifier *= 1.01
            if fb_tendency == PullTendency.PULL.value:
                if power_tier == RatingsTier.ELITE or power_tier == RatingsTier.GOOD:
                    modifier *= 1.03
                elif power_tier == RatingsTier.ABOVE_AVG:
                    modifier *= 1.01
                elif power_tier == RatingsTier.BELOW_AVG:
                    modifier *= 0.99
                elif (
                    power_tier == RatingsTier.POOR
                    or power_tier == RatingsTier.VERY_POOR
                ):
                    modifier *= 0.975
            if fb_tendency == PullTendency.EXTREME_PULL.value:
                if power_tier == RatingsTier.ELITE or power_tier == RatingsTier.GOOD:
                    modifier *= 1.035
                elif power_tier == RatingsTier.ABOVE_AVG:
                    modifier *= 1.02
                elif power_tier == RatingsTier.BELOW_AVG:
                    modifier *= 0.985
                elif (
                    power_tier == RatingsTier.POOR
                    or power_tier == RatingsTier.VERY_POOR
                ):
                    modifier *= 0.95

            if speed_tier == RatingsTier.ELITE:
                modifier *= 1.025
            elif speed_tier == RatingsTier.GOOD:
                modifier *= 1.01
            elif speed_tier == RatingsTier.POOR or speed_tier == RatingsTier.VERY_POOR:
                modifier *= 0.98

        return modifier
