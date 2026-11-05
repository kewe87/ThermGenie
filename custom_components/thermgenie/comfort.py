"""Felt temperature from temperature and humidity. No Home Assistant imports."""

import math


def dew_point(temperature: float, humidity: float) -> float:
    """Return the dew point in °C."""
    a0 = 373.15 / (273.15 + temperature)
    total = -7.90298 * (a0 - 1)
    total += 5.02808 * math.log10(a0)
    total += -1.3816e-7 * (10 ** (11.344 * (1 - 1 / a0)) - 1)
    total += 8.1328e-3 * (10 ** (-3.49149 * (a0 - 1)) - 1)
    total += math.log10(1013.246)
    vapour = 10 ** (total - 3) * humidity
    log_vapour = math.log(vapour / 0.61078)
    return (241.88 * log_vapour) / (17.558 - log_vapour)


def humidex(temperature: float, humidity: float) -> float:
    """Return the humidex. Counts humidity without limit, meant for real heat."""
    pressure = 6.11 * math.exp(5417.7530 * (1 / 273.16 - 1 / (dew_point(temperature, humidity) + 273.15)))
    return temperature + 0.5555 * (pressure - 10.0)


def comfort(temperature: float, dew: float) -> float:
    """Return the comfort temperature: humidity counts from dew point 16 on, at most +2.5 K."""
    return round(temperature + min(max(0.0, dew - 16.0) * 0.5, 2.5), 2)
