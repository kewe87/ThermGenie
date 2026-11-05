"""The humidity values of the room and what the regulation is doing, as sensors with history."""

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_HUMIDITY, CONF_LEARN, CONF_SLEEP, CONF_TUNING, CONF_WAKE, DEFAULTS, TUNING_MANUAL
from .entity import ThermostatEntity
from .optimizer import PHASES_PER_STEP
from .settings import heating


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    conf = {**entry.data, **entry.options}
    climate = entry.runtime_data.climate
    entities: list[SensorEntity] = [BlockedSensor(entry, "blocked_by")]
    entities += [DeviceCommandSensor(entry, device) for device in climate.devices]
    if conf.get(CONF_HUMIDITY):
        entities += [ComfortValueSensor(entry, key) for key in ("humidex", "dew_point", "comfort_temperature")]
    if conf.get(CONF_WAKE) or conf.get(CONF_SLEEP):
        entities.append(NextWakeSensor(entry, "wake_at"))
    if conf.get(CONF_LEARN):
        entities += [OvershootSensor(entry, "overshoot"), BrakeFactorSensor(entry, "brake_factor")]
    if heating({**DEFAULTS, **conf}):
        entities += [TuningSensor(entry, "tuning_state"), TunedGainSensor(entry, "tuned_kp"), TunedGainSensor(entry, "tuned_ki")]
    entry.runtime_data.add(async_add_entities, entities)


class ComfortValueSensor(ThermostatEntity, SensorEntity):
    """Humidex, dew point or comfort temperature of the room."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self.climate.comfort_values()[self.translation_key]


class BlockedSensor(ThermostatEntity, SensorEntity):
    """Why the thermostat holds back although its mode says otherwise."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = ["none", "window", "outdoor"]

    @property
    def native_value(self) -> str:
        return self.climate.blocked_by or "none"


class DeviceCommandSensor(ThermostatEntity, SensorEntity):
    """The shifted setpoint a device got last, nothing while it is off."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, device) -> None:
        super().__init__(entry, "device_command", f"device_command_{device.entity_id}")
        state = entry.runtime_data.climate.hass.states.get(device.entity_id)
        self._attr_translation_placeholders = {"device": state.name if state else device.entity_id}
        self._device = device

    @property
    def native_value(self) -> float | None:
        return self._device.command if isinstance(self._device.command, float) else None

    @property
    def extra_state_attributes(self) -> dict:
        regulator = self._device.regulator
        return {"offset": self._device.offset, "brake": round(regulator.d_offset, 2), "integral": round(regulator.integral, 2)}


class NextWakeSensor(ThermostatEntity, SensorEntity):
    """When the next heating up before the alarm starts."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> datetime | None:
        moment = self.climate.routines.status(dt_util.utcnow()).get("wake_at")
        return dt_util.parse_datetime(moment) if moment else None


class _Learned(ThermostatEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def _last(self) -> dict | None:
        history = self._runtime.learner.history
        return history[-1] if history else None


class OvershootSensor(_Learned):
    """Overshoot of the last finished heating phase."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE_DELTA
    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self._last["overshoot"] if self._last else None

    @property
    def extra_state_attributes(self) -> dict:
        return {**(self._last or {}), "phases": len(self._runtime.learner.history)}


class BrakeFactorSensor(_Learned):
    """Learned factor on the D gain, the state is the factor of the last phase."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float:
        return self._last["factor"] if self._last else 1.0

    @property
    def extra_state_attributes(self) -> dict:
        return dict(self._runtime.learner.factors)


class TuningSensor(ThermostatEntity, SensorEntity):
    """What the optimizer is doing, with its measurements as attributes."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = ["off", "collecting", "proposal"]

    @property
    def native_value(self) -> str:
        if self.climate.conf[CONF_TUNING] == TUNING_MANUAL:
            return "off"
        return "proposal" if self._runtime.optimizer.proposal else "collecting"

    @property
    def extra_state_attributes(self) -> dict:
        optimizer = self._runtime.optimizer
        return {
            "phases": len(optimizer.phases),
            "phases_needed": PHASES_PER_STEP,
            "kp_factor": optimizer.kp_factor,
            "ki_factor": optimizer.ki_factor,
            "measured": optimizer.measured,
            "proposal": optimizer.proposal,
            "last_phase": optimizer.history[-1] if optimizer.history else None,
            "steps": optimizer.steps[-5:],
        }


class TunedGainSensor(ThermostatEntity, SensorEntity):
    """The value of kp or ki the heating runs on right now."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float:
        return self.climate.tuned_gains[0 if self.translation_key == "tuned_kp" else 1]
