"""Forget what the thermostat has learned."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULTS
from .entity import ThermostatEntity
from .settings import heating


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if heating({**DEFAULTS, **entry.data, **entry.options}):
        entry.runtime_data.add(async_add_entities, [ResetLearningButton(entry, "reset_learning")])


class ResetLearningButton(ThermostatEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.climate.async_reset_learning()
