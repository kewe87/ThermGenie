"""Tests of the valve control: the room model, the plan and the valve commands."""

from math import exp, sin, pi
import random

import pytest

from custom_components.thermgenie.valve_control import RoomModel, ValvePlanner, heat_input, round_valve


def simulate(days, outdoor_base=3.0, seed=1, tau=30.0, a=2.0, b=0.08, c=0.2):
    """A virtual room heated by a valve, measured every 5 minutes with a 0.1 K sensor."""
    random.seed(seed)
    model = RoomModel()
    planner = ValvePlanner(model)
    room, heat, valve, t = 19.0, 0.0, 0.0, 0.0
    log = []
    for _ in range(int(days * 24 * 12)):
        hour = (t / 3600) % 24
        target = 21.0 if 6 <= hour < 22 else 18.0
        outdoor = outdoor_base + 4 * sin((hour - 9) / 24 * 2 * pi)
        flow = 60 - 0.8 * outdoor
        for _ in range(5):
            heat += (heat_input(valve, room, flow) - heat) * (1 - exp(-1 / tau))
            room += (a * heat - b * (room - outdoor) + c) / 60
        t += 300
        measured = round(room + random.gauss(0, 0.03), 1)
        model.observe(t, measured, outdoor, valve, flow)
        sent = planner.command(t, planner.plan(t, measured, target, outdoor, flow))
        if sent is not None:
            valve = sent
        log.append((t, hour, target, room, valve, planner.mode))
    return model, planner, log


def test_the_model_learns_the_room():
    model, _planner, _log = simulate(4)
    assert model.ready
    a, b, _c = model.best.theta
    assert a == pytest.approx(2.0, rel=0.15)
    assert b == pytest.approx(0.08, rel=0.3)
    assert model.best.tau_min in (25.0, 45.0)


def test_the_room_holds_its_target_without_overshooting():
    _model, planner, log = simulate(5)
    assert planner.mode == "model"
    day = [entry for entry in log if entry[0] > 4 * 86400 and 11 <= entry[1] < 22]
    assert max(room - target for _t, _h, target, room, _v, _m in day) < 0.3
    assert sum(abs(room - target) for _t, _h, target, room, _v, _m in day) / len(day) < 0.2


def test_the_valves_move_rarely():
    _model, _planner, log = simulate(3)
    moves = sum(1 for before, after in zip(log, log[1:]) if before[4] != after[4] and after[0] > 2 * 86400)
    assert moves < 80


def test_until_the_model_knows_the_room_a_pi_regulator_drives():
    model = RoomModel()
    planner = ValvePlanner(model)
    assert planner.plan(0, 20.0, 21.0, 0.0, 55.0) > 0
    assert planner.mode == "pi"
    assert planner.plan(300, 22.0, 21.0, 0.0, 55.0) == 0.0  # clearly too warm: closed


def test_the_curve_needs_more_valve_when_it_is_colder():
    model, _planner, _log = simulate(4)
    curve = model.summary(21.0, 60.0)["curve"]
    assert curve["-5"] >= curve["0"] >= curve["5"] >= curve["10"]


def test_the_model_survives_a_restart():
    model, _planner, _log = simulate(2)
    again = RoomModel(model.as_dict())
    assert again.best.theta == pytest.approx(model.best.theta, abs=1e-4)
    assert again.samples == model.samples


def test_a_jump_does_not_teach_the_model():
    model = RoomModel()
    for i in range(4):
        model.observe(i * 300.0, 20.0, 5.0, 0.0, 55.0)
    samples = model.samples
    model.observe(1200.0, 23.0, 5.0, 0.0, 55.0)  # window, sun on the sensor or a sensor jump
    assert model.samples == samples


def test_valve_commands_are_rounded_and_spared():
    planner = ValvePlanner(RoomModel())
    assert planner.command(0, 33.0) == 35.0
    assert planner.command(60, 52.0) is None  # too soon
    assert planner.command(700, 41.0) is None  # one small step waits longer
    assert planner.command(700, 55.0) == 55.0
    assert planner.command(760, 0.0) == 0.0  # closing never waits
    assert round_valve(103) == 100.0 and round_valve(-4) == 0.0


class _NotReady(RoomModel):
    """A model that never trusts itself, so the PI regulator drives."""

    @property
    def ready(self) -> bool:
        return False


def _warm_up(planner_cls=ValvePlanner, tau=75.0, a=3.4, b=0.05, start=20.5, target=22.0):
    """A slow room like a living room with two radiators: warm up from eco to comfort."""
    model = _NotReady()
    planner = planner_cls(model)
    room, heat, valve, t, outdoor, flow = start, 0.0, 0.0, 0.0, 0.0, 62.0
    peak, valves = room, []
    for _ in range(6 * 60):  # six hours, one minute steps
        heat += (heat_input(valve, room, flow) - heat) * (1 - exp(-1 / tau))
        room += (a * heat - b * (room - outdoor)) / 60
        t += 60
        if int(t) % 120 == 0:
            sent = planner.command(t, planner.plan(t, round(room, 1), target, outdoor, flow))
            if sent is not None:
                valve = sent
        peak = max(peak, room)
        valves.append(valve)
    return peak, room, valves


def test_the_pi_regulator_brakes_a_room_that_rises_fast():
    peak, end, _ = _warm_up()
    assert peak - 22.0 < 0.45  # the radiators' afterglow no longer carries the room far beyond
    assert abs(end - 22.0) < 0.4  # and it still arrives and holds


def test_the_pi_regulator_still_warms_up_a_cold_room():
    peak, end, valves = _warm_up(start=19.0)
    assert max(valves) >= 60
    assert end > 21.6


def test_a_room_that_stayed_too_warm_does_not_reopen_at_the_old_level():
    planner = ValvePlanner(_NotReady())
    for i in range(10):  # an hour of holding at the target builds the integral
        planner.plan(i * 360.0, 22.0, 22.0, 5.0, 60.0)
    held = planner.pi_integral
    for i in range(10, 20):  # then the afterglow keeps the room too warm for an hour, valve shut
        assert planner.plan(i * 360.0, 22.4, 22.0, 5.0, 60.0) == 0.0
    assert planner.pi_integral < held - 3.0  # the integral bled meanwhile
    for i in range(20, 25):  # slowly cooling back towards the target
        assert planner.plan(i * 360.0, 22.2, 22.0, 5.0, 60.0) == 0.0  # still above: stays shut
    assert planner.plan(25 * 360.0, 22.0, 22.0, 5.0, 60.0) > 0.0  # back at the target it heats again
    assert planner.pi_integral < held - 3.0  # but from a lower base than before the overshoot


def test_what_the_room_needs_survives_a_restart_and_airing():
    model = RoomModel()
    planner = ValvePlanner(model)
    planner.plan(0.0, 20.0, 20.0, 3.0, None)
    for minute in range(1, 240):  # a strong radiator: the room stays a bit too warm, the integral bleeds
        planner.plan(minute * 60.0, 20.4, 20.0, 3.0, None)
    learned = planner.pi_integral
    assert learned < 15.0
    planner.reset()  # window open
    assert planner.pi_integral == learned
    restarted = ValvePlanner(RoomModel(model.as_dict()))
    assert restarted.pi_integral == pytest.approx(learned, abs=0.01)
    assert restarted.plan(0.0, 20.0, 20.0, 3.0, None) < 15.0  # not the wide opening of a fresh start
    model.reset()
    assert planner.pi_integral is None


def test_the_correction_of_the_plan_survives_a_restart():
    model = RoomModel()
    planner = ValvePlanner(model)
    planner.trim = 4.0
    planner.reset()  # airing or a pause starts the measurement again
    assert planner.trim == 4.0
    again = ValvePlanner(RoomModel(model.as_dict()))
    assert again.trim == 4.0
