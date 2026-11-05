"""Heating lock: a room that must not heat, and only frost breaks the lock."""

import asyncio
from datetime import datetime
import logging

from homeassistant.components.climate import HVACMode
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .messages import say
from .valves import valve_position
from .const import CONF_LOCK, CONF_LOCK_FROST_OFF, CONF_LOCK_FROST_ON, CONF_LOCK_WAIT, CONF_VALVES

_LOGGER = logging.getLogger(__name__)


class HeatLock:
    """Switches the heating off again at once. Below the frost limit the lock is set aside until the room is warmer."""

    def __init__(self, climate) -> None:
        self.climate = climate
        self.conf = climate.conf
        self.frost_active = False
        self._frost_ended: datetime | None = None
        self._task: asyncio.Task | None = None
        self._closed = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return bool(self.conf.get(CONF_LOCK))

    def start(self) -> None:
        """Watch the valve, if the room has one that reports."""
        if not self.enabled:
            return
        self.climate.async_on_remove(self._cancel)
        if valves := list(self.conf.get(CONF_VALVES, {}).values()):
            self.climate.async_on_remove(async_track_state_change_event(self.climate.hass, valves, self._on_valve))

    @callback
    def _cancel(self) -> None:
        if self._task:
            self._task.cancel()

    @callback
    def _on_valve(self, event: Event[EventStateChangedData]) -> None:
        if self._valve() == 0:
            self._closed.set()
        self.climate.hass.async_create_task(self.check())

    def _valve(self) -> float | None:
        """Return how far the room is open: the widest valve, None if none of them reports."""
        positions = [valve_position(self.climate.hass, entity) for entity in self.conf.get(CONF_VALVES, {}).values()]
        return max((p for p in positions if p is not None), default=None)

    @property
    def _running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _async_update_frost(self) -> None:
        """Set the lock aside at the frost limit and back on when the room is warmer again."""
        hass = self.climate.hass
        room = self.climate.real_temperature()
        if room is None:
            return
        if not self.frost_active and room <= self.conf[CONF_LOCK_FROST_ON]:
            self.frost_active = True
            target = self.conf[CONF_LOCK_FROST_OFF]
            await self.climate.async_regulate_now()
            await self.climate.async_log(say(hass, "frost_log", room=room, target=target))
            await self.climate.async_notify(
                say(hass, "frost_title", name=self.climate.room),
                say(hass, "frost_body", room=room, target=target, hint=self._window_hint()),
                "time-sensitive",
            )
        elif self.frost_active and room >= self.conf[CONF_LOCK_FROST_OFF]:
            self.frost_active = False
            self._frost_ended = dt_util.utcnow()
            await self.climate.async_regulate_now()
            await self.climate.async_log(say(hass, "frost_end", room=room))

    async def check(self) -> bool:
        """Look at the room and act. Returns True when the lock takes over from the regulation."""
        if not self.enabled:
            return False
        await self._async_update_frost()
        if self.frost_active:
            return False
        if self._running:
            return True
        valve = self._valve() or 0
        wanted = self.climate.hvac_mode == HVACMode.HEAT
        if valve <= 0 and not wanted:
            return False
        # After the frost case the valve still needs its time to close
        if not wanted and self._frost_ended and (dt_util.utcnow() - self._frost_ended).total_seconds() < self.conf[CONF_LOCK_WAIT]:
            return False
        self._closed.clear()
        self._task = self.climate.hass.async_create_background_task(self._shutdown(valve, self.climate.real_temperature()), f"{self.climate.entity_id} heat lock")
        return True

    def _window_hint(self) -> str:
        return say(self.climate.hass, "window_hint") if self.climate.window_is_open() else ""

    async def _wait_closed(self) -> bool:
        if self._valve() in (0, None):
            return True
        try:
            await asyncio.wait_for(self._closed.wait(), self.conf[CONF_LOCK_WAIT])
            return True
        except TimeoutError:
            return False

    async def _shutdown(self, valve: float, room: float | None) -> None:
        """Close, verify, repeat once, then escalate."""
        hass = self.climate.hass
        name = self.climate.room
        await self.climate.async_force_off()
        reason = say(hass, "reason_valve", valve=int(valve)) if valve else say(hass, "reason_heat")
        await self.climate.async_log(say(hass, "lock_log", reason=reason, room=room))
        await self.climate.async_notify(say(hass, "lock_title", name=name), say(hass, "lock_body", reason=reason, room=room), "time-sensitive")
        if await self._wait_closed():
            if valve:
                await self.climate.async_log(say(hass, "valve_closed"))
            return
        await self.climate.async_force_off()
        await self.climate.async_log(say(hass, "valve_repeat"))
        self._closed.clear()
        if await self._wait_closed():
            await self.climate.async_log(say(hass, "valve_closed_2"))
            return
        message = say(hass, "valve_stuck", valve=self._valve())
        await self.climate.async_log(say(hass, "valve_log", message=message))
        await self.climate.async_notify(say(hass, "valve_title", name=name), message, "critical")
        await self.climate.async_speak(say(hass, "valve_say", name=name))
