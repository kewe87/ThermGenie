"""Which settings a thermostat offers as entities on its device page."""

from dataclasses import dataclass
from typing import Any, Callable

from .const import (
    CASCADE_NUMBERS,
    CONF_AIR_COMPARE,
    CONF_AIR_COOL,
    CONF_AIR_FAN,
    CONF_AIR_HEAT,
    CONF_AIR_OFF,
    CONF_AIR_ON,
    CONF_AIR_PERCENT,
    CONF_APPROACH_BELOW,
    CONF_APPROACH_DIRECTION,
    CONF_APPROACH_DISTANCE,
    CONF_APPROACH_TARGET,
    CONF_BOOST_MINUTES,
    CONF_CASCADE_FAN,
    CONF_CASCADE_FOCUS,
    CONF_COOLER,
    CONF_DEVICE_TEMP,
    CONF_DRY_DEW,
    CONF_DRY_DEW_BELOW,
    CONF_DRY_HUMIDITY,
    CONF_DRY_HUMIDITY_BELOW,
    CONF_DTEMP,
    CONF_FAN_BOOST,
    CONF_GUARD_ABOVE,
    CONF_GUARD_BELOW,
    CONF_GUARD_DISTANCE,
    CONF_GUARD_FROM,
    CONF_GUARD_SENSOR,
    CONF_GUARD_UNTIL,
    CONF_HEATERS,
    CONF_HEAT_SOURCE,
    CONF_HOLD_DEVICES,
    CONF_HUMIDITY,
    CONF_INTEGRAL_LIMIT,
    CONF_INTEGRAL_LIMIT_COOL,
    CONF_KD,
    CONF_KD_COOL,
    CONF_KI,
    CONF_KI_COOL,
    CONF_KP,
    CONF_KP_COOL,
    CONF_LEARN,
    CONF_LOCK,
    CONF_OFFSET_MAX,
    CONF_OFFSET_MAX_COOL,
    CONF_OUTDOOR,
    CONF_OUTDOOR_OFF,
    CONF_OUTDOOR_ON,
    CONF_PERIOD,
    CONF_REFERENCE_COOL,
    CONF_REFERENCE_HEAT,
    CONF_SENSOR_TIMEOUT,
    CONF_SLEEP,
    CONF_TUNING,
    CONF_VALVES,
    CONF_VALVE_LIMIT,
    CONF_VALVE_WAIT,
    CONF_WAKE,
    CONF_WAKE_FALLBACK,
    CONF_WAKE_FALLBACK_ON,
    CONF_WAKE_LEAD,
    CONF_WINDOW,
    CONF_WINDOW_CLOSE_DELAY,
    CONF_WINDOW_OPEN_DELAY,
    HEAT_AIR_CONDITIONER,
    HEAT_BOTH,
    HEAT_RADIATORS,
    REFERENCE_COMFORT,
    REFERENCE_HUMIDEX,
    REFERENCE_TEMPERATURE,
    TUNING_AUTOMATIC,
    TUNING_MANUAL,
    TUNING_OBSERVE,
)

Conf = dict[str, Any]


def _always(conf: Conf) -> bool:
    return True


def heating(conf: Conf) -> bool:
    """A locked room does not heat, its heating has nothing to set. Its lock stays in the settings menu."""
    return bool(conf.get(CONF_HEATERS)) and not conf.get(CONF_LOCK)


def _one_heater(conf: Conf) -> bool:
    return heating(conf) and len(conf[CONF_HEATERS]) == 1


def _cooling(conf: Conf) -> bool:
    return bool(conf.get(CONF_COOLER))


def _has(*keys: str) -> Callable[[Conf], bool]:
    return lambda conf: all(conf.get(key) for key in keys)


def _any(*keys: str) -> Callable[[Conf], bool]:
    return lambda conf: any(conf.get(key) for key in keys)


@dataclass(frozen=True)
class Setting:
    """One value. Expert values start disabled, reload ones only work after setting up the thermostat again."""

    key: str
    applies: Callable[[Conf], bool] = _always
    low: float = 0
    high: float = 0
    step: float = 1
    unit: str | None = None
    expert: bool = False
    reload: bool = False
    options: tuple[str, ...] = ()


def _temperature(key: str, applies: Callable[[Conf], bool]) -> Setting:
    return Setting(key, applies, 5, 35, 0.5, "°C")


_cascade = _has(CONF_CASCADE_FOCUS, CONF_CASCADE_FAN)
_alarm = _any(CONF_WAKE, CONF_SLEEP)
_air = _has(CONF_AIR_FAN)
_way_home = _has(CONF_APPROACH_DIRECTION, CONF_APPROACH_DISTANCE)
_guard = _has(CONF_GUARD_SENSOR)
_humidity = _has(CONF_HUMIDITY)

NUMBERS = (
    _temperature("heat_frost", heating),
    _temperature("heat_eco", heating),
    _temperature("heat_comfort", heating),
    _temperature("heat_boost", heating),
    _temperature("cool_eco", _cooling),
    _temperature("cool_comfort", _cooling),
    _temperature("cool_boost", _cooling),
    Setting(CONF_BOOST_MINUTES, _always, 0, 240, 5, "min"),
    Setting(CONF_VALVE_LIMIT, _has(CONF_VALVES), 1, 100, 1, "%"),
    Setting(CONF_VALVE_WAIT, _has(CONF_VALVES), 5, 720, 5, "min"),
    Setting(CONF_WAKE_LEAD, _alarm, 0, 240, 5, "min"),
    Setting(CONF_APPROACH_BELOW, _way_home, 0, 500000, 1000, "m"),
    Setting(CONF_APPROACH_TARGET, _way_home, 5, 30, 0.5, "°C"),
    Setting(CONF_OUTDOOR_OFF, _has(CONF_OUTDOOR), 0, 40, 0.5, "°C"),
    Setting(CONF_OUTDOOR_ON, _has(CONF_OUTDOOR), 0, 40, 0.5, "°C"),
    Setting(CONF_AIR_PERCENT, _air, 1, 100, 1, "%"),
    Setting(CONF_AIR_ON, _has(CONF_AIR_FAN, CONF_AIR_COMPARE), 0.5, 10, 0.5, "K"),
    Setting(CONF_AIR_OFF, _has(CONF_AIR_FAN, CONF_AIR_COMPARE), 0, 10, 0.5, "K"),
    Setting(CONF_GUARD_ABOVE, _guard, 15, 40, 0.1, "°C"),
    Setting(CONF_GUARD_BELOW, _has(CONF_GUARD_SENSOR, CONF_GUARD_DISTANCE), 0, 1000000, 1000, "m"),
    Setting(CONF_DRY_DEW_BELOW, _has(CONF_DRY_DEW), 0, 25, 0.5, "°C"),
    Setting(CONF_DRY_HUMIDITY_BELOW, _has(CONF_DRY_HUMIDITY), 0, 100, 1, "%"),
    Setting(CONF_KP, heating, 0, 3, 0.05, expert=True),
    Setting(CONF_KI, heating, 0, 1, 0.01, expert=True),
    Setting(CONF_KD, _one_heater, 0, 3, 0.1, expert=True),
    Setting(CONF_OFFSET_MAX, heating, 0, 10, 0.5, "K", expert=True),
    Setting(CONF_INTEGRAL_LIMIT, heating, 0, 200, 1, expert=True),
    Setting(CONF_KP_COOL, _cooling, 0, 3, 0.05, expert=True),
    Setting(CONF_KI_COOL, _cooling, 0, 1, 0.01, expert=True),
    Setting(CONF_KD_COOL, _cooling, 0, 3, 0.1, expert=True),
    Setting(CONF_OFFSET_MAX_COOL, _cooling, 0, 10, 0.5, "K", expert=True),
    Setting(CONF_INTEGRAL_LIMIT_COOL, _cooling, 0, 200, 1, expert=True),
    Setting(CONF_PERIOD, _always, 1, 60, 1, "min", expert=True, reload=True),
    Setting(CONF_DTEMP, _always, 0.1, 2, 0.1, "K", expert=True),
    Setting(CONF_SENSOR_TIMEOUT, _always, 5, 720, 5, "min", expert=True),
    Setting(CONF_WINDOW_OPEN_DELAY, _has(CONF_WINDOW), 0, 3600, 10, "s", expert=True),
    Setting(CONF_WINDOW_CLOSE_DELAY, _has(CONF_WINDOW), 0, 3600, 10, "s", expert=True),
    *(
        Setting(key, _cascade, 0, 100, 1, "%", expert=True) if isinstance(default, int) else Setting(key, _cascade, 0, 40, 0.05, "K" if key == "cascade_drift" else "°C", expert=True)
        for key, (_, default) in CASCADE_NUMBERS.items()
    ),
)

# The first value has to stay below the second one
ORDERED = ((CONF_OUTDOOR_ON, CONF_OUTDOOR_OFF), (CONF_AIR_OFF, CONF_AIR_ON))

HEATER_OFFSET = Setting("heater_offset", low=-3, high=3, step=0.1, unit="K")
HEATER_KD = Setting("heater_kd", high=3, step=0.1)

SWITCHES = (
    # A locked room always holds its devices, there is nothing to choose
    Setting(CONF_HOLD_DEVICES, lambda conf: not conf.get(CONF_LOCK)),
    Setting(CONF_WAKE_FALLBACK_ON, _alarm),
    Setting(CONF_AIR_HEAT, _air),
    Setting(CONF_AIR_COOL, _air),
    Setting(CONF_LEARN, heating, reload=True),
    Setting(CONF_DEVICE_TEMP, heating, expert=True),
    Setting(CONF_FAN_BOOST, _cooling, expert=True),
)

TIMES = (
    Setting(CONF_WAKE_FALLBACK, _alarm),
    Setting(CONF_GUARD_FROM, _guard),
    Setting(CONF_GUARD_UNTIL, _guard),
)

_REFERENCES = (REFERENCE_TEMPERATURE, REFERENCE_HUMIDEX, REFERENCE_COMFORT)

SELECTS = (
    Setting(CONF_TUNING, heating, options=(TUNING_MANUAL, TUNING_OBSERVE, TUNING_AUTOMATIC)),
    Setting(CONF_HEAT_SOURCE, lambda conf: heating(conf) and _cooling(conf), options=(HEAT_RADIATORS, HEAT_AIR_CONDITIONER, HEAT_BOTH)),
    Setting(CONF_REFERENCE_HEAT, lambda conf: _humidity(conf) and heating(conf), options=_REFERENCES),
    Setting(CONF_REFERENCE_COOL, lambda conf: _humidity(conf) and _cooling(conf), options=_REFERENCES),
)

# Everything the service set_routine can switch, as far as this thermostat has it
ROUTINES = {
    "sleep": _has(CONF_SLEEP),
    "wake": _alarm,
    "way_home": _way_home,
    "guard": _guard,
    "cascade": _cascade,
    "dry": _any(CONF_DRY_DEW, CONF_DRY_HUMIDITY),
    "air": _air,
}
