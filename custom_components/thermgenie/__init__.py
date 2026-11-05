"""ThermGenie: one thermostat per room, regulated on the sensor that counts."""

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import CONF_HEATERS, CONF_LOCK_VALVE, CONF_VALVES, DOMAIN
from .learning import Learner
from .optimizer import Optimizer

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
CARD_FILE = Path(__file__).parent / "frontend" / "thermgenie-card.js"
CARD_URL = "/thermgenie/thermgenie-card.js"


@dataclass
class Runtime:
    """What the platforms of one thermostat share."""

    store: Store
    learner: Learner
    device: DeviceInfo
    optimizer: Optimizer
    listeners: list[Callable[[], None]] = field(default_factory=list)
    climate: Any = None
    live_options: dict[str, Any] | None = None  # options the running thermostat has taken over itself
    unique_ids: set[str] = field(default_factory=set)

    def stored(self) -> dict[str, Any]:
        """Return what is kept across restarts."""
        return {**self.learner.as_dict(), "optimizer": self.optimizer.as_dict()}

    def updated(self) -> None:
        """Tell the helper entities that something changed."""
        for listener in self.listeners:
            listener()

    def add(self, async_add_entities: AddEntitiesCallback, entities: Iterable[Entity]) -> None:
        """Add entities and remember them, what is not added any more leaves the registry."""
        entities = list(entities)
        self.unique_ids.update(entity.unique_id for entity in entities)
        async_add_entities(entities)

    async def async_change(self, hass: HomeAssistant, entry: ConfigEntry, changes: dict[str, Any], reload: bool = False) -> None:
        """Save settings. The regulators keep what they know unless the change needs a new setup."""
        options = {**entry.options, **changes}
        if not reload:
            self.live_options = options
        hass.config_entries.async_update_entry(entry, options=options)
        if not reload:
            await self.climate.async_settings_changed()


# They all follow the thermostat, so it comes first
HELPERS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TIME]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the card and its popup to every dashboard."""
    if "frontend" in hass.config.components:
        integration = await async_get_integration(hass, DOMAIN)
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_FILE), False)])
        add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 2 has no season any more, version 3 knows a valve per radiator instead of one for the lock."""
    if entry.version > 3:
        return False
    if entry.version == 1:
        gone = ("season_entity", "winter_state", "summer_state", "season_auto_on")
        registry = er.async_get(hass)
        if select := registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_season"):
            registry.async_remove(select)
        hass.config_entries.async_update_entry(
            entry,
            data={k: v for k, v in entry.data.items() if k not in gone},
            options={k: v for k, v in entry.options.items() if k not in gone},
            version=2,
        )
    if entry.version == 2:
        conf = {**entry.data, **entry.options}
        options = {k: v for k, v in entry.options.items() if k != CONF_LOCK_VALVE}
        if (valve := conf.get(CONF_LOCK_VALVE)) and (heaters := conf.get(CONF_HEATERS)):
            options[CONF_VALVES] = {heaters[0]: valve}
        hass.config_entries.async_update_entry(entry, data={k: v for k, v in entry.data.items() if k != CONF_LOCK_VALVE}, options=options, version=3)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one thermostat."""
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    device = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="ThermGenie", model="Thermostat")
    stored = await store.async_load() or {}
    entry.runtime_data = Runtime(store, Learner(stored), device, Optimizer(stored.get("optimizer")))
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.CLIMATE])
    await hass.config_entries.async_forward_entry_setups(entry, HELPERS)
    registry = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.unique_id not in entry.runtime_data.unique_ids:
            registry.async_remove(registered.entity_id)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one thermostat."""
    return await hass.config_entries.async_unload_platforms(entry, [Platform.CLIMATE, *HELPERS])


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options, unless the thermostat has already taken them over."""
    if dict(entry.options) == entry.runtime_data.live_options:
        return
    await hass.config_entries.async_reload(entry.entry_id)
