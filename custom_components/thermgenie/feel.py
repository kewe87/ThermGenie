"""Thermal Wellbeing: the room follows how people feel instead of a number. No Home Assistant imports.

People say how they feel: cold, a bit cool, comfortable, a bit warm, hot. Every
answer is kept with the time of day, the weekday, the outdoor temperature and the
preset that was running, as how far the right temperature lay from that preset.
The target for now is the preset plus the weighted mean of those differences:
answers at a similar hour, in similar weather and under the same preset count
most, old answers fade, so without answers the room slowly goes back to the
preset. On top sits the form of the day: what was said today counts at once and
fades out over a few hours.

After each change the thermostat asks again once the room got there, until the
answers settle and there is nothing left to ask.

Which way the room is going right now is told as a tendency, never as a number.
"""

from dataclasses import dataclass
from math import exp
from typing import Any

FEELINGS = ("cold", "cool", "good", "warm", "hot")
STEP = {"cold": 1.0, "cool": 0.5, "good": 0.0, "warm": -0.5, "hot": -1.0}  # K the room should change
HOUR_WIDTH = 1.5  # h, answers this far from now count about half
OUTDOOR_WIDTH = 6.0  # K
OTHER_PRESET = 0.3  # an answer under another preset still says a little
OTHER_DAY = 0.6  # weekday against weekend
HALF_LIFE_DAYS = 30.0  # without answers the learned difference fades back to the preset
PRIOR_WEIGHT = 0.6  # the preset itself counts like this many answers
DAY_FORM_HOURS = 4.0
DAY_FORM_MAX = 2.0
MAX_DIFF = 4.0  # K a learned temperature may lie away from its preset
MAX_ANSWERS = 400
LOW, HIGH = 5.0, 30.0
ASK_AFTER_MIN = 60  # ask again this long after the room reached its new target
ASK_TIMEOUT_MIN = 180  # or at the latest this long after a change
SETTLED_ANSWERS = 3  # this many matching answers around an hour and the asking stops there
SOFT = 0.4  # a setpoint changed by hand counts this much of an answer
TENDENCY_BAND = 0.45  # K, a room this far from its target is warming or cooling
TENDENCY_KEEP = 0.15  # K, and keeps doing so until this close, so a sensor flickering by 0.1 K does not flip it
SHOW_MIN_SEC = 15 * 60  # the face of an answer stays at least this long, then until the room got there
SHOW_MAX_SEC = 2 * 3600  # no further word means it fits: the face goes neutral after this at the latest
CORRECTION_SEC = 120  # an answer this soon after the last one corrects it instead of adding to it
# The outlook: what the answers so far say about the times of the day, in words
SLOTS = (("morning", 7.5), ("midday", 12.5), ("evening", 19.0), ("night", 22.5))
LEAN_SAME = 0.25  # K, closer to the preset than this is as set
LEAN_CLEAR = 0.75  # K, from here on clearly warmer or cooler
SUPPORT = ((2.5, "high"), (1.0, "medium"), (0.3, "low"))  # weight of the answers behind a slot
# An answer far from what was learned is asked about: was there something special?
UNUSUAL_K = 1.0  # K between the answer and what was learned for this moment
UNUSUAL_SUPPORT = 1.0  # only once enough answers speak for this moment
CHECK_SEC = 30 * 60  # the reason may come this long after the answer
# Reasons that make an answer not count for later; unwell and guests still count for today
REASONS = ("sport", "unwell", "guests", "arrived", "window", "other")
KEEP_TODAY = ("unwell", "guests")  # count for today, and later answers until the next morning are taken the same way
NEXT_MORNING = 4.0  # o'clock: a visit or a cold lasts until then


@dataclass
class Answer:
    time: float  # unix seconds
    hour: float  # local hour of the day
    weekend: bool
    outdoor: float | None
    preset: str
    diff: float  # right temperature minus the preset
    weight: float = 1.0
    reason: str | None = None  # something special: the answer does not count for later

    def as_dict(self) -> dict[str, Any]:
        data = {"t": round(self.time), "h": round(self.hour, 2), "we": self.weekend, "o": self.outdoor, "p": self.preset, "d": round(self.diff, 2), "w": self.weight}
        if self.reason:
            data["r"] = self.reason
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Answer":
        return cls(data["t"], data["h"], data.get("we", False), data.get("o"), data.get("p", "comfort"), data["d"], data.get("w", 1.0), data.get("r"))


@dataclass
class Moment:
    """When something is asked or answered."""

    now: float
    hour: float
    weekend: bool
    outdoor: float | None
    preset: str
    base: float  # the temperature of the preset


def _hour_distance(a: float, b: float) -> float:
    d = abs(a - b) % 24
    return min(d, 24 - d)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def tendency(room: float | None, target: float | None, active: bool, previous: str = "holding") -> str:
    """Return warming, cooling or holding, as the card and the matrix show it."""
    if room is None or target is None or not active:
        return "holding"
    gap = target - room
    if gap > (TENDENCY_KEEP if previous == "warming" else TENDENCY_BAND):
        return "warming"
    if -gap > (TENDENCY_KEEP if previous == "cooling" else TENDENCY_BAND):
        return "cooling"
    return "holding"


def _lean(diff: float) -> str:
    if abs(diff) < LEAN_SAME:
        return "same"
    side = "warmer" if diff > 0 else "cooler"
    return f"{side}_clear" if abs(diff) >= LEAN_CLEAR else side


class FeelLearner:
    """Learns what feels right in one room."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        self.answers = [Answer.from_dict(a) for a in data.get("answers", [])]
        self.day_form = float(data.get("day_form", 0.0))
        self.day_form_at: float | None = data.get("day_form_at")
        self.ask_at: float | None = data.get("ask_at")
        self.last_feeling: str | None = data.get("last_feeling")
        self.last_at: float | None = data.get("last_at")
        self.pending: bool = data.get("pending", False)  # the room is still on its way to where the last answer sent it
        self.checking: dict[str, Any] | None = data.get("checking")  # an unusual answer waits for its reason
        self.special: str | None = data.get("special")  # guests or unwell: answers until special_until count for today only
        self.special_until: float | None = data.get("special_until")

    def _weight(self, answer: Answer, m: Moment) -> float:
        w = answer.weight * exp(-0.5 * (_hour_distance(answer.hour, m.hour) / HOUR_WIDTH) ** 2)
        if m.outdoor is not None and answer.outdoor is not None:
            w *= exp(-0.5 * ((answer.outdoor - m.outdoor) / OUTDOOR_WIDTH) ** 2)
        if answer.weekend != m.weekend:
            w *= OTHER_DAY
        if answer.preset != m.preset:
            w *= OTHER_PRESET
        age_days = max(m.now - answer.time, 0.0) / 86400
        return w * 0.5 ** (age_days / HALF_LIFE_DAYS)

    def learned_diff(self, m: Moment) -> float:
        """Return how far the right temperature lies from the preset, without the form of the day."""
        total, weight = 0.0, PRIOR_WEIGHT
        for answer in self.answers:
            w = self._weight(answer, m)
            total += w * answer.diff
            weight += w
        return _clamp(total / weight, -MAX_DIFF, MAX_DIFF)

    def form(self, now: float) -> float:
        """Return what today's answers still add, fading out."""
        if not self.day_form or self.day_form_at is None:
            return 0.0
        hours = max(now - self.day_form_at, 0.0) / 3600
        return self.day_form * exp(-hours / DAY_FORM_HOURS)

    def support(self, m: Moment) -> float:
        """Return how many answers, weighted, speak for this moment."""
        return sum(self._weight(answer, m) for answer in self.answers)

    def outlook(self, m: Moment) -> dict[str, Any]:
        """What was learned so far, per time of the day and for today, without a single temperature."""
        slots = []
        for name, hour in SLOTS:
            at = Moment(m.now, hour, m.weekend, m.outdoor, m.preset, m.base)
            support = self.support(at)
            confidence = next((level for limit, level in SUPPORT if support >= limit), "none")
            slots.append({
                "slot": name,
                "lean": _lean(self.learned_diff(at)) if confidence != "none" else "open",
                "confidence": confidence,
                "settled": self.settled(hour),
                "now": min(SLOTS, key=lambda s: _hour_distance(s[1], m.hour))[0] == name,
            })
        form = self.form(m.now)
        return {"slots": slots, "today": _lean(form) if abs(form) >= LEAN_SAME else None}

    def target(self, m: Moment) -> float:
        """Return the temperature the room should have now, in half degrees."""
        value = m.base + self.learned_diff(m) + self.form(m.now)
        return round(_clamp(value, LOW, HIGH) * 2) / 2

    def feel(self, feeling: str, room: float | None, current: float, m: Moment, special: str | None = None) -> float:
        """Take an answer and return the new target. A special moment (an open window) is kept but not learned."""
        if feeling not in STEP:
            raise ValueError(feeling)
        # What was felt is the room as it is, unless it is still far from where it is going
        felt = current if room is None or abs(room - current) > 1.0 else room
        right = _clamp(felt + STEP[feeling], LOW, HIGH)
        if special:
            self._remember(Answer(m.now, m.hour, m.weekend, m.outdoor, m.preset, right - m.base, 0.0, special))
            self.checking = None
            return self.target(m)
        if self.special and self.special_until and m.now < self.special_until:
            # During a visit the answers act on the room but are not learned
            self._take(right, m)
            self.answers[-1].weight, self.answers[-1].reason = 0.0, self.special
            self.checking = None
            self.last_feeling, self.last_at = feeling, m.now
            self.pending = feeling != "good"
            self.ask_at = None
            return self.target(m)
        learned = m.base + self.learned_diff(m)
        unusual = self.support(m) >= UNUSUAL_SUPPORT and abs(right - learned) >= UNUSUAL_K
        before = {"form": self.day_form, "form_at": self.day_form_at}
        self._take(right, m)
        self.checking = {"at": m.now, **before} if unusual else None
        self.last_feeling, self.last_at = feeling, m.now
        self.pending = feeling != "good"
        self.ask_at = None if feeling == "good" and self.settled(m.hour) else m.now
        return self.target(m)

    def explain(self, reason: str, m: Moment) -> bool:
        """The reason for an unusual answer: normal keeps it, anything else takes it out of what is learned."""
        check = self.checking
        self.checking = None
        if reason == "normal":
            self.special = self.special_until = None  # the visit is over
        if check is None or m.now - check["at"] > CHECK_SEC or not self.answers or self.answers[-1].time != check["at"]:
            return False
        if reason == "normal":
            return True
        answer = self.answers[-1]
        answer.weight, answer.reason = 0.0, reason
        if reason in KEEP_TODAY:
            self.special = reason
            self.special_until = m.now + ((NEXT_MORNING - m.hour) % 24 or 24) * 3600
        else:
            self.day_form, self.day_form_at = check["form"], check["form_at"]
            self.pending = False
        return True

    def end_special(self) -> None:
        self.special = self.special_until = None

    def exceptions(self, count: int = 5) -> list[dict[str, Any]]:
        """The last answers that do not count, with their reason."""
        return [{"reason": a.reason, "at": a.time} for a in self.answers if a.reason][-count:][::-1]

    def told(self, target: float, m: Moment) -> float:
        """A number said in Thermal Wellbeing counts like a feeling that leads there."""
        self._take(_clamp(target, LOW, HIGH), m)
        self.last_at = m.now
        self.pending = False
        self.ask_at = m.now
        return self.target(m)

    def _take(self, right: float, m: Moment) -> None:
        last = self.answers[-1] if self.answers else None
        if last is not None and last.weight == 1.0 and 0 <= m.now - last.time < CORRECTION_SEC:
            # A second tap right after the first one means the first was wrong
            self.answers.pop()
        self._remember(Answer(m.now, m.hour, m.weekend, m.outdoor, m.preset, right - m.base))
        # Today counts at once: the target goes where it was asked, the rest fades
        self.day_form = _clamp(right - m.base - self.learned_diff(m), -DAY_FORM_MAX, DAY_FORM_MAX)
        self.day_form_at = m.now

    def hand_set(self, target: float, m: Moment) -> None:
        """A setpoint changed by hand in the thermostat mode says a little about what feels right."""
        self._remember(Answer(m.now, m.hour, m.weekend, m.outdoor, m.preset, _clamp(target, LOW, HIGH) - m.base, SOFT))

    def _remember(self, answer: Answer) -> None:
        self.answers.append(answer)
        del self.answers[:-MAX_ANSWERS]

    def settled(self, hour: float) -> bool:
        """Return whether the last real answers around this hour agree."""
        near = [a for a in self.answers if a.weight == 1.0 and _hour_distance(a.hour, hour) <= HOUR_WIDTH]
        recent = near[-SETTLED_ANSWERS:]
        return len(recent) == SETTLED_ANSWERS and all(abs(a.diff - recent[-1].diff) <= 0.25 for a in recent)

    def due(self, now: float, reached_since: float | None) -> bool:
        """Return whether it is time to ask how it feels now."""
        if self.ask_at is None:
            return False
        if (now - self.ask_at) / 60 > ASK_TIMEOUT_MIN:
            return True
        return reached_since is not None and reached_since >= self.ask_at and (now - reached_since) / 60 >= ASK_AFTER_MIN

    def arrived(self, now: float, done: bool = True) -> bool:
        """The room got where the last answer sent it, or nothing more can be done, or no further word came:
        the face goes back to neutral. Return whether it changed."""
        if not self.pending or self.last_at is None or now - self.last_at < SHOW_MIN_SEC:
            return False
        if not done and now - self.last_at < SHOW_MAX_SEC:
            return False
        self.pending = False
        return True

    def showing(self) -> str | None:
        """Return the feeling the card shows: the last answer while the room still acts on it."""
        return self.last_feeling if self.pending else None

    def asked(self) -> None:
        self.ask_at = None

    def status(self, m: Moment) -> dict[str, Any]:
        """What the card may show: no temperatures, only how much was learned."""
        return {
            "answers": sum(1 for a in self.answers if a.weight == 1.0),
            "last_feeling": self.last_feeling,
            "last_at": self.last_at,
            "showing": self.showing(),
            "asking": self.ask_at is not None,
            "outlook": self.outlook(m),
            "checking": self.checking is not None and m.now - self.checking["at"] <= CHECK_SEC,
            "exceptions": self.exceptions(),
            "special": self.special if self.special_until and m.now < self.special_until else None,
        }

    def reset(self) -> None:
        self.__init__()

    def as_dict(self) -> dict[str, Any]:
        return {
            "answers": [a.as_dict() for a in self.answers],
            "day_form": round(self.day_form, 3),
            "day_form_at": self.day_form_at,
            "ask_at": self.ask_at,
            "last_feeling": self.last_feeling,
            "last_at": self.last_at,
            "pending": self.pending,
            "checking": self.checking,
            "special": self.special,
            "special_until": self.special_until,
        }
