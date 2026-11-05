"""What the entities below a thermostat have in common."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .const import DEFAULTS
from .settings import Setting


class ThermostatEntity(Entity):
    """Follows the thermostat of its config entry."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, key: str, suffix: str | None = None) -> None:
        self._entry = entry
        self._runtime = entry.runtime_data
        self._attr_device_info = entry.runtime_data.device
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{suffix or key}"

    @property
    def climate(self):
        return self._runtime.climate

    async def async_added_to_hass(self) -> None:
        self._runtime.listeners.append(self._updated)
        self.async_on_remove(lambda: self._runtime.listeners.remove(self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()


class SettingEntity(Entity):
    """One value of the settings, it changes the running thermostat without setting it up again."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, setting: Setting, suffix: str | None = None) -> None:
        self._entry = entry
        self.setting = setting
        self._attr_device_info = entry.runtime_data.device
        self._attr_translation_key = setting.key
        self._attr_unique_id = f"{entry.entry_id}_{suffix or setting.key}"
        self._attr_entity_registry_enabled_default = not setting.expert

    @property
    def conf(self) -> dict:
        return {**DEFAULTS, **self._entry.data, **self._entry.options}

    async def _async_save(self, changes: dict) -> None:
        await self._entry.runtime_data.async_change(self.hass, self._entry, changes, self.setting.reload)
        self.async_write_ha_state()
