"""Valve control: drives the radiator valves itself and learns how the room behaves. No Home Assistant imports.

The room is described by a small heat balance, in kelvin per hour:

    dT/dt = a * h - b * (T - T_out) + c

h is the heat the radiators give off. It follows the valve opening times the
flow temperature above the room with a delay, because a radiator warms up and
cools down slowly. a says how strongly the radiators heat the room, b how fast it
loses heat to the outside, c what else warms it (sun, people, the neighbours).

The model learns a, b and c all the time with recursive least squares, for several
radiator delays at once, and keeps the delay that predicts best. With it the valve
opening is planned ahead: the opening that keeps the room closest to the target over
the next two hours wins, an overshoot counts more than being a little too cold.
Until the model knows the room well enough a simple PI regulator drives the valves.
"""

from collections import deque
from dataclasses import dataclass
from math import exp, sqrt
from typing import Any

FLOW_NORM = 40.0  # K of flow above the room that count as one unit of heat
FLOW_DEFAULT = 55.0  # assumed flow without a sensor
TAUS_MIN = (10.0, 25.0, 45.0, 75.0)  # radiator delays that are tried, in minutes
WINDOW_SEC = 15 * 60  # the slope of the room temperature is measured over this time
MIN_STEP_SEC = 60  # samples closer than this are skipped
MAX_GAP_SEC = 30 * 60  # a longer gap starts the measurement again
MAX_SLOPE = 6.0  # K/h, a faster change is a sensor jump or an open window
FORGET = 0.997  # forgetting factor of the least squares, about two days of memory
P_START = 50.0
P_MAX = 1000.0
ERROR_SMOOTH = 0.03
BIAS_SMOOTH = 0.15
READY_SAMPLES = 48
READY_HEATING = 8  # samples with the radiators clearly warm
READY_COOLING = 8  # samples with the radiators clearly cold
READY_RMSE = 0.8  # K/h
BOUNDS = ((0.02, 30.0), (0.0, 2.0), (-3.0, 3.0))

HORIZON_MIN = 120
PLAN_STEP_MIN = 5
SETTLE_MIN = 15  # the first minutes of the plan cannot be changed any more
OVERSHOOT_FREE = 0.1  # K above the target that cost like being too cold
OVERSHOOT_WEIGHT = 5.0
MOVE_WEIGHT = 1e-4  # per squared percent of valve change
TRIM_GAIN = 2.0  # percent per kelvin hour
TRIM_MAX = 10.0

PI_KP = 40.0  # percent per kelvin
PI_KI = 10.0  # percent per kelvin hour
PI_I_MAX = 70.0
# The PI regulator looks ahead: radiators keep heating long after the valve closed, so a
# room that is rising fast is braked by where it will be, not by where it is.
TREND_SEC = 20 * 60  # the rise of the room is measured over this time
TREND_MIN_SEC = 8 * 60  # a shorter stretch says nothing yet
LEAD_OF_DELAY = 0.6  # how far ahead it looks, as a share of the learned radiator delay
LEAD_MIN_H = 0.25
LEAD_MAX_H = 0.75
LEAD_FALLING = 0.5  # a falling room opens a little earlier, but more carefully
VALVE_STEP = 5.0  # valve positions are rounded to this
VALVE_MIN_GAP_SEC = 10 * 60  # a valve is moved at most this often, closing excepted
VALVE_SMALL_GAP_SEC = 30 * 60  # a move of one step waits this long
CURVE_OUTDOOR = (-10.0, -5.0, 0.0, 5.0, 10.0, 15.0)


def heat_input(valve: float, room: float, flow: float | None) -> float:
    """Return what the radiators give the room for an opening in percent, before their delay."""
    if flow is None:
        return valve / 100.0
    return valve / 100.0 * max(flow - room, 0.0) / FLOW_NORM


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round_valve(value: float) -> float:
    """Round to the valve step and keep within 0 to 100 percent."""
    return float(_clamp(round(value / VALVE_STEP) * VALVE_STEP, 0.0, 100.0))


class Estimator:
    """Recursive least squares over a, b and c for one radiator delay."""

    def __init__(self, tau_min: float, data: dict[str, Any] | None = None) -> None:
        self.tau_min = tau_min
        self.theta = [1.0, 0.1, 0.0]
        self.p = [[P_START if i == j else 0.0 for j in range(3)] for i in range(3)]
        self.heat = 0.0
        self.mse: float | None = None
        if data:
            self.theta = [float(v) for v in data["theta"]]
            self.p = [[float(v) for v in row] for row in data["p"]]
            self.heat = float(data.get("heat", 0.0))
            self.mse = data.get("mse")

    def advance(self, heat: float, seconds: float) -> None:
        """Let the radiators warm up or cool down for some seconds."""
        k = 1.0 - exp(-seconds / 60.0 / self.tau_min)
        self.heat += (heat - self.heat) * k

    def predict(self, x: list[float]) -> float:
        return sum(t * v for t, v in zip(self.theta, x))

    def learn(self, x: list[float], y: float) -> None:
        """One step of recursive least squares, the parameters stay within physical bounds."""
        error = y - self.predict(x)
        self.mse = error * error if self.mse is None else (1 - ERROR_SMOOTH) * self.mse + ERROR_SMOOTH * error * error
        px = [sum(self.p[i][j] * x[j] for j in range(3)) for i in range(3)]
        denom = FORGET + sum(x[i] * px[i] for i in range(3))
        gain = [v / denom for v in px]
        self.theta = [_clamp(self.theta[i] + gain[i] * error, *BOUNDS[i]) for i in range(3)]
        self.p = [[(self.p[i][j] - gain[i] * px[j]) / FORGET for j in range(3)] for i in range(3)]
        trace = sum(self.p[i][i] for i in range(3))
        if trace > P_MAX:  # nothing new to learn for a long time: do not let it run away
            self.p = [[v * P_MAX / trace for v in row] for row in self.p]

    def as_dict(self) -> dict[str, Any]:
        return {"theta": [round(v, 5) for v in self.theta], "p": [[round(v, 6) for v in row] for row in self.p], "heat": round(self.heat, 4), "mse": None if self.mse is None else round(self.mse, 5)}


@dataclass
class _Sample:
    time: float
    room: float
    outdoor: float
    heats: list[float]


class RoomModel:
    """Learns the room from what the valves did and how the temperature answered."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        stored = {float(e["tau_min"]): e for e in data.get("estimators", [])}
        self.estimators = [Estimator(tau, stored.get(tau)) for tau in TAUS_MIN]
        self.samples = int(data.get("samples", 0))
        self.heating_samples = int(data.get("heating_samples", 0))
        self.cooling_samples = int(data.get("cooling_samples", 0))
        self.flow_mean = data.get("flow_mean")
        self.bias = 0.0  # K/h the model was off lately, corrects the plan until the fit catches up
        self._window: deque[_Sample] = deque()
        self._last: float | None = None

    @property
    def best(self) -> Estimator:
        """Return the delay that predicts the room best so far."""
        scored = [e for e in self.estimators if e.mse is not None]
        return min(scored, key=lambda e: e.mse) if scored else self.estimators[1]

    @property
    def ready(self) -> bool:
        """Only a model that has seen the radiators warm and cold and predicts well may plan."""
        best = self.best
        return (
            self.samples >= READY_SAMPLES
            and self.heating_samples >= READY_HEATING
            and self.cooling_samples >= READY_COOLING
            and best.mse is not None
            and sqrt(best.mse) <= READY_RMSE
            and best.theta[0] > BOUNDS[0][0]
        )

    def interrupt(self) -> None:
        """An open window or a dead sensor: what follows must not be mixed with what was before."""
        self._window.clear()
        self._last = None

    def observe(self, now: float, room: float, outdoor: float, valve: float, flow: float | None) -> bool:
        """Feed one measurement. Returns True when the model learned from it."""
        if self._last is not None and now - self._last < MIN_STEP_SEC:
            return False
        if self._last is not None and now - self._last > MAX_GAP_SEC:
            self.interrupt()
        seconds = 0.0 if self._last is None else now - self._last
        self._last = now
        heat = heat_input(valve, room, flow)
        for estimator in self.estimators:
            estimator.advance(heat, seconds)
        if flow is not None:
            self.flow_mean = flow if self.flow_mean is None else round(0.99 * self.flow_mean + 0.01 * flow, 2)
        self._window.append(_Sample(now, room, outdoor, [e.heat for e in self.estimators]))
        while now - self._window[0].time > WINDOW_SEC * 1.5:
            self._window.popleft()
        first = self._window[0]
        span = now - first.time
        if span < WINDOW_SEC:
            return False
        slope = (room - first.room) / (span / 3600.0)
        if abs(slope) > MAX_SLOPE:
            self.interrupt()
            return False
        count = len(self._window)
        mean_room = sum(s.room for s in self._window) / count
        mean_out = sum(s.outdoor for s in self._window) / count
        best = self.best
        for i, estimator in enumerate(self.estimators):
            mean_heat = sum(s.heats[i] for s in self._window) / count
            x = [mean_heat, -(mean_room - mean_out), 1.0]
            if estimator is best:
                self.bias += BIAS_SMOOTH * (slope - estimator.predict(x) - self.bias)
            estimator.learn(x, slope)
        self.samples += 1
        best_heat = self.best.heat
        if best_heat > 0.3:
            self.heating_samples += 1
        elif best_heat < 0.05:
            self.cooling_samples += 1
        # Every sample overlaps with the next ones: keep only the second half of the window
        while self._window and now - self._window[0].time > WINDOW_SEC / 2:
            self._window.popleft()
        return True

    def simulate(self, room: float, outdoor: float, flow: float | None, valve: float, minutes: float, heat: float | None = None) -> list[float]:
        """Return the room temperature every plan step for a valve held constant."""
        best = self.best
        a, b, c = best.theta
        c += self.bias
        heat = best.heat if heat is None else heat
        step_h = PLAN_STEP_MIN / 60.0
        k = 1.0 - exp(-PLAN_STEP_MIN / best.tau_min)
        temps = []
        for _ in range(int(minutes // PLAN_STEP_MIN)):
            heat += (heat_input(valve, room, flow) - heat) * k
            room += step_h * (a * heat - b * (room - outdoor) + c)
            temps.append(room)
        return temps

    def steady_valve(self, target: float, outdoor: float, flow: float | None) -> float | None:
        """Return the opening that holds the target for good, None when it cannot."""
        a, b, c = self.best.theta
        unit = heat_input(100.0, target, flow)
        if a <= 0 or unit <= 0:
            return None
        need = (b * (target - outdoor) - c) / (a * unit) * 100.0
        return round(_clamp(need, 0.0, 100.0), 1)

    def summary(self, target: float, flow: float | None) -> dict[str, Any]:
        """What the model knows, for the card and the history."""
        best = self.best
        a, b, c = best.theta
        flow = flow if flow is not None else self.flow_mean
        return {
            "ready": self.ready,
            "samples": self.samples,
            "delay_min": best.tau_min,
            "heating_power": round(a, 3),
            "heat_loss": round(b, 4),
            "extra_heat": round(c, 3),
            "fit_k_per_h": None if best.mse is None else round(sqrt(best.mse), 3),
            "curve": {str(int(o)): self.steady_valve(target, o, flow) for o in CURVE_OUTDOOR},
        }

    def reset(self) -> None:
        self.__init__()

    def as_dict(self) -> dict[str, Any]:
        return {
            "estimators": [{"tau_min": e.tau_min, **e.as_dict()} for e in self.estimators],
            "samples": self.samples,
            "heating_samples": self.heating_samples,
            "cooling_samples": self.cooling_samples,
            "flow_mean": self.flow_mean,
        }


class ValvePlanner:
    """Decides the opening of the valves of one room."""

    def __init__(self, model: RoomModel) -> None:
        self.model = model
        self.trim = 0.0
        self.pi_integral: float | None = None
        self.last_valve: float | None = None
        self.last_time: float | None = None
        self.mode = "pi"
        self.trend: deque[tuple[float, float]] = deque()
        self.forecast: float | None = None  # where the PI regulator expects the room, for the history

    def reset(self) -> None:
        self.trim = 0.0
        self.pi_integral = None
        self.last_time = None
        self.trend.clear()
        self.forecast = None

    def slope(self, now: float, room: float) -> float:
        """Return how fast the room changes, in K per hour, from a straight line through the last minutes."""
        self.trend.append((now, room))
        while self.trend and now - self.trend[0][0] > TREND_SEC:
            self.trend.popleft()
        if len(self.trend) < 3 or now - self.trend[0][0] < TREND_MIN_SEC:
            return 0.0
        n = len(self.trend)
        mean_t = sum(t for t, _ in self.trend) / n
        mean_r = sum(r for _, r in self.trend) / n
        var = sum((t - mean_t) ** 2 for t, _ in self.trend)
        if var <= 0:
            return 0.0
        k_per_s = sum((t - mean_t) * (r - mean_r) for t, r in self.trend) / var
        return _clamp(k_per_s * 3600.0, -MAX_SLOPE, MAX_SLOPE)

    def lead_hours(self) -> float:
        """How far the PI regulator looks ahead, from the radiator delay the model found best."""
        best = self.model.best
        tau = best.tau_min if best.mse is not None else 45.0
        return _clamp(LEAD_OF_DELAY * tau / 60.0, LEAD_MIN_H, LEAD_MAX_H)

    def plan(self, now: float, room: float, target: float, outdoor: float, flow: float | None) -> float:
        """Return the wanted opening in percent, before rounding."""
        hours = 0.0 if self.last_time is None else min((now - self.last_time) / 3600.0, 0.5)
        self.last_time = now
        error = target - room
        slope = self.slope(now, room)
        if not self.model.ready:
            self.mode = "pi"
            if self.pi_integral is None:
                self.pi_integral = _clamp(1.5 * (target - outdoor), 5.0, 60.0)
            lead = self.lead_hours()
            ahead = room + slope * lead * (1.0 if slope > 0 else LEAD_FALLING)
            self.forecast = round(ahead, 2)
            ahead_error = target - ahead
            if ahead_error > -0.2:
                # Only the real distance fills the integral, the forecast must not wind it up
                self.pi_integral = _clamp(self.pi_integral + PI_KI * min(error, ahead_error) * hours, 0.0, PI_I_MAX)
            if ahead_error < -0.2 or error < -0.2:
                return 0.0
            return _clamp(PI_KP * ahead_error + self.pi_integral, 0.0, 100.0)
        self.mode = "model"
        self.forecast = None
        self.pi_integral = None
        self.trim = _clamp(self.trim + TRIM_GAIN * error * hours, -TRIM_MAX, TRIM_MAX)
        best, best_cost = 0.0, None
        settle = SETTLE_MIN // PLAN_STEP_MIN
        for step in range(0, 101, int(VALVE_STEP)):
            temps = self.model.simulate(room, outdoor, flow, float(step), HORIZON_MIN)
            cost = 0.0
            for temp in temps[settle:]:
                over = temp - target
                weight = OVERSHOOT_WEIGHT if over > OVERSHOOT_FREE else 1.0
                cost += weight * over * over
            cost += 3.0 * (temps[-1] - target) ** 2
            if self.last_valve is not None:
                cost += MOVE_WEIGHT * (step - self.last_valve) ** 2
            if best_cost is None or cost < best_cost:
                best, best_cost = float(step), cost
        return _clamp(best + self.trim, 0.0, 100.0)

    def command(self, now: float, wanted: float) -> float | None:
        """Return the opening to send now, None when the valve stays where it is."""
        wanted = round_valve(wanted)
        last = self.last_valve
        if last is not None:
            if abs(wanted - last) < VALVE_STEP:
                return None
            since = None if self._sent_at is None else now - self._sent_at
            if wanted != 0.0 and since is not None:
                if since < VALVE_MIN_GAP_SEC:
                    return None
                if abs(wanted - last) < 2 * VALVE_STEP and since < VALVE_SMALL_GAP_SEC:
                    return None  # small corrections wait, every move costs battery
        self.last_valve = wanted
        self._sent_at = now
        return wanted

    _sent_at: float | None = None
