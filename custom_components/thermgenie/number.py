"""The numbers of the settings."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HEATERS, CONF_KD, CONF_KD_HEATERS, CONF_LOCK, CONF_OFFSETS, DEFAULTS, DOMAIN
from .entity import SettingEntity
from .settings import HEATER_KD, HEATER_OFFSET, NUMBERS, ORDERED, Setting


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    conf = {**DEFAULTS, **entry.data, **entry.options}
    entities: list[NumberEntity] = [SettingNumber(entry, setting) for setting in NUMBERS if setting.applies(conf)]
    heaters = conf.get(CONF_HEATERS, [])
    if len(heaters) > 1 and not conf.get(CONF_LOCK):
        for heater in heaters:
            entities.append(HeaterNumber(entry, HEATER_OFFSET, heater, CONF_OFFSETS, 0.0, _name(hass, heater)))
            entities.append(HeaterNumber(entry, HEATER_KD, heater, CONF_KD_HEATERS, conf[CONF_KD], _name(hass, heater)))
    entry.runtime_data.add(async_add_entities, entities)


def _name(hass: HomeAssistant, entity_id: str) -> str:
    """Return the name of a radiator. It may not be up yet, the registry knows it anyway."""
    if (state := hass.states.get(entity_id)) is not None:
        return state.name
    registered = er.async_get(hass).async_get(entity_id)
    return (registered.name or registered.original_name or entity_id) if registered else entity_id


class SettingNumber(SettingEntity, NumberEntity):
    """One number of the settings."""

    _attr_mode = NumberMode.BOX

    def __init__(self, entry: ConfigEntry, setting: Setting, suffix: str | None = None) -> None:
        super().__init__(entry, setting, suffix)
        self._attr_native_min_value = setting.low
        self._attr_native_max_value = setting.high
        self._attr_native_step = setting.step
        self._attr_native_unit_of_measurement = setting.unit

    @property
    def native_value(self) -> float:
        return self.conf[self.setting.key]

    async def async_set_native_value(self, value: float) -> None:
        merged = {**self.conf, self.setting.key: value}
        if any(self.setting.key in pair and merged[pair[0]] >= merged[pair[1]] for pair in ORDERED):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="limits_order")
        await self._async_save({self.setting.key: value})


class HeaterNumber(SettingNumber):
    """Offset or brake of one radiator in a room with several."""

    def __init__(self, entry: ConfigEntry, setting: Setting, heater: str, store: str, default: float, name: str) -> None:
        super().__init__(entry, setting, f"{setting.key}_{heater}")
        self._attr_translation_placeholders = {"device": name}
        self._heater = heater
        self._store = store
        self._default = default

    @property
    def native_value(self) -> float:
        return self.conf.get(self._store, {}).get(self._heater, self._default)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_save({self._store: {**self.conf.get(self._store, {}), self._heater: value}})
