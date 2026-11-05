"""Night cascade: a fan as the fast actuator, the air conditioner behind it. No Home Assistant imports.

The inner loop drives the fan towards the felt temperature at the bed. The outer loop only
moves the setpoint of the air conditioner when the fan has reached its limit, or when a
fan at its minimum shows that there is too much cooling. A throttled fan with a cold
source room is therefore impossible by construction.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CascadeSettings:
    """The set screws of the cascade."""

    base: float = 22.4  # K, zero point of the wandering band
    drift: float = 0.15  # K per hour of sleep
    drift_hours: float = 7.0
    fan_authority: float = 2.0  # K of felt cooling the fan delivers at 100 %
    fan_cap: int = 60  # %, noise limit
    fan_cap_hot: int = 80  # %, noise limit on really hot nights
    fan_floor: int = 15  # %, air change in a closed room
    fan_floor_cooling: int = 30  # %, keeps the cooled air stream going
    hot: float = 24.0  # °C real temperature that allows the higher noise limit
    hot_hold: float = 23.8  # °C keeps it while the fan is already up
    cold: float = 21.0  # °C real temperature that throttles the fan in any case
    limit_early: float = 20.5  # °C lowest setpoint at the start of the night
    limit_mid: float = 21.0  # °C from 4 hours of sleep on
    limit_late: float = 22.0  # °C from 6 hours of sleep on
    below_preset: float = 2.0  # K, never further below the comfort preset
    step: float = 0.5  # K per outer loop


@dataclass(frozen=True)
class CascadeResult:
    """What the cascade wants."""

    scenario: str
    base: float
    gap: float
    demand: int
    hot: bool
    cold: bool
    cap: int
    floor: int
    fan: int
    lower_limit: float
    target: float | None  # new setpoint of the air conditioner, None to leave it


def scenario(window_open: bool, cooling: bool) -> str:
    """A: through draught, B: cooling, C: mild night, D: window open while cooling."""
    if window_open:
        return "D" if cooling else "A"
    return "B" if cooling else "C"


def decide(
    settings: CascadeSettings,
    hours: float,
    felt: float,
    real: float,
    target: float,
    fan_now: int,
    preset: float,
    window_open: bool,
    cooling: bool,
) -> CascadeResult:
    """Return the fan speed and setpoint for one cycle."""
    s = settings
    case = scenario(window_open, cooling)
    base = round(s.base + min(max(hours, 0), s.drift_hours) * s.drift, 2)
    gap = round(felt - base, 3)
    # Felt cooling = authority * (pct / 100) ** 0.9, solved for pct
    demand = int(round(100 * (min(max(gap, 0), s.fan_authority) / s.fan_authority) ** 1.1111, 0))

    hot = demand > s.fan_cap and (real >= s.hot or (real >= s.hot_hold and fan_now >= 75))
    cold = demand < 5 or (demand < 20 and fan_now <= 20) or real < s.cold
    cap = s.fan_floor if cold else (s.fan_cap_hot if hot else s.fan_cap)
    floor = s.fan_floor if (cold or case != "B" or demand < s.fan_floor_cooling) else s.fan_floor_cooling
    fan = max(floor, min(cap, demand))

    time_limit = s.limit_late if hours >= 6 else (s.limit_mid if hours >= 4 else s.limit_early)
    lower_limit = max(time_limit, preset - s.below_preset)

    new_target = None
    if case == "B":
        if target < lower_limit:
            new_target = lower_limit
        elif demand > cap and target > lower_limit:
            new_target = max(target - s.step, lower_limit)
        elif demand < s.fan_floor_cooling and target < preset:
            new_target = min(target + s.step, preset)

    return CascadeResult(case, base, gap, demand, hot, cold, cap, floor, fan, lower_limit, new_target)
