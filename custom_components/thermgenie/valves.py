"""Watch the valves: a radiator that was told to close and stays open gets a warning."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CONF_VALVE_LIMIT, CONF_VALVE_WAIT, CONF_VALVES
from .messages import say


def valve_position(hass: HomeAssistant, entity: str) -> float | None:
    """Return the opening of a valve in percent, None if it does not report."""
    state = hass.states.get(entity)
    try:
        return float(state.state)
    except (AttributeError, ValueError):
        return None


class ValveWatch:
    """Compares what a radiator was told with what its valve does. A locked room escalates on its own."""

    def __init__(self, climate) -> None:
        self.climate = climate
        self.conf = climate.conf
        self._open_since: dict[str, datetime] = {}
        self.stuck: dict[str, float] = {}

    def _should_be_closed(self, device) -> bool:
        """Only a clear command counts: valves stay partly open up to some kelvin above a setpoint on their own."""
        if self.climate.device_state(device) is None or device.command is None:
            return False
        return device.command == "off" or device.shut

    async def async_check(self) -> None:
        now = dt_util.utcnow()
        wait = timedelta(minutes=self.conf[CONF_VALVE_WAIT])
        for device in self.climate.devices:
            entity = self.conf.get(CONF_VALVES, {}).get(device.entity_id)
            position = valve_position(self.climate.hass, entity) if entity else None
            if position is None or position < self.conf[CONF_VALVE_LIMIT] or not self._should_be_closed(device):
                self._open_since.pop(device.entity_id, None)
                if self.stuck.pop(device.entity_id, None) is not None:
                    await self.climate.async_log(say(self.climate.hass, "valve_watch_ok", device=self.climate.device_name(device)))
                continue
            since = self._open_since.setdefault(device.entity_id, now)
            if device.entity_id in self.stuck:
                self.stuck[device.entity_id] = position
            elif now - since >= wait:
                self.stuck[device.entity_id] = position
                await self._async_warn(device, position)

    async def _async_warn(self, device, position: float) -> None:
        hass = self.climate.hass
        name = self.climate.device_name(device)
        message = say(hass, "valve_watch_body", device=name, valve=int(position), minutes=int(self.conf[CONF_VALVE_WAIT]))
        await self.climate.async_log(message)
        # The heating lock has its own alarm for this
        if not self.climate.lock.enabled:
            await self.climate.async_notify(say(hass, "valve_watch_title", name=self.climate.room), message, "time-sensitive")
