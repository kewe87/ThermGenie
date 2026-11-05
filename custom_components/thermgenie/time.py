"""The times of the settings."""

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULTS
from .entity import SettingEntity
from .settings import TIMES


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    conf = {**DEFAULTS, **entry.data, **entry.options}
    entry.runtime_data.add(async_add_entities, [SettingTime(entry, setting) for setting in TIMES if setting.applies(conf)])


class SettingTime(SettingEntity, TimeEntity):
    @property
    def native_value(self) -> time:
        hour, minute = str(self.conf[self.setting.key]).split(":")[:2]
        return time(int(hour), int(minute))

    async def async_set_value(self, value: time) -> None:
        await self._async_save({self.setting.key: f"{value.hour:02}:{value.minute:02}:00"})
