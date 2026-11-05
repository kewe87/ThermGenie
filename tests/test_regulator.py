"""Tests of the regulator."""

from custom_components.thermgenie.regulator import Regulator


def reg(kd=0.0):
    return Regulator(kp=0.3, ki=0.05, kd=kd, offset_max=2.0, integral_limit=20.0)


def test_room_too_cold_raises_the_setpoint():
    assert reg().update(21.0, 20.0, 1.0, 0.0) > 21.0


def test_cooling_uses_the_same_formula():
    # Room too warm while cooling: the air conditioner gets a lower setpoint
    assert reg().update(24.0, 25.0, 1.0, 0.0, direction=-1) < 24.0


def test_offset_is_limited():
    assert reg().update(21.0, 10.0, 1.0, 0.0) == 23.0
    assert reg().update(21.0, 30.0, 1.0, 0.0) == 19.0


def test_integral_is_limited():
    r = reg()
    for i in range(1000):
        r.update(21.0, 10.0, 1.0, i * 300.0)
    assert r.integral == 20.0


def test_long_pause_counts_as_one_period():
    r = reg()
    r.update(21.0, 20.0, 500.0, 0.0)
    assert r.integral == 1.0


def _ramp(r, start, slope_per_hour, target, direction=1):
    result = None
    for i in range(7):
        result = r.update(target, start + slope_per_hour * i / 12, 1.0, i * 300.0, direction)
    return result


def test_brake_lowers_the_setpoint_on_a_rise_near_the_target():
    assert _ramp(reg(kd=0.8), 20.5, 1.0, 21.0) < _ramp(reg(), 20.5, 1.0, 21.0)


def test_no_brake_far_from_the_target():
    braked = reg(kd=0.8)
    _ramp(braked, 15.0, 1.0, 21.0)
    assert braked.d_offset == 0.0


def test_no_brake_on_a_falling_temperature():
    braked = reg(kd=0.8)
    _ramp(braked, 21.0, -1.0, 21.0)
    assert braked.d_offset == 0.0


def test_cooling_brake_raises_the_setpoint_on_a_fall_near_the_target():
    braked = _ramp(reg(kd=0.8), 24.5, -1.0, 24.0, direction=-1)
    plain = _ramp(reg(), 24.5, -1.0, 24.0, direction=-1)
    assert braked > plain


def test_without_kd_there_is_no_history_effect():
    a, b = reg(), reg()
    for i in range(50):
        a.update(21.0, 20.5, 1.0, i * 300.0)
        b.update(21.0, 20.5, 1.0, i * 7.0)
    assert a.integral == b.integral
