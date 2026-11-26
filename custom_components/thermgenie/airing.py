"""How fast a room may warm up again after airing, learned from what happened the last times."""
from __future__ import annotations

from typing import Any

from .const import AIRING_RISE_K_PER_H

RATE_MIN = 0.4  # K per hour
RATE_MAX = 2.0
WATCH_SEC = 90 * 60  # the radiators' afterglow shows within this time after arriving
OVERSHOOT_TOO_MUCH = 0.3  # K beyond the target: next time slower
OVERSHOOT_NONE = 0.1  # K: it could have been a little faster
SLOWER = 0.8
FASTER = 1.1


class AiringLearner:
    """Learns the rise after airing: slower when the room overshot, a little faster when it did not."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        self.rate = float(data.get("rate", AIRING_RISE_K_PER_H))
        self.count = int(data.get("count", 0))
        self.last_overshoot: float | None = data.get("last_overshoot")
        self.watch: dict[str, float] | None = None

    def arrived(self, now: float, target: float, room: float) -> None:
        """The ramp reached the target: watch how far the afterglow carries the room."""
        self.watch = {"until": now + WATCH_SEC, "target": target, "peak": room}

    def cancel(self) -> None:
        """A window or a new setpoint spoils the measurement."""
        self.watch = None

    def observe(self, now: float, room: float | None, target: float) -> bool:
        """Follow the room after arriving; return True when the rate was learned anew."""
        watch = self.watch
        if watch is None:
            return False
        if target != watch["target"]:
            self.watch = None
            return False
        if room is not None:
            watch["peak"] = max(watch["peak"], room)
        if now < watch["until"]:
            return False
        self.watch = None
        overshoot = round(watch["peak"] - watch["target"], 2)
        self.last_overshoot = overshoot
        self.count += 1
        if overshoot > OVERSHOOT_TOO_MUCH:
            self.rate = max(RATE_MIN, self.rate * SLOWER)
        elif overshoot < OVERSHOOT_NONE:
            self.rate = min(RATE_MAX, self.rate * FASTER)
        self.rate = round(self.rate, 3)
        return True

    def reset(self) -> None:
        self.rate, self.count, self.last_overshoot, self.watch = AIRING_RISE_K_PER_H, 0, None, None

    def as_dict(self) -> dict[str, Any]:
        return {"rate": self.rate, "count": self.count, "last_overshoot": self.last_overshoot}
