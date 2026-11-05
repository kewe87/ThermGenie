"""Learns the brake from finished heating phases. No Home Assistant imports.

After each clean heating phase the overshoot adjusts a factor on the D gain, in small
bounded steps and separately per flow temperature range. A wrong measurement can
therefore never move the regulation far.
"""

from dataclasses import dataclass, field
from typing import Any

MIN_START_GAP = 0.3  # K below the target to count as a heating phase
END_DROP = 0.1  # K below the peak ends a phase
MAX_AFTER_REACHED_SEC = 3 * 3600
MAX_PHASE_SEC = 8 * 3600
FACTOR_MIN = 0.25
FACTOR_MAX = 2.5
OVERSHOOT_HIGH = 0.3  # K, brake harder above this
OVERSHOOT_LOW = 0.1  # K, brake less below this
STEP_UP = 1.1
STEP_DOWN = 0.95
NO_FLOW = "unknown"


def flow_bucket(flow: float | None) -> str:
    """Return the flow temperature range. Without a sensor all phases share one range."""
    if flow is None:
        return NO_FLOW
    if flow < 60:
        return "low"
    return "mid" if flow <= 70 else "high"


@dataclass
class PhaseTracker:
    """Follows one heating phase from the start to the peak after the target."""

    active: bool = False
    start: float = 0.0
    target: float = 0.0
    start_temp: float = 0.0
    peak: float = 0.0
    reached_at: float | None = None
    flows: list[float] = field(default_factory=list)

    def update(self, now: float, room: float, target: float, heating: bool, flow: float | None) -> dict[str, Any] | None:
        """Feed one sample. Returns the phase when it has just finished cleanly."""
        if not self.active:
            if heating and target - room >= MIN_START_GAP:
                self.active = True
                self.start, self.target, self.start_temp, self.peak = now, target, room, room
                self.reached_at = None
                self.flows = []
            return None

        if not heating or target != self.target or now - self.start > MAX_PHASE_SEC:
            self.active = False  # window, new setpoint or manual change: not a clean phase
            return None

        if flow is not None and self.reached_at is None:
            self.flows.append(flow)
        self.peak = max(self.peak, room)
        if self.reached_at is None:
            if room >= target:
                self.reached_at = now
            return None
        if room > self.peak - END_DROP and now - self.reached_at < MAX_AFTER_REACHED_SEC:
            return None

        self.active = False
        flow_mean = sum(self.flows) / len(self.flows) if self.flows else None
        rise_hours = max((self.reached_at - self.start) / 3600, 1 / 60)
        return {
            "start": self.start,
            "end": now,
            "target": target,
            "start_temp": self.start_temp,
            "peak": self.peak,
            "overshoot": round(self.peak - target, 2),
            "rise": round((target - self.start_temp) / rise_hours, 2),
            "flow": round(flow_mean, 1) if flow_mean is not None else None,
            "bucket": flow_bucket(flow_mean),
        }


class Learner:
    """Keeps the factor per flow range."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        self.factors: dict[str, float] = dict(data.get("factors", {}))
        self.history: list[dict[str, Any]] = list(data.get("history", []))

    def factor(self, flow: float | None) -> float:
        """Return the factor for the flow right now."""
        return self.factors.get(flow_bucket(flow), 1.0)

    def learn(self, phase: dict[str, Any]) -> None:
        """Apply one finished phase."""
        bucket = phase["bucket"]
        factor = self.factors.get(bucket, 1.0)
        if phase["overshoot"] > OVERSHOOT_HIGH:
            factor *= STEP_UP
        elif phase["overshoot"] < OVERSHOOT_LOW:
            factor *= STEP_DOWN
        self.factors[bucket] = round(min(FACTOR_MAX, max(FACTOR_MIN, factor)), 3)
        self.history = [*self.history, {**phase, "factor": self.factors[bucket]}][-500:]

    def reset(self) -> None:
        """Forget everything that was learned, the phase log stays."""
        self.factors = {}

    def as_dict(self) -> dict[str, Any]:
        """Return the state to store."""
        return {"factors": self.factors, "history": self.history}
