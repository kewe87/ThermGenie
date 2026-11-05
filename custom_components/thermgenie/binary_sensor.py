"""What can go wrong in a thermostat, for the diagnosis of its device."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOCK, CONF_VALVES
from .entity import ThermostatEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities: list[BinarySensorEntity] = [SensorStale(entry, "sensor_stale")]
    if {**entry.data, **entry.options}.get(CONF_LOCK):
        entities.append(FrostBreak(entry, "frost_active"))
    if {**entry.data, **entry.options}.get(CONF_VALVES):
        entities.append(ValveStuck(entry, "valve_stuck"))
    entry.runtime_data.add(async_add_entities, entities)


class SensorStale(ThermostatEntity, BinarySensorEntity):
    """The room sensor went silent, the devices regulate on their own."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.climate.sensor_stale


class ValveStuck(ThermostatEntity, BinarySensorEntity):
    """A valve stays open although its radiator was told to close."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return bool(self.climate.valves.stuck)

    @property
    def extra_state_attributes(self) -> dict:
        return {"valves": dict(self.climate.valves.stuck)}


class FrostBreak(ThermostatEntity, BinarySensorEntity):
    """Frost has lifted the heating lock for the moment."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.climate.lock.frost_active
