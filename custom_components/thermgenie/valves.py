"""Watch the valves: a radiator that was told to close and stays open gets a warning."""

from datetime import datetime, timedelta

from homeassistant.components.climate import HVACAction, HVACMode

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CONF_VALVE_LIMIT, CONF_VALVE_WAIT, CONF_VALVES
from .messages import say

ROOM_WINDOW = timedelta(minutes=45)  # nothing heated for this long, and this is how far back the rise is measured
ROOM_LATE = timedelta(minutes=20)  # still rising in the last part: after-heat has flattened by then
ROOM_RISE = 0.7
ROOM_LATE_RISE = 0.25
ROOM_STEP = 0.5  # a bigger jump between two readings is the sensor, not a radiator
ROOM_HUMIDITY = 8.0  # percentage points: a shower, not a valve
ROOM_FALL = 0.3  # falling again by this much from the peak ends the warning


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
        # The room itself: when nothing heats and it still gets warmer, a valve is open whatever it reports
        self._quiet_since: datetime | None = None
        self._samples: list[tuple[datetime, float, float | None]] = []
        self._warned_peak: float | None = None

    def _should_be_closed(self, device) -> bool:
        """Only a clear command counts: valves stay partly open up to some kelvin above a setpoint on their own."""
        if self.climate.device_state(device) is None or device.command is None:
            return False
        return device.command == "off" or device.shut

    async def async_check(self) -> None:
        now = dt_util.utcnow()
        await self._async_check_room(now)
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

    async def _async_check_room(self, now: datetime) -> None:
        """A valve that reports closed can still be open, after a firmware update or reset for example.

        Warn when the room has not been heated for a while and still gets warmer steadily: after-heat fades
        within half an hour, a shower brings humidity, a sensor jump is a jump. Seen with an uncalibrated TRVZB.
        """
        climate = self.climate
        room = climate.current_temperature
        quiet = climate.hvac_mode == HVACMode.HEAT and climate.hvac_action == HVACAction.IDLE and not climate.lock.frost_active
        if room is None or not quiet:
            self._quiet_since, self._samples = None, []
            await self._async_room_ok()
            return
        self._quiet_since = self._quiet_since or now
        self._samples.append((now, room, climate.current_humidity))
        self._samples = [s for s in self._samples if now - s[0] <= ROOM_WINDOW]
        if self._warned_peak is not None:
            self._warned_peak = max(self._warned_peak, room)
            if room <= self._warned_peak - ROOM_FALL:
                await self._async_room_ok()
            return
        if now - self._quiet_since < ROOM_WINDOW or len(self._samples) < 3:
            return
        rise = room - self._samples[0][1]
        late = [s for s in self._samples if now - s[0] <= ROOM_LATE]
        steps = max(abs(b[1] - a[1]) for a, b in zip(self._samples, self._samples[1:]))
        humidity = [s[2] for s in self._samples if s[2] is not None]
        if (
            rise >= ROOM_RISE
            and late and room - late[0][1] >= ROOM_LATE_RISE
            and steps <= ROOM_STEP
            and (not humidity or max(humidity) - min(humidity) < ROOM_HUMIDITY)
        ):
            self._warned_peak = room
            self.stuck["room"] = round(rise, 1)
            hass = climate.hass
            minutes = int((now - self._quiet_since).total_seconds() // 60)
            message = say(hass, "room_watch_body", rise=f"{rise:.1f}".replace(".", ",") if hass.config.language.startswith("de") else f"{rise:.1f}", minutes=minutes)
            await climate.async_log(message)
            await climate.async_notify(say(hass, "room_watch_title", name=climate.room), message, "time-sensitive")

    async def _async_room_ok(self) -> None:
        self._warned_peak = None
        if self.stuck.pop("room", None) is not None:
            await self.climate.async_log(say(self.climate.hass, "room_watch_ok"))
