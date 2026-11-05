"""What heats a room, the value it is regulated on and how the regulation is tuned."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULTS
from .entity import SettingEntity
from .settings import SELECTS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    conf = {**DEFAULTS, **entry.data, **entry.options}
    entry.runtime_data.add(async_add_entities, [SettingSelect(entry, setting) for setting in SELECTS if setting.applies(conf)])


class SettingSelect(SettingEntity, SelectEntity):
    @property
    def options(self) -> list[str]:
        return list(self.setting.options)

    @property
    def current_option(self) -> str:
        return self.conf[self.setting.key]

    async def async_select_option(self, option: str) -> None:
        await self._async_save({self.setting.key: option})
