"""The thermostat entity of ThermGenie."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .comfort import comfort, dew_point, humidex
from .const import (
    DOMAIN,
    COMMAND_TIMEOUT_SEC,
    HOLD_WAIT_SEC,
    CONF_TUNING,
    TUNING_AUTOMATIC,
    TUNING_MANUAL,
    CONF_HEAT_SOURCE,
    HEAT_AIR_CONDITIONER,
    HEAT_BOTH,
    HEAT_RADIATORS,
    CONF_HOLD_DEVICES,
    CONF_VALVES,
    CONF_COOLER,
    CONF_DEVICE_TEMP,
    CONF_DTEMP,
    CONF_FAN_BOOST,
    CONF_FLOW,
    CONF_HEATERS,
    CONF_HUMIDITY,
    CONF_INTEGRAL_LIMIT,
    CONF_INTEGRAL_LIMIT_COOL,
    CONF_KD,
    CONF_KD_COOL,
    CONF_KD_HEATERS,
    CONF_KI,
    CONF_KI_COOL,
    CONF_KP,
    CONF_KP_COOL,
    CONF_LOCK_FROST_OFF,
    CONF_LEARN,
    CONF_NOTIFY,
    CONF_OFFSET_MAX,
    CONF_OFFSET_MAX_COOL,
    CONF_OFFSETS,
    CONF_OUTDOOR,
    CONF_OUTDOOR_OFF,
    CONF_OUTDOOR_ON,
    CONF_PERIOD,
    CONF_PRESENCE,
    CONF_QUIET,
    CONF_REFERENCE_COOL,
    CONF_REFERENCE_HEAT,
    CONF_SENSOR,
    CONF_SENSOR_TIMEOUT,
    CONF_TTS,
    CONF_TTS_TARGETS,
    CONF_WINDOW,
    CONF_WINDOW_CLOSE_DELAY,
    CONF_WINDOW_OPEN_DELAY,
    DEFAULT_PRESETS,
    DEFAULTS,
    FAN_BOOST_GAP,
    FAN_QUIET_MODES,
    OUTDOOR_HOLD_SEC,
    PRESET_BOOST,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_FROST,
    REFERENCE_COMFORT,
    REFERENCE_HUMIDEX,
    ROUTINE_NAMES,
)
from .learning import PhaseTracker
from .lock import HeatLock
from .messages import say
from .regulator import Regulator
from .routines import Routines
from .valves import ValveWatch

_LOGGER = logging.getLogger(__name__)

OFF = "off"
PROFILE_PRESETS = {
    "heat": (PRESET_FROST, PRESET_ECO, PRESET_COMFORT, PRESET_BOOST),
    "cool": (PRESET_ECO, PRESET_COMFORT, PRESET_BOOST),
}
PRESET_NONE = "none"
PASS_THROUGH = (HVACMode.DRY, HVACMode.FAN_ONLY)
STORE_DELAY_SEC = 30


@dataclass
class Device:
    """One radiator valve or air conditioner below the thermostat."""

    entity_id: str
    role: str  # "heat" or "cool"
    offset: float
    kd: float
    regulator: Regulator
    command: float | str | None = None  # last command the device accepted
    last_run: datetime | None = None
    sent_at: datetime | None = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Create the thermostat of a config entry."""
    entry.runtime_data.add(async_add_entities, [ThermGenieClimate(entry)])
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("reset_learning", None, "async_reset_learning")
    platform.async_register_entity_service("set_routine", {vol.Required("routine"): vol.In(ROUTINE_NAMES), vol.Required("enabled"): bool}, "async_set_routine")


def _as_float(state: Any) -> float | None:
    """Return the value of a state, None if there is no usable one."""
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


class ThermGenieClimate(ClimateEntity, RestoreEntity):
    """A thermostat over heaters and optionally one cooler, heating or cooling, whichever mode is set."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "thermgenie"
    # Only the card needs these, the history stays small without them
    _unrecorded_attributes = frozenset({"devices", "profiles", "presets", "routines", "routines_off", "learned_factors", "lock_frost_off"})
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self.conf = {**DEFAULTS, **entry.data, **entry.options}
        self.runtime = entry.runtime_data
        self.runtime.climate = self
        self.room = entry.title
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = entry.runtime_data.device
        self._lock = asyncio.Lock()
        self._devices = [Device(e, "heat", 0.0, 0.0, Regulator(0, 0, 0, 0, 0)) for e in self.conf.get(CONF_HEATERS, [])]
        if self.conf.get(CONF_COOLER):
            self._devices.append(Device(self.conf[CONF_COOLER], "cool", 0.0, 0.0, Regulator(0, 0, 0, 0, 0)))
        self._tune_devices()
        self._roles = {d.role for d in self._devices}

        self._mode = HVACMode.OFF
        self._resting_profile = "heat" if "heat" in self._roles else "cool"
        self._profiles = {
            "heat": {"target": self.conf["heat_comfort"], "preset": PRESET_COMFORT},
            "cool": {"target": self.conf["cool_comfort"], "preset": PRESET_COMFORT},
        }
        self._window_open = False
        self._window_timer = None
        self._outdoor_blocked = False
        self._outdoor_since: tuple[bool, datetime] | None = None
        self._sensor_stale = False
        self.mode_since = dt_util.utcnow()
        self.routines = Routines(self)
        self.lock = HeatLock(self)
        self.valves = ValveWatch(self)
        self._hold_timer = None
        self._phase = PhaseTracker()

    def _heat_source(self) -> str:
        """Return what heats. An air conditioner that cannot heat leaves it to the radiators."""
        source = self.conf[CONF_HEAT_SOURCE]
        if source != HEAT_RADIATORS and not any(d.role == "heat" for d in self._devices):
            return HEAT_RADIATORS
        for device in self._devices:
            state = self.hass.states.get(device.entity_id) if device.role == "cool" else None
            if state is not None and "heat" not in (state.attributes.get("hvac_modes") or []):
                return HEAT_RADIATORS
        return source

    def _acts(self, device: Device) -> bool:
        """Return whether a device works in the current mode."""
        role = self._mode_role()
        if role != "heat":
            return device.role == role
        source = self._heat_source()
        return source == HEAT_BOTH or (device.role == "cool") == (source == HEAT_AIR_CONDITIONER)

    def _tune_devices(self) -> None:
        """Hand the settings to the devices. What a regulator has summed up so far stays."""
        conf = self.conf
        for device in self._devices:
            regulator = device.regulator
            if device.role == "heat":
                device.offset = conf.get(CONF_OFFSETS, {}).get(device.entity_id, 0.0)
                device.kd = conf.get(CONF_KD_HEATERS, {}).get(device.entity_id, conf[CONF_KD])
                kp, ki = self.tuned_gains
                regulator.kp, regulator.ki, regulator.offset_max, regulator.integral_limit = kp, ki, conf[CONF_OFFSET_MAX], conf[CONF_INTEGRAL_LIMIT]
            else:
                device.kd = conf[CONF_KD_COOL]
                regulator.kp, regulator.ki, regulator.offset_max, regulator.integral_limit = conf[CONF_KP_COOL], conf[CONF_KI_COOL], conf[CONF_OFFSET_MAX_COOL], conf[CONF_INTEGRAL_LIMIT_COOL]
            regulator.kd = device.kd

    def _tuning_base(self) -> tuple[str, float, float]:
        """Return what a measurement of the optimizer depends on."""
        return self.conf[CONF_TUNING], self.conf[CONF_KP], self.conf[CONF_KI]

    @property
    def tuned_gains(self) -> tuple[float, float]:
        """Return kp and ki of the heating. Only automatic tuning touches what the user set."""
        kp, ki = self.conf[CONF_KP], self.conf[CONF_KI]
        if self.conf[CONF_TUNING] != TUNING_AUTOMATIC:
            return kp, ki
        optimizer = self.runtime.optimizer
        return round(kp * optimizer.kp_factor, 4), round(ki * optimizer.ki_factor, 4)

    async def async_settings_changed(self) -> None:
        """Take over settings changed on the device page while running."""
        before = self._tuning_base()
        self.conf.update({**DEFAULTS, **self._entry.data, **self._entry.options})
        if self._tuning_base() != before:
            self.runtime.optimizer.restart()
        self._tune_devices()
        for name, profile in self._profiles.items():
            profile["target"] = self.conf.get(f"{name}_{profile['preset']}", profile["target"])
        self.routines.settings_changed()
        if not await self.lock.check():
            await self._async_regulate(force=True)

    # Properties

    @property
    def profile(self) -> str:
        """Return the settings in use: those of the running mode, while off those of the last one."""
        return self._mode_role() or self._resting_profile

    @property
    def devices(self) -> list[Device]:
        return self._devices

    @property
    def sensor_stale(self) -> bool:
        return self._sensor_stale

    @property
    def blocked_by(self) -> str | None:
        return self._blocked_by()

    @property
    def window_entity(self) -> str | None:
        return self.conf.get(CONF_WINDOW)

    @property
    def cool_target(self) -> float:
        return self._profiles["cool"]["target"]

    def window_is_open(self) -> bool:
        return self._window_open

    def _cooler_modes(self) -> list[HVACMode]:
        """Return what the cooler offers besides cooling. Before it is up both count, so a restored mode survives."""
        state = self.hass.states.get(self.conf[CONF_COOLER]) if self.conf.get(CONF_COOLER) else None
        known = state.attributes.get("hvac_modes") if state else None
        return [m for m in PASS_THROUGH if not known or m in known]

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the modes of the devices. One mode at a time keeps heating and cooling apart."""
        modes = [HVACMode.OFF]
        if "heat" in self._roles:
            modes.append(HVACMode.HEAT)
        if "cool" in self._roles:
            modes.append(HVACMode.COOL)
            modes.extend(self._cooler_modes())
        return modes

    @property
    def hvac_mode(self) -> HVACMode:
        return self._mode

    @property
    def active_target(self) -> float:
        """Return the setpoint of the profile in use. It waits there while the thermostat is off."""
        return self._profiles[self.profile]["target"]

    @property
    def active_preset(self) -> str:
        return self._profiles[self.profile]["preset"]

    @property
    def target_temperature(self) -> float | None:
        """Off means off, there is no target. Only a frost break has one."""
        if self.lock.frost_active:
            return self.conf[CONF_LOCK_FROST_OFF]
        return None if self._mode == HVACMode.OFF else self.active_target

    @property
    def preset_modes(self) -> list[str]:
        return [PRESET_NONE, *PROFILE_PRESETS[self.profile]]

    @property
    def preset_mode(self) -> str | None:
        return None if self._mode == HVACMode.OFF else self.active_preset

    @property
    def current_temperature(self) -> float | None:
        return self._reference(self.profile)

    @property
    def current_humidity(self) -> float | None:
        return self._humidity()

    @property
    def hvac_action(self) -> HVACAction:
        if self.lock.frost_active:
            return HVACAction.HEATING
        if self._mode == HVACMode.OFF:
            return HVACAction.OFF
        if self._blocked_by():
            return HVACAction.IDLE
        if self._mode == HVACMode.DRY:
            return HVACAction.DRYING
        if self._mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        working = HVACAction.HEATING if self._mode == HVACMode.HEAT else HVACAction.COOLING
        role = self._mode.value
        reported = {s.attributes.get("hvac_action") for d in self._devices if self._acts(d) and (s := self.hass.states.get(d.entity_id))}
        if reported - {None}:
            return working if working in reported else HVACAction.IDLE
        room = self._reference(role)
        if room is None:
            return HVACAction.IDLE
        return working if (self.active_target - room) * (1 if role == "heat" else -1) > 0 else HVACAction.IDLE

    def comfort_values(self) -> dict[str, float | None]:
        """Return what the integration calculates from temperature and humidity."""
        temperature = self.real_temperature()
        humidity = self._humidity()
        dew = dew_point(temperature, humidity) if temperature is not None and humidity else None
        if dew is None:
            return {"humidex": None, "comfort_temperature": None, "dew_point": None}
        return {"humidex": round(humidex(temperature, humidity), 2), "comfort_temperature": comfort(temperature, dew), "dew_point": round(dew, 2)}

    @callback
    def async_write_ha_state(self) -> None:
        super().async_write_ha_state()
        self.runtime.updated()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        active = [d.command for d in self._devices if self._active_role() and self._acts(d) and isinstance(d.command, float)]
        attributes = {
            "profile": self.profile,
            "blocked_by": self._blocked_by(),
            "sensor_stale": self._sensor_stale,
            "heat_lock": self.lock.enabled,
            "frost_active": self.lock.frost_active,
            "room_temperature": self.real_temperature(),
            **self.comfort_values(),
            "regulated_target_temperature": active[-1] if active else None,
            "devices": {
                d.entity_id: {
                    "role": d.role,
                    "offset": d.offset,
                    "command": d.command,
                    "d_offset": round(d.regulator.d_offset, 2),
                    "integral": round(d.regulator.integral, 2),
                    "available": self._device_state(d) is not None,
                }
                for d in self._devices
            },
            "profiles": self._profiles,
            "presets": {k: self.conf[k] for k in DEFAULT_PRESETS},
            "routines": self.routines.status(dt_util.utcnow()),
            "routines_off": sorted(self.routines.off),
            "reference": self.conf[CONF_REFERENCE_COOL if self.profile == "cool" else CONF_REFERENCE_HEAT],
            "guard_last_start": self.routines.guard_last,
        }
        if self.lock.enabled:
            attributes["lock_frost_off"] = self.conf[CONF_LOCK_FROST_OFF]
        if self.conf[CONF_LEARN]:
            attributes["learned_factors"] = self.runtime.learner.factors
        return attributes

    # Life cycle

    async def async_added_to_hass(self) -> None:
        """Restore the state and start listening."""
        await super().async_added_to_hass()
        self._restore(await self.async_get_last_state())
        self._read_window()
        self._enforce_modes()

        watch = [self.conf[CONF_SENSOR]]
        if self.conf.get(CONF_HUMIDITY):
            watch.append(self.conf[CONF_HUMIDITY])
        self.async_on_remove(async_track_state_change_event(self.hass, watch, self._on_sensor))
        self.async_on_remove(async_track_state_change_event(self.hass, [d.entity_id for d in self._devices], self._on_device))
        if self.conf.get(CONF_WINDOW):
            self.async_on_remove(async_track_state_change_event(self.hass, [self.conf[CONF_WINDOW]], self._on_window))
        self.async_on_remove(async_track_time_interval(self.hass, self._on_cycle, timedelta(minutes=self.conf[CONF_PERIOD])))
        self.async_on_remove(self._cancel_window_timer)
        self.async_on_remove(self._cancel_hold_timer)
        if valves := list(self.conf.get(CONF_VALVES, {}).values()):
            self.async_on_remove(async_track_state_change_event(self.hass, valves, self._on_valve))
        self.routines.start()
        self.lock.start()
        self.hass.async_create_task(self._async_first_run())

    async def _async_first_run(self) -> None:
        if self.active_preset != PRESET_NONE:
            await self.routines.async_apply_sleep()
        if not await self.lock.check():
            await self._async_regulate(force=True)

    def _restore(self, last) -> None:
        if last is None:
            return
        if last.state in (HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF, *PASS_THROUGH):
            self._mode = HVACMode(last.state)
        for name, saved in (last.attributes.get("profiles") or {}).items():
            if name in self._profiles and saved.get("target") is not None:
                preset = saved.get("preset", PRESET_NONE)
                # A preset follows its value in the settings, that may have changed
                self._profiles[name] = {"target": self.conf.get(f"{name}_{preset}", saved["target"]), "preset": preset}
        if last.attributes.get("profile") in self._roles:
            self._resting_profile = last.attributes["profile"]
        self._outdoor_blocked = last.attributes.get("blocked_by") == "outdoor"
        self.routines.guard_last = last.attributes.get("guard_last_start")
        self.routines.off = set(last.attributes.get("routines_off") or [])
        self.routines.air_running = bool((last.attributes.get("routines") or {}).get("air"))
        self.lock.frost_active = bool(last.attributes.get("frost_active"))
        for device in self._devices:
            saved = (last.attributes.get("devices") or {}).get(device.entity_id) or {}
            device.regulator.integral = saved.get("integral", 0.0)

    # Inputs

    def real_temperature(self) -> float | None:
        """Return the measured air temperature."""
        return _as_float(self.hass.states.get(self.conf[CONF_SENSOR]))

    def _humidity(self) -> float | None:
        entity = self.conf.get(CONF_HUMIDITY)
        return _as_float(self.hass.states.get(entity)) if entity else None

    def _reference(self, role: str) -> float | None:
        """Return the value the room is regulated on. Without humidity that is the plain temperature."""
        temperature = self.real_temperature()
        kind = self.conf[CONF_REFERENCE_COOL if role == "cool" else CONF_REFERENCE_HEAT]
        humidity = self._humidity()
        if temperature is None or not humidity:
            return temperature
        if kind == REFERENCE_HUMIDEX:
            return round(humidex(temperature, humidity), 2)
        if kind == REFERENCE_COMFORT:
            return comfort(temperature, dew_point(temperature, humidity))
        return temperature

    def _fresh_reference(self, role: str, now: datetime) -> float | None:
        """Return the reference for regulating, None if the sensor went silent."""
        state = self.hass.states.get(self.conf[CONF_SENSOR])
        age = (now - state.last_reported).total_seconds() / 60 if state else 0
        value = self._reference(role)
        self._sensor_stale = value is None or age > self.conf[CONF_SENSOR_TIMEOUT]
        return None if self._sensor_stale else value

    def _read_window(self) -> None:
        entity = self.conf.get(CONF_WINDOW)
        state = self.hass.states.get(entity) if entity else None
        self._window_open = state is not None and state.state == STATE_ON

    def _enforce_modes(self) -> None:
        """A device may be gone from the settings since the mode was saved."""
        if self._mode not in self.hvac_modes:
            self._set_mode(HVACMode.OFF)

    def _set_mode(self, mode: HVACMode) -> None:
        if mode != self._mode:
            self.mode_since = dt_util.utcnow()
        self._mode = mode
        self._resting_profile = self._mode_role() or self._resting_profile

    def _update_outdoor(self, now: datetime) -> None:
        """Block heating on warm days, with hysteresis and a hold time."""
        entity = self.conf.get(CONF_OUTDOOR)
        value = _as_float(self.hass.states.get(entity)) if entity else None
        if value is None:
            self._outdoor_since = None
            return
        if value > self.conf[CONF_OUTDOOR_OFF]:
            wanted = True
        elif value < self.conf[CONF_OUTDOOR_ON]:
            wanted = False
        else:
            self._outdoor_since = None
            return
        if wanted == self._outdoor_blocked:
            self._outdoor_since = None
        elif self._outdoor_since is None or self._outdoor_since[0] != wanted:
            self._outdoor_since = (wanted, now)
        elif (now - self._outdoor_since[1]).total_seconds() >= OUTDOOR_HOLD_SEC:
            self._outdoor_blocked = wanted
            self._outdoor_since = None

    @property
    def warm_outside(self) -> bool:
        return self._outdoor_blocked

    def _blocked_by(self) -> str | None:
        if self._mode == HVACMode.HEAT and self._outdoor_blocked:
            return "outdoor"
        if self._mode != HVACMode.OFF and self._window_open:
            return "window"
        return None

    def _mode_role(self) -> str | None:
        if self._mode == HVACMode.HEAT:
            return "heat"
        if self._mode == HVACMode.OFF:
            return None
        return "cool"

    def _active_role(self) -> str | None:
        """Return the role that may run now, None if everything stays off."""
        return None if self._blocked_by() else self._mode_role()

    def role_is_running(self, role: str) -> bool:
        """Return whether a device of this role accepted its command."""
        return self._mode_role() in (None, role) and any(d.role == role and d.command not in (None, OFF) for d in self._devices)

    # Events

    @callback
    def _on_sensor(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @callback
    def _on_device(self, event: Event[EventStateChangedData]) -> None:
        """A device came back from the dead or was changed by hand: bring it in line right away."""
        old = event.data["old_state"]
        new = event.data["new_state"]
        if new is None or new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.async_write_ha_state()
        elif old is None or old.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.hass.async_create_task(self._async_regulate(force=True))
        elif (self.lock.enabled or self.conf[CONF_HOLD_DEVICES]) and (old.state, old.attributes.get(ATTR_TEMPERATURE)) != (new.state, new.attributes.get(ATTR_TEMPERATURE)):
            self._hold_devices()
        if new is not None and self._device_changed_by_hand(event.data["entity_id"], new):
            self.runtime.optimizer.observer.abort()

    def _device_changed_by_hand(self, entity_id: str, state) -> bool:
        """Return whether a device differs from its command although it had the time to take it."""
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        for device in self._devices:
            if device.entity_id == entity_id:
                settled = device.sent_at is None or (dt_util.utcnow() - device.sent_at).total_seconds() >= HOLD_WAIT_SEC
                return settled and self._changed_by_hand(device, state)
        return False

    def _changed_by_hand(self, device: Device, state) -> bool:
        """Compare a device with its last command."""
        if device.command is None:
            return False
        attributes = state.attributes
        if device.command == OFF:
            if HVACMode.OFF in (attributes.get("hvac_modes") or []):
                return state.state != HVACMode.OFF
            return attributes.get(ATTR_TEMPERATURE) != attributes.get("min_temp", self.min_temp)
        if isinstance(device.command, str):
            return state.state != device.command
        temperature = attributes.get(ATTR_TEMPERATURE)
        # A device may round a command to its own steps
        off_by = abs(temperature - device.command) if temperature is not None else 0
        return state.state != (self._mode_role() or device.role) or off_by > (attributes.get("target_temp_step") or 0.5) / 2 + 0.01

    @callback
    def _hold_devices(self) -> None:
        """Set back what was changed by hand. Soon after a command a device may still report the old value, and the radio has a budget, so that waits."""
        now = dt_util.utcnow()
        wait = 0.0
        changed = False
        for device in self._devices:
            state = self._device_state(device)
            if state is None or not self._changed_by_hand(device, state):
                continue
            remaining = HOLD_WAIT_SEC - (now - device.sent_at).total_seconds() if device.sent_at else 0
            if remaining > 0:
                wait = max(wait, remaining)
                continue
            device.command = None
            device.sent_at = now
            changed = True
            self.hass.async_create_task(self.async_log(say(self.hass, "device_held", device=self.device_name(device))))
        if changed:
            self.hass.async_create_task(self._async_regulate(force=True))
        if wait and self._hold_timer is None:
            self._hold_timer = async_call_later(self.hass, wait, self._on_hold_timer)

    @callback
    def _on_hold_timer(self, _now: datetime) -> None:
        self._hold_timer = None
        self._hold_devices()

    @callback
    def _cancel_hold_timer(self) -> None:
        if self._hold_timer:
            self._hold_timer()
            self._hold_timer = None

    async def _on_valve(self, event: Event[EventStateChangedData]) -> None:
        await self.valves.async_check()
        self.async_write_ha_state()

    @callback
    def _on_window(self, event: Event[EventStateChangedData]) -> None:
        self._cancel_window_timer()
        new = event.data["new_state"]
        wanted = new is not None and new.state == STATE_ON
        delay = self.conf[CONF_WINDOW_OPEN_DELAY] if wanted else self.conf[CONF_WINDOW_CLOSE_DELAY]

        @callback
        def _apply(_now: datetime) -> None:
            self._window_timer = None
            self._window_open = wanted
            self.hass.async_create_task(self._async_regulate(force=True))

        self._window_timer = async_call_later(self.hass, delay, _apply)

    @callback
    def _cancel_window_timer(self) -> None:
        if self._window_timer:
            self._window_timer()
            self._window_timer = None

    async def _on_cycle(self, now: datetime) -> None:
        await self._async_regulate()
        await self.routines.async_cycle(dt_util.utcnow())
        await self.lock.check()
        await self.valves.async_check()
        self._track_phase()

    def _flow(self) -> float | None:
        entity = self.conf.get(CONF_FLOW)
        return _as_float(self.hass.states.get(entity)) if entity else None

    def _track_phase(self) -> None:
        """Follow the heating phases and learn from the finished ones."""
        tuning = self.conf[CONF_TUNING] != TUNING_MANUAL
        if not self.conf[CONF_LEARN] and not tuning:
            return
        room = self._reference("heat")
        if room is None:
            return
        # Only what the radiators do says something about their brake
        heating = self._active_role() == "heat" and not self._sensor_stale and self._heat_source() != HEAT_AIR_CONDITIONER
        # The heater with the lowest offset closes first, the room settles at its target
        offset = min((d.offset for d in self._devices if d.role == "heat"), default=0.0)
        target = self._profiles["heat"]["target"] + offset
        now = dt_util.utcnow().timestamp()
        if tuning:
            self._track_tuning(now, room, target, heating)
        if not self.conf[CONF_LEARN]:
            return
        phase = self._phase.update(now, room, target, heating, self._flow())
        if phase is None:
            return
        self.runtime.learner.learn(phase)
        self._save_learned()
        self.async_write_ha_state()

    def _track_tuning(self, now: float, room: float, target: float, heating: bool) -> None:
        """Measure the heating phases for the optimizer and tell what came of them."""
        optimizer = self.runtime.optimizer
        phase = optimizer.observer.update(now, room, target, heating)
        if phase is None:
            return
        automatic = self.conf[CONF_TUNING] == TUNING_AUTOMATIC
        result = optimizer.add(phase, automatic, now)
        self._save_learned()
        if result is not None:
            if automatic:
                self._tune_devices()
            kp, ki = self.conf[CONF_KP], self.conf[CONF_KI]
            message = say(self.hass, "tuning_step" if automatic else "tuning_proposal", reason=say(self.hass, f"tuning_{result['reason']}"), kp=round(kp * result["kp_factor"], 3), ki=round(ki * result["ki_factor"], 3))
            self.hass.async_create_task(self.async_log(message))
        self.async_write_ha_state()

    def _save_learned(self) -> None:
        self.runtime.store.async_delay_save(self.runtime.stored, STORE_DELAY_SEC)

    async def async_reset_learning(self) -> None:
        """Forget the learned factors and go back to the values the user set."""
        self.runtime.learner.reset()
        self.runtime.optimizer.reset()
        self._tune_devices()
        self._save_learned()
        self.async_write_ha_state()

    # Commands from Home Assistant

    def _refuse_when_locked(self, role: str) -> None:
        """Nothing from outside, be it a dashboard, Alexa or an automation, touches a locked heating."""
        if role == "heat" and self.lock.enabled:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="heat_locked", translation_placeholders={"room": self.room})

    async def async_handle_set_hvac_mode_service(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT:
            self._refuse_when_locked("heat")
        await super().async_handle_set_hvac_mode_service(hvac_mode)

    async def async_handle_set_preset_mode_service(self, preset_mode: str) -> None:
        self._refuse_when_locked(self.profile)
        await super().async_handle_set_preset_mode_service(preset_mode)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        before = self.profile
        self._set_mode(HVACMode(hvac_mode))
        if self.profile != before:
            await self.routines.async_apply_sleep()
        if not await self.lock.check():
            await self._async_regulate(force=True)

    async def async_set_routine(self, routine: str, enabled: bool) -> None:
        """Switch one routine of this thermostat on or off."""
        await self.routines.async_set_enabled(routine, enabled)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        self._refuse_when_locked(self.profile)
        await self.async_set_hvac_mode(HVACMode(self.profile))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        mode = kwargs.get(ATTR_HVAC_MODE)
        self._refuse_when_locked("heat" if mode == HVACMode.HEAT else "cool" if mode == HVACMode.COOL else self.profile)
        await self.async_apply_target(**kwargs)

    async def async_apply_target(self, **kwargs: Any) -> None:
        """Take over a setpoint, used by the service and the routines."""
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None and mode in self.hvac_modes:
            self._set_mode(HVACMode(mode))
        if (target := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._profiles[self.profile] = {"target": float(target), "preset": PRESET_NONE}
            self.routines.preset_changed(PRESET_NONE)
        if not await self.lock.check():
            await self._async_regulate(force=True)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        profile = self._profiles[self.profile]
        profile["preset"] = preset_mode
        if preset_mode != PRESET_NONE:
            profile["target"] = self.conf[f"{self.profile}_{preset_mode}"]
        self.routines.preset_changed(preset_mode)
        await self._async_regulate(force=True)

    async def async_cool_target(self, target: float, preset: str = PRESET_NONE) -> None:
        """Change the cooling setpoint only, whatever the mode. Used by the night cascade."""
        self._profiles["cool"] = {"target": float(target), "preset": preset}
        await self._async_regulate(force=True)

    async def async_force_off(self) -> None:
        """Switch off and send the command again, also when it looks like it was already sent."""
        self._set_mode(HVACMode.OFF)
        for device in self._devices:
            device.command = None
        await self._async_regulate(force=True)

    async def async_regulate_now(self) -> None:
        """Bring the devices in line right away."""
        await self._async_regulate(force=True)

    # Messages

    async def async_log(self, message: str, name: str | None = None) -> None:
        if self.hass.services.has_service("logbook", "log"):
            await self.hass.services.async_call("logbook", "log", {"name": name or self.room, "message": message}, blocking=False)

    async def async_notify(self, title: str, message: str, level: str | None = None) -> None:
        """Send a push. The critical level gets through silent modes."""
        service = self.conf.get(CONF_NOTIFY)
        if not service or "." not in service:
            return
        data: dict[str, Any] = {"title": title, "message": message}
        if level == "critical":
            data["data"] = {"push": {"interruption-level": "critical", "sound": {"name": "default", "critical": 1, "volume": 1.0}}}
        elif level:
            data["data"] = {"push": {"interruption-level": level}}
        domain, name = service.split(".", 1)
        try:
            await self.hass.services.async_call(domain, name, data, blocking=False)
        except HomeAssistantError as err:
            _LOGGER.warning("%s: push failed: %s", self.entity_id, err)

    async def async_speak(self, message: str) -> None:
        """Say it out loud when somebody is home and no focus mode is on."""
        service = self.conf.get(CONF_TTS)
        if not service or "." not in service:
            return
        presence = self.conf.get(CONF_PRESENCE)
        quiet = self.conf.get(CONF_QUIET)
        if presence and not self.hass.states.is_state(presence, "home"):
            return
        if quiet and self.hass.states.is_state(quiet, STATE_ON):
            return
        domain, name = service.split(".", 1)
        data = {"message": message, "target": self.conf.get(CONF_TTS_TARGETS, []), "data": {"type": "tts"}}
        try:
            await self.hass.services.async_call(domain, name, data, blocking=False)
        except HomeAssistantError as err:
            _LOGGER.warning("%s: announcement failed: %s", self.entity_id, err)

    # Regulation

    def device_name(self, device: Device) -> str:
        state = self.hass.states.get(device.entity_id)
        return state.name if state else device.entity_id

    def device_state(self, device: Device):
        return self._device_state(device)

    def _device_state(self, device: Device):
        state = self.hass.states.get(device.entity_id)
        return None if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) else state

    async def _async_regulate(self, force: bool = False) -> None:
        """Bring all devices in line. A dead device never holds back the others."""
        async with self._lock:
            now = dt_util.utcnow()
            self._update_outdoor(now)
            factor = self.runtime.learner.factor(self._flow()) if self.conf[CONF_LEARN] else 1.0
            for device in self._devices:
                state = self._device_state(device)
                if state is None:
                    device.command = None  # send again as soon as it is back
                    continue
                if device.role == "heat":
                    device.regulator.kd = device.kd * factor
                wanted = self._wanted(device, state, now, force)
                await self._async_send(device, state, wanted)
                await self._async_fan(device, state, wanted)
        self.async_write_ha_state()

    def _wanted(self, device: Device, state, now: datetime, force: bool) -> float | str:
        """Return what the device should do: OFF, a pass-through mode or a setpoint."""
        if self.lock.frost_active and device.role == "heat":
            return self._fit(self.conf[CONF_LOCK_FROST_OFF], state)
        target = self.active_target + device.offset
        if not self._acts(device) or self._blocked_by() == "outdoor":
            device.last_run = None
            return OFF
        if self._window_open:
            device.last_run = None
            return OFF if device.role == "cool" else self.conf["heat_frost"]
        if self._mode in PASS_THROUGH:
            device.last_run = None
            return self._mode.value
        role = self._mode_role()
        room = self._fresh_reference(role, now)
        if room is None:  # sensor gone: the device regulates on its own sensor
            return self._fit(target, state)

        periods = 1.0
        if device.last_run is not None:
            periods = (now - device.last_run).total_seconds() / 60 / self.conf[CONF_PERIOD]
        device.last_run = now
        direction = 1 if role == "heat" else -1
        value = device.regulator.update(target, room, periods, now.timestamp(), direction)
        if self.conf[CONF_DEVICE_TEMP] and (own := state.attributes.get("current_temperature")) is not None:
            value += own - room  # the device sits elsewhere, tell it in its own scale
        wanted = self._fit(value, state)
        if not force and isinstance(device.command, float) and abs(wanted - device.command) < self.conf[CONF_DTEMP]:
            return device.command  # spare the radio
        return wanted

    def _fit(self, value: float, state) -> float:
        """Round to the regulation step and stay within the limits of the device."""
        step = self.conf[CONF_DTEMP] or 0.5
        value = round(value / step) * step
        low = state.attributes.get("min_temp", self.min_temp)
        high = state.attributes.get("max_temp", self.max_temp)
        return float(min(high, max(low, value)))

    async def _async_send(self, device: Device, state, wanted: float | str) -> None:
        """Send only what changed. A failed command is repeated in the next cycle."""
        modes = state.attributes.get("hvac_modes") or []
        try:
            if wanted == OFF:
                if HVACMode.OFF in modes:
                    # Also when it was started behind our back: that is the interlock
                    if state.state != HVACMode.OFF:
                        await self._async_command(SERVICE_SET_HVAC_MODE, device, {ATTR_HVAC_MODE: HVACMode.OFF})
                elif device.command != OFF:
                    # Some valves have no off mode, their lowest setpoint means off
                    await self._async_command(SERVICE_SET_TEMPERATURE, device, {ATTR_TEMPERATURE: state.attributes.get("min_temp", self.min_temp)})
                device.command = OFF
                return
            if isinstance(wanted, str):  # drying or fan only, the device decides the rest
                if state.state != wanted:
                    await self._async_command(SERVICE_SET_HVAC_MODE, device, {ATTR_HVAC_MODE: wanted})
                device.command = wanted
                return
            mode = self._mode_role() or device.role
            if state.state != mode and mode in modes:
                await self._async_command(SERVICE_SET_HVAC_MODE, device, {ATTR_HVAC_MODE: mode})
                device.command = None
            if device.command != wanted:
                await self._async_command(SERVICE_SET_TEMPERATURE, device, {ATTR_TEMPERATURE: wanted})
                device.command = wanted
        except (HomeAssistantError, TimeoutError) as err:
            device.command = None
            _LOGGER.warning("%s: command to %s failed: %s", self.entity_id, device.entity_id, err)

    async def _async_command(self, service: str, device: Device, data: dict[str, Any]) -> None:
        device.sent_at = dt_util.utcnow()
        await self._async_call(service, device, data)

    async def _async_fan(self, device: Device, state, wanted: float | str) -> None:
        """Turn the fan of the air conditioner up while it has a lot to do."""
        if not self.conf[CONF_FAN_BOOST] or device.role != "cool":
            return
        fan = state.attributes.get("fan_mode")
        fans = state.attributes.get("fan_modes") or []
        room = self._reference("cool")
        boost = isinstance(wanted, float) and self._mode == HVACMode.COOL and room is not None and wanted - room <= -FAN_BOOST_GAP
        try:
            if boost and fan != "high" and "high" in fans:
                await self._async_call(SERVICE_SET_FAN_MODE, device, {ATTR_FAN_MODE: "high"})
            elif not boost and fan not in FAN_QUIET_MODES and "auto" in fans and wanted != OFF:
                await self._async_call(SERVICE_SET_FAN_MODE, device, {ATTR_FAN_MODE: "auto"})
        except (HomeAssistantError, TimeoutError) as err:
            _LOGGER.warning("%s: fan command to %s failed: %s", self.entity_id, device.entity_id, err)

    async def _async_call(self, service: str, device: Device, data: dict[str, Any]) -> None:
        async with asyncio.timeout(COMMAND_TIMEOUT_SEC):
            await self.hass.services.async_call(CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: device.entity_id, **data}, blocking=True)
