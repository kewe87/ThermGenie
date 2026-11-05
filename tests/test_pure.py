"""Tests of the parts without Home Assistant."""

import pytest

from custom_components.thermgenie.cascade import CascadeSettings, decide, scenario
from custom_components.thermgenie.comfort import comfort, dew_point, humidex
from custom_components.thermgenie.learning import Learner, PhaseTracker, flow_bucket

S = CascadeSettings()


def test_comfort_values_match_the_formulas():
    assert dew_point(21.5, 47) == pytest.approx(9.7337, abs=0.001)
    assert humidex(21.5, 47) == pytest.approx(22.6563, abs=0.001)
    assert dew_point(30, 100) == pytest.approx(30, abs=0.05)


@pytest.mark.parametrize(("window", "cooling", "case"), [(True, False, "A"), (False, True, "B"), (False, False, "C"), (True, True, "D")])
def test_scenarios(window, cooling, case):
    assert scenario(window, cooling) == case


def test_fan_follows_the_gap_and_stays_below_the_noise_limit():
    low = decide(S, 0, 22.9, 23, 24, 30, 24.5, False, True)
    high = decide(S, 0, 24.4, 23, 24, 30, 24.5, False, True)
    assert low.fan < high.fan
    assert high.fan == S.fan_cap


def test_hot_night_allows_more_noise():
    assert decide(S, 0, 24.4, 24.5, 24, 30, 24.5, False, True).fan > S.fan_cap


def test_cold_room_throttles_the_fan_whatever_the_gap():
    result = decide(S, 0, 24.4, 20.5, 24, 60, 24.5, False, True)
    assert result.cold and result.fan == S.fan_floor


def test_outer_loop_only_moves_the_air_conditioner_when_cooling():
    assert decide(S, 0, 24.4, 23, 24, 60, 24.5, False, False).target is None
    assert decide(S, 0, 24.4, 23, 24, 60, 24.5, True, True).target is None
    assert decide(S, 0, 24.4, 23, 24, 60, 24.5, False, True).target == 23.5


def test_outer_loop_gives_cooling_back_when_the_fan_idles():
    assert decide(S, 0, 22.5, 23, 23, 15, 24.5, False, True).target == 23.5
    assert decide(S, 0, 22.5, 23, 24.5, 15, 24.5, False, True).target is None


def test_lower_limit_rises_during_the_night():
    assert decide(S, 7, 24.4, 23, 21.5, 60, 24.5, False, True).target == 22.5
    assert decide(S, 1, 24.4, 23, 22.5, 60, 24.5, False, True).lower_limit == 22.5
    assert decide(S, 1, 24.4, 23, 22.5, 60, 22.5, False, True).lower_limit == 20.5


def test_flow_ranges():
    assert [flow_bucket(f) for f in (None, 50, 65, 75)] == ["unknown", "low", "mid", "high"]


def _phase(*rooms, target=21.5, flow=65):
    tracker = PhaseTracker()
    result = None
    for i, room in enumerate(rooms):
        result = tracker.update(i * 600.0, room, target, True, flow) or result
    return result


def test_clean_phase_reports_overshoot_and_flow():
    phase = _phase(20.5, 21.0, 21.5, 22.0, 22.0, 21.8)
    assert phase["overshoot"] == 0.5
    assert phase["bucket"] == "mid"


def test_phase_breaks_on_new_target_or_when_heating_stops():
    tracker = PhaseTracker()
    tracker.update(0, 20, 21.5, True, 65)
    assert tracker.update(600, 21.6, 22.0, True, 65) is None
    assert not tracker.active
    tracker.update(0, 20, 21.5, True, 65)
    tracker.update(600, 20, 21.5, False, 65)
    assert not tracker.active


def test_learner_moves_in_small_bounded_steps_per_range():
    learner = Learner()
    learner.learn({"bucket": "mid", "overshoot": 0.5})
    assert learner.factor(65) == 1.1
    assert learner.factor(50) == 1.0
    learner.learn({"bucket": "low", "overshoot": 0.0})
    assert learner.factor(50) == 0.95
    learner.learn({"bucket": "low", "overshoot": 0.2})
    assert learner.factor(50) == 0.95
    for _ in range(60):
        learner.learn({"bucket": "mid", "overshoot": 1})
    assert learner.factor(65) == 2.5
    learner.reset()
    assert learner.factor(65) == 1.0
    assert Learner(learner.as_dict()).history
