"""PI regulator with a brake on the approach to the target. No Home Assistant imports.

The room sensor is the truth, the device only gets a shifted setpoint. The same
formula works for heating and cooling: a room below the target raises the setpoint.
"""

from collections import deque

D_ERROR_WINDOW = 1.0  # the brake only acts within this distance to the target (K)
D_MAX_SLOPE = 3.0  # K/h, limits a single outlier of the room sensor
D_WINDOW_SEC = 1800  # time window of the regression over the room temperature
D_MIN_SPAN_SEC = 900  # no brake until the samples span this duration
MAX_PERIODS = 2.0  # a longer gap means the regulation was paused


def _limit(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))


class Regulator:
    """Regulator of one device."""

    def __init__(self, kp: float, ki: float, kd: float, offset_max: float, integral_limit: float) -> None:
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.offset_max = offset_max
        self.integral_limit = integral_limit
        self.integral = 0.0
        self.d_offset = 0.0
        self._history: deque[tuple[float, float]] = deque(maxlen=60)

    def _approach_slope(self, room: float, now: float, direction: int) -> float:
        """Return the speed towards the target in K/h, 0 when moving away from it."""
        self._history.append((now, room))
        while now - self._history[0][0] > D_WINDOW_SEC:
            self._history.popleft()
        if now - self._history[0][0] < D_MIN_SPAN_SEC:
            return 0.0

        count = len(self._history)
        mean_t = sum(t for t, _ in self._history) / count
        mean_v = sum(v for _, v in self._history) / count
        den = sum((t - mean_t) ** 2 for t, _ in self._history)
        if den == 0:
            return 0.0
        slope = sum((t - mean_t) * (v - mean_v) for t, v in self._history) / den * 3600.0
        return min(D_MAX_SLOPE, max(0.0, slope * direction))

    def update(self, target: float, room: float, periods: float, now: float, direction: int = 1) -> float:
        """Return the shifted setpoint. direction is +1 for heating and -1 for cooling."""
        step = 1.0 if periods > MAX_PERIODS else periods
        error = target - room
        missing = error * direction  # what is left to reach the target, negative once past it

        slope = self._approach_slope(room, now, direction) if self.kd else 0.0
        self.d_offset = self.kd * slope if missing < D_ERROR_WINDOW else 0.0

        self.integral = self._next_integral(error, step, braking=self.d_offset > 0 and missing > 0)
        correction = self.kp * error + self.ki * self.integral - direction * self.d_offset
        return target + _limit(correction, self.offset_max)

    def _next_integral(self, error: float, step: float, braking: bool) -> float:
        """Sum up the error. Past the target the old sum loses half its size per period, so it cannot overshoot for long."""
        total = self.integral
        if total * error < 0:
            total *= 0.5**step
        if not braking:
            total += error * step
        return _limit(total, self.integral_limit)
