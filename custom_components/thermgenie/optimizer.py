"""Tunes the regulator from finished heating phases. No Home Assistant imports.

Several comparable phases are measured before anything moves, a single step stays small
and the factors on kp and ki are bounded. What the user set stays the base of the
regulation, so going back to manual is always possible. A step that made things
worse is taken back and not tried again for a while.
"""

from dataclasses import dataclass
from statistics import median
from typing import Any

MIN_GAP = 0.5  # K below the target to count as a heating phase
BAND = 0.1  # K around the target that does not count as a swing
SETTLE_SEC = 3 * 3600  # how long the room is watched after reaching the target
MIN_SETTLE_SEC = 3600  # a phase that was cut short before this says nothing
MAX_RISE_SEC = 8 * 3600
MAX_HOURS_PER_K = 24.0

PHASES_PER_STEP = 5
FACTOR_MIN = 0.5
FACTOR_MAX = 2.0
WORSE_BY = 0.05  # a higher score than this over the best one takes a step back
BLOCKED_ROUNDS = 3  # measurements a step that failed is not tried again

OVERSHOOT_HIGH = 0.3  # K
OVERSHOOT_LOW = 0.1  # K
UNDERSHOOT_HIGH = 0.3  # K
SWINGS_HIGH = 2
SLOW_HOURS_PER_K = 3.0

# reason: factor on kp, factor on ki
STEPS = {
    "swinging": (0.9, 0.85),
    "overshoot": (1.0, 0.85),
    "sagging": (1.0, 1.1),
    "slow": (1.1, 1.0),
}


@dataclass
class PhaseObserver:
    """Follows one heating phase from the start until the room has settled at the target."""

    active: bool = False
    start: float = 0.0
    target: float = 0.0
    start_temp: float = 0.0
    reached_at: float | None = None
    peak: float = 0.0
    low: float = 0.0
    side: int = 0
    swings: int = 0

    def abort(self) -> None:
        """Forget the running phase, something from outside spoiled it."""
        self.active = False

    def update(self, now: float, room: float, target: float, clean: bool) -> dict[str, Any] | None:
        """Feed one sample. Returns the phase when it has just finished."""
        if not self.active:
            if clean and target - room >= MIN_GAP:
                self.active = True
                self.start, self.target, self.start_temp = now, target, room
                self.reached_at = None
                self.swings = 0
            return None

        spoiled = not clean or target != self.target
        if self.reached_at is None:
            if spoiled:
                self.active = False
            elif room >= target:
                self.reached_at = now
                self.peak = self.low = room
                self.side = 0
            elif now - self.start > MAX_RISE_SEC:
                self.active = False
                return self._result(now, room)
            return None

        if spoiled:  # what the room did up to here is still worth something
            self.active = False
            return self._result(now, room) if now - self.reached_at >= MIN_SETTLE_SEC else None

        self.peak = max(self.peak, room)
        self.low = min(self.low, room)
        side = 1 if room > self.target + BAND else -1 if room < self.target - BAND else 0
        if side:
            self.swings += self.side == -side
            self.side = side
        if now - self.reached_at < SETTLE_SEC:
            return None
        self.active = False
        return self._result(now, room)

    def _result(self, now: float, room: float) -> dict[str, Any]:
        reached = self.reached_at is not None
        rise = (self.reached_at if reached else now) - self.start
        progress = (self.target if reached else room) - self.start_temp
        return {
            "start": self.start,
            "end": now,
            "target": self.target,
            "reached": reached,
            "overshoot": round(max(0.0, self.peak - self.target), 2) if reached else 0.0,
            "undershoot": round(max(0.0, self.target - self.low), 2) if reached else 0.0,
            "swings": self.swings,
            "hours_per_k": round(min(MAX_HOURS_PER_K, rise / 3600 / max(progress, 0.1)), 2),
        }


def measure(phases: list[dict[str, Any]]) -> dict[str, float]:
    """Sum up phases. The median leaves out the one with the sun on the sensor. A lower score is better."""
    keys = ("overshoot", "undershoot", "swings", "hours_per_k")
    values = {key: round(float(median(phase[key] for phase in phases)), 2) for key in keys}
    score = values["overshoot"] + values["undershoot"] + 0.1 * values["swings"] + 0.05 * values["hours_per_k"]
    return {**values, "score": round(score, 3)}


def advice(values: dict[str, float]) -> str | None:
    """Return what the measurement calls for, None when the regulation is fine."""
    if values["swings"] >= SWINGS_HIGH:
        return "swinging"
    if values["overshoot"] > OVERSHOOT_HIGH:
        return "overshoot"
    if values["undershoot"] > UNDERSHOOT_HIGH:
        return "sagging"
    if values["hours_per_k"] > SLOW_HOURS_PER_K and values["overshoot"] < OVERSHOOT_LOW:
        return "slow"
    return None


def _bounded(factor: float) -> float:
    return round(min(FACTOR_MAX, max(FACTOR_MIN, factor)), 3)


class Optimizer:
    """Keeps the factors on kp and ki and decides about the next step."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        self.kp_factor: float = data.get("kp_factor", 1.0)
        self.ki_factor: float = data.get("ki_factor", 1.0)
        self.best: dict[str, float] | None = data.get("best")
        self.measured: dict[str, float] | None = data.get("measured")
        self.proposal: dict[str, Any] | None = data.get("proposal")
        self.last_step: str | None = data.get("last_step")
        self.blocked: dict[str, int] = dict(data.get("blocked", {}))
        self.phases: list[dict[str, Any]] = list(data.get("phases", []))
        self.history: list[dict[str, Any]] = list(data.get("history", []))
        self.steps: list[dict[str, Any]] = list(data.get("steps", []))
        self.observer = PhaseObserver()

    def add(self, phase: dict[str, Any], apply: bool, now: float) -> dict[str, Any] | None:
        """Take a finished phase. Returns the proposal or the step taken once enough came together."""
        self.phases.append(phase)
        self.history = [*self.history, phase][-50:]
        if len(self.phases) < PHASES_PER_STEP:
            return None
        self.measured = measure(self.phases)
        self.phases = []
        self.blocked = {reason: left - 1 for reason, left in self.blocked.items() if left > 1}
        if apply and self._take_back():
            return self._move("back", self.best["kp_factor"], self.best["ki_factor"], now)

        reason = advice(self.measured)
        kp_step, ki_step = STEPS.get(reason, (1.0, 1.0))
        kp, ki = _bounded(self.kp_factor * kp_step), _bounded(self.ki_factor * ki_step)
        if reason in self.blocked or (kp, ki) == (self.kp_factor, self.ki_factor):
            self.proposal = None
            return None
        if apply:
            return self._move(reason, kp, ki, now)
        self.proposal = {"reason": reason, "kp_factor": kp, "ki_factor": ki}
        return self.proposal

    def _take_back(self) -> bool:
        """Remember the best values so far and return whether the last step should be undone."""
        current = {"kp_factor": self.kp_factor, "ki_factor": self.ki_factor}
        score = self.measured["score"]
        best = self.best
        if best is None or score <= best["score"] or current == {k: best[k] for k in current}:
            self.best = {**current, "score": score}
            return False
        if score <= best["score"] + WORSE_BY:
            return False
        if self.last_step:
            self.blocked[self.last_step] = BLOCKED_ROUNDS
        return True

    def _move(self, reason: str, kp: float, ki: float, now: float) -> dict[str, Any]:
        step = {"at": now, "reason": reason, "kp_factor": kp, "ki_factor": ki, "measured": self.measured}
        self.kp_factor, self.ki_factor = kp, ki
        self.last_step = None if reason == "back" else reason
        self.proposal = None
        self.steps = [*self.steps, step][-20:]
        return step

    def restart(self) -> None:
        """The base of the regulation changed, what was measured before does not count any more."""
        self.observer.abort()
        self.phases = []
        self.best = None
        self.proposal = None
        self.last_step = None

    def reset(self) -> None:
        """Go back to what the user set, the log of the phases stays."""
        self.restart()
        self.kp_factor = self.ki_factor = 1.0
        self.measured = None
        self.blocked = {}
        self.steps = []

    def as_dict(self) -> dict[str, Any]:
        """Return the state to store."""
        return {
            "kp_factor": self.kp_factor,
            "ki_factor": self.ki_factor,
            "best": self.best,
            "measured": self.measured,
            "proposal": self.proposal,
            "last_step": self.last_step,
            "blocked": self.blocked,
            "phases": self.phases,
            "history": self.history,
            "steps": self.steps,
        }
