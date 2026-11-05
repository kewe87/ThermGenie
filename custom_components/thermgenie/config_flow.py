"""The setup wizard and the settings menu of ThermGenie."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
import voluptuous as vol

from .ai import ENTITY_FIELDS, async_suggest
from .const import (
    CASCADE_NUMBERS,
    CONF_APPROACH_BELOW,
    CONF_APPROACH_DIRECTION,
    CONF_APPROACH_DISTANCE,
    CONF_APPROACH_TARGET,
    CONF_BOOST_MINUTES,
    CONF_CASCADE_FAN,
    CONF_CASCADE_FELT,
    CONF_CASCADE_FOCUS,
    CONF_CASCADE_FRESH,
    CONF_CASCADE_REAL,
    CONF_CASCADE_START,
    CONF_COOLER,
    CONF_DEVICE_TEMP,
    CONF_DRY_DEW,
    CONF_DRY_DEW_BELOW,
    CONF_DRY_HUMIDITY,
    CONF_DRY_HUMIDITY_BELOW,
    CONF_DTEMP,
    CONF_FAN_BOOST,
    CONF_FLOW,
    CONF_GUARD_ABOVE,
    CONF_GUARD_BELOW,
    CONF_GUARD_DISTANCE,
    CONF_GUARD_FROM,
    CONF_GUARD_SENSOR,
    CONF_GUARD_UNTIL,
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
    CONF_LEARN,
    CONF_LOCK,
    CONF_LOCK_FROST_OFF,
    CONF_LOCK_FROST_ON,
    CONF_HEAT_SOURCE,
    CONF_HOLD_DEVICES,
    HEAT_AIR_CONDITIONER,
    HEAT_BOTH,
    HEAT_RADIATORS,
    CONF_VALVES,
    CONF_VALVE_LIMIT,
    CONF_VALVE_WAIT,
    CONF_LOCK_WAIT,
    CONF_NAME,
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
    CONF_SLEEP,
    CONF_TUNING,
    TUNING_AUTOMATIC,
    TUNING_MANUAL,
    TUNING_OBSERVE,
    CONF_TTS,
    CONF_TTS_TARGETS,
    CONF_WAKE,
    CONF_AIR_COMPARE,
    CONF_AIR_COOL,
    CONF_AIR_FAN,
    CONF_AIR_HEAT,
    CONF_AIR_OFF,
    CONF_AIR_ON,
    CONF_AIR_PERCENT,
    CONF_WAKE_FALLBACK,
    CONF_WAKE_FALLBACK_ENTITY,
    CONF_WAKE_FALLBACK_ON,
    CONF_WAKE_LEAD,
    CONF_WINDOW,
    CONF_WINDOW_CLOSE_DELAY,
    CONF_WINDOW_OPEN_DELAY,
    DEFAULTS,
    DOMAIN,
    REFERENCE_COMFORT,
    REFERENCE_HUMIDEX,
    REFERENCE_TEMPERATURE,
)

MAX_HEATERS = 6
_LOGGER = logging.getLogger(__name__)

SWITCHES = ["binary_sensor", "input_boolean"]


def _number(low: float, high: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(min=low, max=high, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _entity(domain: list[str], multiple: bool = False) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain, multiple=multiple))


def _reference() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=[REFERENCE_TEMPERATURE, REFERENCE_HUMIDEX, REFERENCE_COMFORT], translation_key="reference", mode=selector.SelectSelectorMode.DROPDOWN)
    )


def _section(name: str, fields: dict[Any, Any], collapsed: bool = False) -> dict[Any, Any]:
    return {vol.Required(name): section(vol.Schema(fields), {"collapsed": collapsed})}


class _Steps:
    """The pages, shared by the setup wizard and the settings menu."""

    values: dict[str, Any]

    def _opt(self, key: str) -> vol.Optional:
        """Return an optional field that can also be emptied again."""
        return vol.Optional(key, description={"suggested_value": self.values.get(key)})

    def _def(self, key: str) -> vol.Required:
        return vol.Required(key, default=self.values.get(key, DEFAULTS[key]))

    def _take(self, user_input: dict[str, Any], *optional: str) -> None:
        for key in optional:
            self.values.pop(key, None)
        flat: dict[str, Any] = {}
        for key, value in user_input.items():
            flat.update(value if isinstance(value, dict) else {key: value})
        self.values.update({k: v for k, v in flat.items() if v not in (None, "", [])})

    def _service(self) -> selector.SelectSelector:
        names = sorted(f"notify.{name}" for name in self.hass.services.async_services_for_domain("notify"))
        return selector.SelectSelector(selector.SelectSelectorConfig(options=names, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN))

    async def _after(self, step: str) -> ConfigFlowResult:
        raise NotImplementedError

    def _devices_schema(self, with_name: bool) -> vol.Schema:
        fields: dict[Any, Any] = {}
        if with_name:
            fields[vol.Required(CONF_NAME)] = selector.TextSelector()
        fields[vol.Required(CONF_SENSOR, description={"suggested_value": self.values.get(CONF_SENSOR)})] = _entity(["sensor"])
        fields[self._opt(CONF_HUMIDITY)] = _entity(["sensor"])
        fields[self._opt(CONF_HEATERS)] = _entity(["climate"], multiple=True)
        fields[self._opt(CONF_COOLER)] = _entity(["climate"])
        fields[self._opt(CONF_WINDOW)] = _entity(["binary_sensor"])
        return vol.Schema(fields)

    def _devices_errors(self, user_input: dict[str, Any]) -> dict[str, str]:
        heaters = user_input.get(CONF_HEATERS) or []
        cooler = user_input.get(CONF_COOLER)
        if not heaters and not cooler:
            return {"base": "no_device"}
        if cooler in heaters:
            return {"base": "cooler_is_heater"}
        if len(heaters) > MAX_HEATERS:
            return {"base": "too_many_heaters"}
        return {}

    def _device_name(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id

    async def async_step_offsets(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offset and brake per radiator, only asked when a room has several."""
        heaters = self.values.get(CONF_HEATERS, [])
        if len(heaters) < 2:
            self.values[CONF_OFFSETS] = {}
            self.values[CONF_KD_HEATERS] = {}
            return await self._after("offsets")
        if user_input is not None:
            self.values[CONF_OFFSETS] = {e: user_input[f"offset_{i}"] for i, e in enumerate(heaters, 1)}
            self.values[CONF_KD_HEATERS] = {e: user_input[f"kd_{i}"] for i, e in enumerate(heaters, 1)}
            return await self._after("offsets")
        offsets = self.values.get(CONF_OFFSETS, {})
        kds = self.values.get(CONF_KD_HEATERS, {})
        schema: dict[Any, Any] = {}
        for i, e in enumerate(heaters, 1):
            schema[vol.Required(f"offset_{i}", default=offsets.get(e, 0.0))] = _number(-3, 3, 0.1, "K")
            schema[vol.Required(f"kd_{i}", default=kds.get(e, self.values.get(CONF_KD, DEFAULTS[CONF_KD])))] = _number(0, 3, 0.1)
        names = "\n".join(f"- **{i}:** {self._device_name(e)}" for i, e in enumerate(heaters, 1))
        return self.async_show_form(step_id="offsets", data_schema=vol.Schema(schema), description_placeholders={"devices": names})

    async def async_step_outdoor(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """No heating on warm days."""
        if user_input is not None:
            self._take(user_input, CONF_OUTDOOR)
            return await self._after("outdoor")
        schema = {
            self._opt(CONF_OUTDOOR): _entity(["sensor"]),
            self._def(CONF_OUTDOOR_OFF): _number(0, 40, 0.5, "°C"),
            self._def(CONF_OUTDOOR_ON): _number(0, 40, 0.5, "°C"),
        }
        return self.async_show_form(step_id="outdoor", data_schema=vol.Schema(schema))

    async def async_step_presets(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The preset temperatures, separately for heating and cooling."""
        if user_input is not None:
            self._take(user_input)
            return await self._after("presets")
        schema: dict[Any, Any] = {}
        if self.values.get(CONF_HEATERS):
            schema |= _section("heating", {self._def(k): _number(5, 35, 0.5, "°C") for k in ("heat_frost", "heat_eco", "heat_comfort", "heat_boost")})
        if self.values.get(CONF_COOLER):
            schema |= _section("cooling", {self._def(k): _number(5, 35, 0.5, "°C") for k in ("cool_eco", "cool_comfort", "cool_boost")})
        return self.async_show_form(step_id="presets", data_schema=vol.Schema(schema))

    async def async_step_regulation(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The set screws of the regulator."""
        if user_input is not None:
            self._take(user_input, CONF_FLOW)
            return await self._after("regulation")
        schema: dict[Any, Any] = {}
        if self.values.get(CONF_HEATERS):
            schema |= _section(
                "heating",
                {
                    **(
                        {
                            self._def(CONF_HEAT_SOURCE): selector.SelectSelector(
                                selector.SelectSelectorConfig(options=[HEAT_RADIATORS, HEAT_AIR_CONDITIONER, HEAT_BOTH], translation_key="heat_source", mode=selector.SelectSelectorMode.DROPDOWN)
                            )
                        }
                        if self.values.get(CONF_COOLER)
                        else {}
                    ),
                    self._def(CONF_REFERENCE_HEAT): _reference(),
                    self._def(CONF_KP): _number(0, 3, 0.05),
                    self._def(CONF_KI): _number(0, 1, 0.01),
                    self._def(CONF_KD): _number(0, 3, 0.1),
                    self._def(CONF_OFFSET_MAX): _number(0, 10, 0.5, "K"),
                    self._def(CONF_INTEGRAL_LIMIT): _number(0, 200, 1),
                    self._def(CONF_DEVICE_TEMP): selector.BooleanSelector(),
                },
            )
            schema |= _section(
                "learning",
                {
                    self._def(CONF_TUNING): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=[TUNING_MANUAL, TUNING_OBSERVE, TUNING_AUTOMATIC], translation_key="tuning", mode=selector.SelectSelectorMode.DROPDOWN)
                    ),
                    self._def(CONF_LEARN): selector.BooleanSelector(),
                    self._opt(CONF_FLOW): _entity(["sensor"]),
                },
            )
        if self.values.get(CONF_COOLER):
            schema |= _section(
                "cooling",
                {
                    self._def(CONF_REFERENCE_COOL): _reference(),
                    self._def(CONF_KP_COOL): _number(0, 3, 0.05),
                    self._def(CONF_KI_COOL): _number(0, 1, 0.01),
                    self._def(CONF_KD_COOL): _number(0, 3, 0.1),
                    self._def(CONF_OFFSET_MAX_COOL): _number(0, 10, 0.5, "K"),
                    self._def(CONF_INTEGRAL_LIMIT_COOL): _number(0, 200, 1),
                    self._def(CONF_FAN_BOOST): selector.BooleanSelector(),
                },
            )
        schema |= _section(
            "timing",
            {
                self._def(CONF_PERIOD): _number(1, 60, 1, "min"),
                self._def(CONF_DTEMP): _number(0.1, 2, 0.1, "K"),
                self._def(CONF_BOOST_MINUTES): _number(0, 240, 5, "min"),
                self._def(CONF_SENSOR_TIMEOUT): _number(5, 720, 5, "min"),
                self._def(CONF_WINDOW_OPEN_DELAY): _number(0, 3600, 10, "s"),
                self._def(CONF_WINDOW_CLOSE_DELAY): _number(0, 3600, 10, "s"),
            },
            collapsed=True,
        )
        return self.async_show_form(step_id="regulation", data_schema=vol.Schema(schema))

    async def async_step_routines(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Messages and everyday life. Everything stays inactive without its entities."""
        if user_input is not None:
            self._take(user_input, CONF_NOTIFY, CONF_TTS, CONF_TTS_TARGETS, CONF_QUIET, CONF_PRESENCE, CONF_SLEEP, CONF_WAKE, CONF_WAKE_FALLBACK_ENTITY, CONF_APPROACH_DIRECTION, CONF_APPROACH_DISTANCE)
            return await self._after("routines")
        schema = {
            **_section(
                "messages",
                {
                    self._opt(CONF_NOTIFY): self._service(),
                    self._opt(CONF_TTS): self._service(),
                    self._opt(CONF_TTS_TARGETS): _entity(["media_player"], multiple=True),
                    self._opt(CONF_QUIET): _entity(SWITCHES),
                },
            ),
            **_section(
                "daily",
                {
                    self._opt(CONF_PRESENCE): _entity(["person", "device_tracker", "binary_sensor"]),
                    self._opt(CONF_SLEEP): _entity(SWITCHES),
                    self._opt(CONF_WAKE): _entity(["input_datetime"]),
                    self._def(CONF_WAKE_LEAD): _number(0, 240, 5, "min"),
                    self._def(CONF_WAKE_FALLBACK_ON): selector.BooleanSelector(),
                    self._def(CONF_WAKE_FALLBACK): selector.TimeSelector(),
                    self._opt(CONF_WAKE_FALLBACK_ENTITY): _entity(["input_datetime", "sensor"]),
                },
            ),
            **_section(
                "way_home",
                {
                    self._opt(CONF_APPROACH_DIRECTION): _entity(["sensor"]),
                    self._opt(CONF_APPROACH_DISTANCE): _entity(["sensor"]),
                    self._def(CONF_APPROACH_BELOW): _number(0, 500000, 1000, "m"),
                    self._def(CONF_APPROACH_TARGET): _number(5, 30, 0.5, "°C"),
                },
                collapsed=True,
            ),
        }
        return self.async_show_form(step_id="routines", data_schema=vol.Schema(schema))

    async def async_step_air(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A fan that evens out the air, while heating and while cooling."""
        if user_input is not None:
            self._take(user_input, CONF_AIR_FAN, CONF_AIR_COMPARE)
            return await self._after("air")
        schema = {
            self._opt(CONF_AIR_FAN): _entity(["fan"]),
            self._def(CONF_AIR_HEAT): selector.BooleanSelector(),
            self._def(CONF_AIR_COOL): selector.BooleanSelector(),
            self._def(CONF_AIR_PERCENT): _number(1, 100, 1, "%"),
            self._opt(CONF_AIR_COMPARE): _entity(["sensor"]),
            self._def(CONF_AIR_ON): _number(0.5, 10, 0.5, "K"),
            self._def(CONF_AIR_OFF): _number(0, 10, 0.5, "K"),
        }
        return self.async_show_form(step_id="air", data_schema=vol.Schema(schema))

    async def async_step_valves(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Hold the devices against changes by hand and watch whether the valves close."""
        heaters = self.values.get(CONF_HEATERS, [])
        if user_input is not None:
            valves = {e: user_input.pop(f"valve_{i}") for i, e in enumerate(heaters, 1) if user_input.get(f"valve_{i}")}
            self._take({k: v for k, v in user_input.items() if not k.startswith("valve_") or k in (CONF_VALVE_LIMIT, CONF_VALVE_WAIT)})
            self.values[CONF_VALVES] = valves
            return await self._after("valves")
        known = self.values.get(CONF_VALVES, {})
        schema: dict[Any, Any] = {self._def(CONF_HOLD_DEVICES): selector.BooleanSelector()}
        for i, e in enumerate(heaters, 1):
            schema[vol.Optional(f"valve_{i}", description={"suggested_value": known.get(e)})] = _entity(["sensor"])
        schema[self._def(CONF_VALVE_LIMIT)] = _number(1, 100, 1, "%")
        schema[self._def(CONF_VALVE_WAIT)] = _number(5, 720, 5, "min")
        names = "\n".join(f"- **{i}:** {self._device_name(e)}" for i, e in enumerate(heaters, 1))
        return self.async_show_form(step_id="valves", data_schema=vol.Schema(schema), description_placeholders={"devices": names})

    async def async_step_lock(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The heating lock."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_LOCK_FROST_OFF] <= user_input[CONF_LOCK_FROST_ON]:
                errors["base"] = "frost_limits"
            else:
                self._take(user_input)
                return await self._after("lock")
        schema = {
            self._def(CONF_LOCK): selector.BooleanSelector(),
            self._def(CONF_LOCK_FROST_ON): _number(0, 15, 0.5, "°C"),
            self._def(CONF_LOCK_FROST_OFF): _number(0, 20, 0.5, "°C"),
            self._def(CONF_LOCK_WAIT): _number(30, 1800, 30, "s"),
        }
        return self.async_show_form(step_id="lock", data_schema=vol.Schema(schema), errors=errors)

    async def async_step_summer(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Heat guard, drying limit and night cascade."""
        if user_input is not None:
            self._take(
                user_input,
                CONF_GUARD_SENSOR,
                CONF_GUARD_DISTANCE,
                CONF_DRY_DEW,
                CONF_DRY_HUMIDITY,
                CONF_CASCADE_FOCUS,
                CONF_CASCADE_FAN,
                CONF_CASCADE_FELT,
                CONF_CASCADE_REAL,
                CONF_CASCADE_FRESH,
                CONF_CASCADE_START,
            )
            return await self._after("summer")
        fine = {
            self._def(key): _number(0, 100, 1, "%") if isinstance(default, int) else _number(0, 40, 0.05, "K" if key == "cascade_drift" else "°C")
            for key, (_, default) in CASCADE_NUMBERS.items()
        }
        schema = {
            **_section(
                "heat_guard",
                {
                    self._opt(CONF_GUARD_SENSOR): _entity(["sensor"]),
                    self._def(CONF_GUARD_ABOVE): _number(15, 40, 0.1, "°C"),
                    self._opt(CONF_GUARD_DISTANCE): _entity(["sensor"]),
                    self._def(CONF_GUARD_BELOW): _number(0, 1000000, 1000, "m"),
                    self._def(CONF_GUARD_FROM): selector.TimeSelector(),
                    self._def(CONF_GUARD_UNTIL): selector.TimeSelector(),
                },
            ),
            **_section(
                "drying",
                {
                    self._opt(CONF_DRY_DEW): _entity(["sensor"]),
                    self._def(CONF_DRY_DEW_BELOW): _number(0, 25, 0.5, "°C"),
                    self._opt(CONF_DRY_HUMIDITY): _entity(["sensor"]),
                    self._def(CONF_DRY_HUMIDITY_BELOW): _number(0, 100, 1, "%"),
                },
            ),
            **_section(
                "cascade",
                {
                    self._opt(CONF_CASCADE_FOCUS): _entity(SWITCHES),
                    self._opt(CONF_CASCADE_FAN): _entity(["fan"]),
                    self._opt(CONF_CASCADE_FELT): _entity(["sensor"]),
                    self._opt(CONF_CASCADE_REAL): _entity(["sensor"]),
                    self._opt(CONF_CASCADE_FRESH): _entity(["sensor"], multiple=True),
                    self._opt(CONF_CASCADE_START): _entity(["input_datetime"]),
                },
            ),
            **_section("cascade_fine", fine, collapsed=True),
        }
        return self.async_show_form(step_id="summer", data_schema=vol.Schema(schema))


class ThermGenieConfigFlow(_Steps, ConfigFlow, domain=DOMAIN):
    """Set up one thermostat in a few steps. Everything else lives in the settings."""

    VERSION = 3

    def __init__(self) -> None:
        self.values = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._devices_errors(user_input)
            if not errors:
                await self.async_set_unique_id(user_input[CONF_NAME].strip().casefold())
                self._abort_if_unique_id_configured()
                self._take(user_input)
                return await self.async_step_offsets()
        return self.async_show_form(step_id="user", data_schema=self._devices_schema(True), errors=errors)

    async def _after(self, step: str) -> ConfigFlowResult:
        if step == "offsets":
            return await self.async_step_outdoor()
        if step == "outdoor":
            return await self.async_step_presets()
        if step == "presets":
            return await self.async_step_routines()
        return self.async_create_entry(title=self.values.pop(CONF_NAME).strip(), data=self.values)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "ThermGenieOptionsFlow":
        return ThermGenieOptionsFlow(config_entry)


class ThermGenieOptionsFlow(_Steps, OptionsFlow):
    """The settings: a menu of pages, saved together at the end."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.values = {**config_entry.data, **config_entry.options}
        self._entry = config_entry
        self._suggested: dict[str, Any] = {}
        self._reason = ""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        pages = ["ai"] if self.hass.states.async_entity_ids("ai_task") else []
        pages += ["devices", "outdoor", "presets", "regulation", "routines", "air"]
        if self.values.get(CONF_HEATERS):
            pages += ["lock", "valves"]
        if self.values.get(CONF_COOLER):
            pages.append("summer")
        return self.async_show_menu(step_id="init", menu_options=[*pages, "save"])

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._devices_errors(user_input)
            if not errors:
                self._take(user_input, CONF_HEATERS, CONF_COOLER, CONF_WINDOW, CONF_HUMIDITY)
                return await self.async_step_offsets()
        return self.async_show_form(step_id="devices", data_schema=self._devices_schema(False), errors=errors)

    async def _after(self, step: str) -> ConfigFlowResult:
        return await self.async_step_init()

    async def async_step_ai(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask an AI Task entity for suggestions. They end up in a form, not in the settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._suggested, self._reason = await async_suggest(self.hass, user_input["ai_entity"], self._entry.title, self.values, user_input.get("wish", ""))
            except (HomeAssistantError, vol.Invalid) as err:
                _LOGGER.warning("AI suggestions failed: %s", err)
                errors["base"] = "ai_failed"
            else:
                if self._suggested:
                    return await self.async_step_ai_review()
                errors["base"] = "ai_empty"
        schema = {
            vol.Required("ai_entity"): _entity(["ai_task"]),
            vol.Optional("wish"): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        }
        return self.async_show_form(step_id="ai", data_schema=vol.Schema(schema), errors=errors)

    async def async_step_ai_review(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show what the AI suggests. Every value can be changed or emptied before it counts."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._devices_errors({**self.values, **user_input})
            if not errors:
                # The room sensor cannot be emptied, without it nothing works
                self._take(user_input, *(key for key in self._suggested if key != CONF_SENSOR))
                if CONF_HEATERS in self._suggested:
                    return await self.async_step_offsets()
                return await self.async_step_init()
        schema: dict[Any, Any] = {}
        for key, value in self._suggested.items():
            field = vol.Optional(key, description={"suggested_value": value})
            if key in ENTITY_FIELDS:
                domains, multiple, _purpose = ENTITY_FIELDS[key]
                schema[field] = _entity(list(domains), multiple=multiple)
            else:
                schema[field] = _number(5, 30, 0.5, "°C")
        return self.async_show_form(step_id="ai_review", data_schema=vol.Schema(schema), errors=errors, description_placeholders={"reason": self._reason or "-"})

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=self.values)
