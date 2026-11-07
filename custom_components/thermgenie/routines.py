"""Everyday routines of a thermostat. Each one only runs when its entities are set in the mask."""

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_change
from homeassistant.util import dt as dt_util

from .cascade import CascadeSettings, decide
from .messages import say
from .const import (
    CONF_AIR_COMPARE,
    CONF_AIR_COOL,
    CONF_AIR_FAN,
    CONF_AIR_HEAT,
    CONF_AIR_OFF,
    CONF_AIR_ON,
    CONF_AIR_PERCENT,
    CASCADE_NUMBERS,
    CONF_APPROACH_BELOW,
    CONF_APPROACH_DIRECTION,
    CONF_APPROACH_DISTANCE,
    CONF_APPROACH_TARGET,
    CONF_BOOST_MINUTES,
    CONF_CASCADE_FAN,
    CONF_CASCADE_FELT,
    CONF_CASCADE_FOCUS,
    CONF_CASCADE_FRESH,
    CONF_CASCADE_REAL,
    CONF_CASCADE_START,
    CONF_DRY_DEW,
    CONF_DRY_DEW_BELOW,
    CONF_DRY_HUMIDITY,
    CONF_DRY_HUMIDITY_BELOW,
    CONF_GUARD_BELOW,
    CONF_GUARD_DISTANCE,
    CONF_GUARD_FROM,
    CONF_GUARD_SENSOR,
    CONF_GUARD_ABOVE,
    CONF_GUARD_UNTIL,
    CONF_PRESENCE,
    CONF_SLEEP,
    CONF_WAKE,
    CONF_WAKE_FALLBACK,
    CONF_WAKE_FALLBACK_ENTITY,
    CONF_WAKE_FALLBACK_ON,
    CONF_WAKE_LEAD,
    GUARD_COOLDOWN_SEC,
    GUARD_OFF_SEC,
    HOLD_SEC,
)

_LOGGER = logging.getLogger(__name__)

INVALID = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)
FRESH_SEC = 5400
WOKE_UP_AFTER_SEC = 10800
FAN_STEP = 8


def _clock(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")[:2]
    return int(hour), int(minute)


class Routines:
    """Sleep, wake-up, way home, heat guard, drying limit, boost time and the night cascade."""

    def __init__(self, climate) -> None:
        self.climate = climate
        self.conf = climate.conf
        self.guard_last: float | None = None
        self._guard_since: datetime | None = None
        self._dry_since: datetime | None = None
        self._last_cycle: datetime | None = None
        self._boost_timer = None
        self._boost_until: datetime | None = None
        self._coming = False
        self.air_running = False
        self.off: set[str] = set()  # routines switched off by hand
        self.settings_changed()

    def settings_changed(self) -> None:
        """The mask delivers floats, a fan only takes whole percentages."""
        self._cascade = CascadeSettings(**{field: type(default)(self.conf[key]) for key, (field, default) in CASCADE_NUMBERS.items()})

    def _state(self, key: str):
        entity = self.conf.get(key)
        return self.climate.hass.states.get(entity) if entity else None

    def _number(self, key: str) -> float | None:
        state = self._state(key)
        try:
            return float(state.state)
        except (AttributeError, ValueError):
            return None

    def status(self, now: datetime) -> dict[str, Any]:
        """Tell the card what the routines are up to. A routine that is not set up is left out."""
        status: dict[str, Any] = {}
        if self.conf.get(CONF_SLEEP):
            sleep = self._state(CONF_SLEEP)
            presence = self._state(CONF_PRESENCE)
            if sleep is not None and sleep.state == STATE_ON:
                status["sleep"] = "asleep"
            elif presence is not None and presence.state not in (*INVALID, "home"):
                status["sleep"] = "away"
            else:
                status["sleep"] = "awake"
        if self.conf.get(CONF_WAKE) or self.conf[CONF_WAKE_FALLBACK_ON]:
            alarm = self._alarm(now)
            moment = self._wake_moment(now)
            if moment is not None and not alarm and moment <= now:
                moment += timedelta(days=1)
            status["wake_at"] = moment.isoformat() if moment else None
            status["wake_alarm"] = alarm is not None
        if self.conf.get(CONF_AIR_FAN):
            status["air"] = self.air_running
        if self.conf.get(CONF_APPROACH_DIRECTION) and self.conf.get(CONF_APPROACH_DISTANCE):
            status["way_home"] = self._coming
        if self._boost_until is not None:
            status["boost_until"] = self._boost_until.isoformat()
        if self.conf.get(CONF_GUARD_SENSOR):
            status["guard"] = True
        if self.conf.get(CONF_CASCADE_FOCUS) and self.conf.get(CONF_CASCADE_FAN):
            status["cascade"] = True
        if self.conf.get(CONF_DRY_DEW) or self.conf.get(CONF_DRY_HUMIDITY):
            status["dry"] = True
        return status

    async def async_set_enabled(self, routine: str, enabled: bool) -> None:
        """Switch a routine. A sleep routine that comes back catches up at once."""
        if enabled:
            self.off.discard(routine)
            if routine == "sleep":
                await self.async_apply_sleep()
        else:
            self.off.add(routine)

    def start(self) -> None:
        """Start listening."""
        watch = self.climate.async_on_remove
        hass = self.climate.hass
        people = [self.conf[k] for k in (CONF_SLEEP, CONF_PRESENCE) if self.conf.get(k)]
        if self.conf.get(CONF_SLEEP) and people:
            watch(async_track_state_change_event(hass, people, self._on_sleep))
        way = [self.conf[k] for k in (CONF_APPROACH_DIRECTION, CONF_APPROACH_DISTANCE) if self.conf.get(k)]
        if len(way) == 2:
            watch(async_track_state_change_event(hass, way, self._on_way_home))
        if self.conf.get(CONF_CASCADE_FOCUS) and self.conf.get(CONF_CASCADE_FAN):
            watch(async_track_state_change_event(hass, [self.conf[CONF_CASCADE_FOCUS]], self._on_focus))
            watch(async_track_time_change(hass, self._on_cascade_tick, minute=list(range(0, 60, 5)), second=0))
        wake = [self.conf[k] for k in (CONF_WAKE, CONF_WAKE_FALLBACK_ENTITY) if self.conf.get(k)]
        if wake:
            watch(async_track_state_change_event(hass, wake, self._on_wake))
        watch(self._cancel_boost)

    # Sleep and presence

    def _sleep_preset(self) -> str | None:
        """Return eco while asleep or away, comfort otherwise, None if the state is unknown."""
        if not self.conf.get(CONF_SLEEP):
            return None
        sleep = self._state(CONF_SLEEP)
        presence = self._state(CONF_PRESENCE)
        if (sleep and sleep.state in INVALID) or (presence and presence.state in INVALID):
            return None
        away = presence is not None and presence.state != "home"
        return "eco" if (sleep is not None and sleep.state == STATE_ON) or away else "comfort"

    async def async_apply_sleep(self) -> None:
        """Follow sleep and presence while the heating settings are in use."""
        if "sleep" in self.off or self.climate.profile != "heat":
            return
        preset = self._sleep_preset()
        if preset and preset != self.climate.active_preset:
            await self.climate.async_set_preset_mode(preset)

    @callback
    def _on_sleep(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        old = event.data["old_state"]
        if new is None or new.state in INVALID:
            return
        if old is None or old.state in INVALID:
            # After a restart a manually set temperature survives the sensors coming back
            if self.climate.active_preset == "none":
                return
        # A new position or a move between two zones changes nothing about being home or asleep
        elif (old.state in (STATE_ON, "home")) == (new.state in (STATE_ON, "home")):
            return
        self.climate.hass.async_create_task(self.async_apply_sleep())

    # Way home

    @callback
    def _on_way_home(self, event: Event[EventStateChangedData]) -> None:
        self.climate.hass.async_create_task(self._async_way_home())

    async def _async_way_home(self) -> None:
        direction = self._state(CONF_APPROACH_DIRECTION)
        distance = self._number(CONF_APPROACH_DISTANCE)
        presence = self._state(CONF_PRESENCE)
        coming = (
            direction is not None
            and direction.state == "towards"
            and distance is not None
            and distance < self.conf[CONF_APPROACH_BELOW]
            and presence is not None
            and presence.state == "not_home"
        )
        # Only on the way in, so a setpoint changed by hand on the road stays
        started = coming and not self._coming
        self._coming = coming
        if started and "way_home" not in self.off and HVACMode.HEAT in self.climate.hvac_modes and not self.climate.lock.enabled:
            await self.climate.async_apply_target(temperature=self.conf[CONF_APPROACH_TARGET], hvac_mode=HVACMode.HEAT)

    # Boost time

    @callback
    def _cancel_boost(self) -> None:
        if self._boost_timer:
            self._boost_timer()
            self._boost_timer = None
        self._boost_until = None

    @callback
    def preset_changed(self, preset: str) -> None:
        """Let a boost fall back to comfort after its time."""
        self._cancel_boost()
        minutes = self.conf[CONF_BOOST_MINUTES]
        if preset != "boost" or not minutes:
            return

        @callback
        def _done(_now: datetime) -> None:
            self._boost_timer = None
            self._boost_until = None
            if self.climate.active_preset == "boost":
                self.climate.hass.async_create_task(self.climate.async_set_preset_mode("comfort"))

        self._boost_timer = async_call_later(self.climate.hass, minutes * 60, _done)
        self._boost_until = dt_util.utcnow() + timedelta(minutes=minutes)

    # Every cycle

    async def async_cycle(self, now: datetime) -> None:
        """Run the routines that look at the clock or at how long something has lasted."""
        await self._async_wake_up(now)
        await self._async_heat_guard(now)
        await self._async_dry_limit(now)
        await self._async_air()
        self._last_cycle = now

    @callback
    def _on_wake(self, _event: Event) -> None:
        """Show a changed alarm right away, the cycle may be minutes off."""
        self.climate.async_write_ha_state()

    def _alarm(self, now: datetime) -> datetime | None:
        """Return the alarm if it still lies ahead."""
        state = self._state(CONF_WAKE)
        stamp = state.attributes.get("timestamp") if state else None
        wake = dt_util.utc_from_timestamp(stamp) if stamp else None
        return wake if wake is not None and wake > now else None

    def _fixed_clock(self) -> tuple[int, int]:
        """Return the fixed wake-up time: from its entity if it has a usable one, else from the settings."""
        state = self._state(CONF_WAKE_FALLBACK_ENTITY)
        if state is not None and state.state not in INVALID:
            if "hour" in state.attributes and "minute" in state.attributes:
                return int(state.attributes["hour"]), int(state.attributes["minute"])
            moment = dt_util.parse_datetime(state.state)
            if moment is not None:
                local = dt_util.as_local(moment)
                return local.hour, local.minute
            clock = dt_util.parse_time(state.state)
            if clock is not None:
                return clock.hour, clock.minute
        return _clock(self.conf[CONF_WAKE_FALLBACK])

    def _wake_moment(self, now: datetime) -> datetime | None:
        """Return when to heat up: ahead of a future alarm, else at the fixed time if that is wanted."""
        alarm = self._alarm(now)
        if alarm is not None:
            return alarm - timedelta(minutes=self.conf[CONF_WAKE_LEAD])
        if not self.conf[CONF_WAKE_FALLBACK_ON]:
            return None
        hour, minute = self._fixed_clock()
        local = dt_util.as_local(now)
        moment = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # An alarm that already rang today stands for this morning
        state = self._state(CONF_WAKE)
        stamp = state.attributes.get("timestamp") if state else None
        if stamp and dt_util.as_local(dt_util.utc_from_timestamp(stamp)).date() == local.date():
            moment += timedelta(days=1)
        return moment

    async def _async_wake_up(self, now: datetime) -> None:
        """Heat up before the alarm, without a future alarm at the fixed time if that is wanted."""
        if "wake" in self.off or self.climate.profile != "heat" or self._last_cycle is None:
            return
        moment = self._wake_moment(now)
        if moment is not None and self._last_cycle < moment <= now and self.climate.active_preset != "comfort":
            await self.climate.async_set_preset_mode("comfort")

    # Moving the air

    def _air_wanted(self) -> bool:
        """Run while the room works in a wanted direction and, if a second sensor is set, the air is uneven."""
        action = self.climate.hvac_action
        if not ((action == HVACAction.HEATING and self.conf[CONF_AIR_HEAT]) or (action == HVACAction.COOLING and self.conf[CONF_AIR_COOL])):
            return False
        if not self.conf.get(CONF_AIR_COMPARE):
            return True
        other = self._number(CONF_AIR_COMPARE)
        room = self.climate.real_temperature()
        if other is None or room is None:
            return False
        return abs(other - room) >= self.conf[CONF_AIR_OFF if self.air_running else CONF_AIR_ON]

    async def _async_air(self) -> None:
        """Only a fan started here is stopped here, one switched on by hand stays as it is."""
        entity = self.conf.get(CONF_AIR_FAN)
        fan = self._state(CONF_AIR_FAN)
        if not entity or fan is None or fan.state in INVALID:
            return
        # The night cascade has this fan to itself while it runs
        if entity == self.conf.get(CONF_CASCADE_FAN) and "cascade" not in self.off and (focus := self._state(CONF_CASCADE_FOCUS)) and focus.state == STATE_ON:
            return
        wanted = "air" not in self.off and self._air_wanted()
        if wanted and not self.air_running and fan.state != STATE_ON:
            self.air_running = True
            await self.climate.hass.services.async_call("fan", "turn_on", {"entity_id": entity, "percentage": int(self.conf[CONF_AIR_PERCENT])}, blocking=False)
            self.climate.async_write_ha_state()
        elif not wanted and self.air_running:
            self.air_running = False
            await self.climate.hass.services.async_call("fan", "turn_off", {"entity_id": entity}, blocking=False)
            self.climate.async_write_ha_state()

    def _held(self, since: datetime | None, condition: bool, now: datetime) -> datetime | None:
        if not condition:
            return None
        return since or now

    async def _async_heat_guard(self, now: datetime) -> None:
        """Keep the home from heating up while nobody is there and forgot the air conditioner."""
        if "guard" in self.off:
            self._guard_since = None
            return
        felt = self._number(CONF_GUARD_SENSOR)
        self._guard_since = self._held(self._guard_since, felt is not None and felt > self.conf[CONF_GUARD_ABOVE], now)
        if self._guard_since is None or (now - self._guard_since).total_seconds() < HOLD_SEC:
            return
        presence = self._state(CONF_PRESENCE)
        distance = self._number(CONF_GUARD_DISTANCE)
        if presence is None or presence.state != "not_home" or (now - presence.last_changed).total_seconds() < HOLD_SEC:
            return
        if distance is None or distance >= self.conf[CONF_GUARD_BELOW]:
            return
        if not (self.climate.profile == "cool" or self.climate.warm_outside) or self.climate.hvac_mode != HVACMode.OFF or self.climate.window_is_open():
            return
        if (now - self.climate.mode_since).total_seconds() < GUARD_OFF_SEC:
            return
        local = dt_util.as_local(now)
        start_h, start_m = _clock(self.conf[CONF_GUARD_FROM])
        end_h, end_m = _clock(self.conf[CONF_GUARD_UNTIL])
        if not (start_h, start_m) <= (local.hour, local.minute) < (end_h, end_m):
            return
        if self.guard_last is not None and now.timestamp() - self.guard_last < GUARD_COOLDOWN_SEC:
            return

        hass = self.climate.hass
        self.guard_last = now.timestamp()
        await self.climate.async_set_hvac_mode(HVACMode.COOL)
        await self.climate.async_set_preset_mode("eco")
        target = self.climate.active_target
        await self.climate.async_log(say(hass, "guard_log", felt=felt, target=target))
        if self.climate.role_is_running("cool"):
            await self.climate.async_notify(
                say(hass, "guard_title"),
                say(hass, "guard_body", felt=felt, target=target),
            )
        else:
            await self.climate.async_notify(
                say(hass, "guard_failed_title"),
                say(hass, "guard_failed_body", felt=felt),
                "time-sensitive",
            )

    async def _async_dry_limit(self, now: datetime) -> None:
        """Stop drying before the air gets too dry."""
        if "dry" in self.off:
            self._dry_since = None
            return
        dew = self._number(CONF_DRY_DEW)
        humidity = self._number(CONF_DRY_HUMIDITY)
        too_dry = (dew is not None and dew < self.conf[CONF_DRY_DEW_BELOW]) or (humidity is not None and humidity < self.conf[CONF_DRY_HUMIDITY_BELOW])
        self._dry_since = self._held(self._dry_since, self.climate.hvac_mode == HVACMode.DRY and too_dry, now)
        if self._dry_since is None or (now - self._dry_since).total_seconds() < HOLD_SEC:
            return
        self._dry_since = None
        await self.climate.async_set_hvac_mode(HVACMode.OFF)
        message = say(self.climate.hass, "dry_body", dew=dew, humidity=humidity)
        await self.climate.async_log(message)
        await self.climate.async_notify(say(self.climate.hass, "dry_title"), message)

    # Night cascade

    @callback
    def _on_focus(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        old = event.data["old_state"]
        if new is None or old is None or "cascade" in self.off:
            return
        if new.state == STATE_ON:
            self.climate.hass.async_create_task(self._async_cascade(dt_util.now()))
        elif new.state == "off" and old.state == STATE_ON and (new.last_changed - old.last_changed).total_seconds() > WOKE_UP_AFTER_SEC:
            self.climate.hass.async_create_task(self._async_woke_up((new.last_changed - old.last_changed).total_seconds() / 3600))

    @callback
    def _on_cascade_tick(self, now: datetime) -> None:
        self.climate.hass.async_create_task(self._async_cascade(now))

    async def _async_call_fan(self, service: str, **data: Any) -> None:
        await self.climate.hass.services.async_call("fan", service, {"entity_id": self.conf[CONF_CASCADE_FAN], **data}, blocking=False)

    async def _async_woke_up(self, hours: float) -> None:
        """Hand the room back in the morning. This must not touch a running heating."""
        if self.climate.hvac_mode != HVACMode.HEAT:
            await self.climate.async_cool_target(self.conf["cool_comfort"], "comfort")
            await self.climate.async_set_hvac_mode(HVACMode.OFF)
        await self._async_call_fan("turn_off")
        hass = self.climate.hass
        await self.climate.async_log(say(hass, "woke_up", hours=f"{hours:.1f}"), name=say(hass, "cascade_name"))

    def _fresh(self, now: datetime) -> bool:
        """At least one of the room sensors has to be alive, else nothing is moved."""
        for entity in self.conf.get(CONF_CASCADE_FRESH) or [self.conf.get(CONF_CASCADE_REAL)]:
            state = self.climate.hass.states.get(entity) if entity else None
            if state and state.state not in INVALID and (now - state.last_reported).total_seconds() < FRESH_SEC:
                return True
        return False

    def _sleep_hours(self, now: datetime, focus) -> float:
        start = self._state(CONF_CASCADE_START)
        stamp = start.attributes.get("timestamp") if start else None
        if stamp is not None and 0 <= (hours := (now.timestamp() - stamp) / 3600) < 16:
            return round(hours, 3)
        return round((now - focus.last_changed).total_seconds() / 3600, 3)

    async def _async_cascade(self, now: datetime) -> None:
        if "cascade" in self.off:
            return
        focus = self._state(CONF_CASCADE_FOCUS)
        fan = self._state(CONF_CASCADE_FAN)
        presence = self._state(CONF_PRESENCE)
        if focus is None or focus.state != STATE_ON or fan is None or fan.state != STATE_ON:
            return
        if presence is None or presence.state != "home" or not self._fresh(now):
            return
        hours = self._sleep_hours(now, focus)
        felt = self._number(CONF_CASCADE_FELT)
        real = self._number(CONF_CASCADE_REAL)
        felt = 23.0 if felt is None else felt
        real = 23.0 if real is None else real
        fan_now = int(fan.attributes.get("percentage") or 0)
        target = self.climate.cool_target
        # Unknown counts as open: that is the safe direction, it locks the outer loop
        window = self.climate.hass.states.get(self.climate.window_entity) if self.climate.window_entity else None
        window_open = window is not None and window.state != "off"
        cooling = self.climate.hvac_mode == HVACMode.COOL
        result = decide(self._cascade, hours, felt, real, target, fan_now, self.conf["cool_comfort"], window_open, cooling)

        hass = self.climate.hass
        name = say(hass, "cascade_name")
        extra = say(hass, "cascade_cold") if result.cold else (say(hass, "cascade_hot") if result.hot else "")
        await self.climate.async_log(
            say(
                hass,
                "cascade_log",
                scenario=result.scenario,
                felt=felt,
                real=real,
                base=result.base,
                gap=result.gap,
                demand=result.demand,
                cap=result.cap,
                floor=result.floor,
                fan_now=fan_now,
                fan=result.fan,
                extra=extra,
                target=target,
                hours=f"{hours:.1f}",
            ),
            name=name,
        )
        if abs(result.fan - fan_now) >= FAN_STEP:
            await self._async_call_fan("set_percentage", percentage=result.fan)
        # The air conditioner is the slow actuator, it is only moved every 15 minutes
        if result.target is not None and dt_util.as_local(now).minute % 15 == 0:
            await self.climate.async_cool_target(result.target)
            await self.climate.async_log(say(hass, "cascade_target", target=target, new=result.target, demand=result.demand, cap=result.cap, lower=result.lower_limit), name=name)
