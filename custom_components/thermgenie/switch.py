"""The on and off values of the settings, and one switch per routine."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULTS
from .entity import SettingEntity, ThermostatEntity
from .settings import ROUTINES, SWITCHES


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    conf = {**DEFAULTS, **entry.data, **entry.options}
    entry.runtime_data.add(
        async_add_entities,
        [
            *(SettingSwitch(entry, setting) for setting in SWITCHES if setting.applies(conf)),
            *(RoutineSwitch(entry, routine) for routine, applies in ROUTINES.items() if applies(conf)),
        ],
    )


class SettingSwitch(SettingEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return bool(self.conf[self.setting.key])

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_save({self.setting.key: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_save({self.setting.key: False})


class RoutineSwitch(ThermostatEntity, SwitchEntity):
    """The same as the routine buttons in the popup."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, routine: str) -> None:
        super().__init__(entry, f"routine_{routine}")
        self._routine = routine

    @property
    def is_on(self) -> bool:
        return self._routine not in self.climate.routines.off

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.climate.async_set_routine(self._routine, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.climate.async_set_routine(self._routine, False)
