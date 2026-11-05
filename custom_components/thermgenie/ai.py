"""Setup suggestions from an AI Task entity. They only fill a form, nothing is applied unseen."""

import json
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from .const import (
    CONF_AIR_COMPARE,
    CONF_AIR_FAN,
    CONF_COOLER,
    CONF_HEATERS,
    CONF_HUMIDITY,
    CONF_OUTDOOR,
    CONF_PRESENCE,
    CONF_SENSOR,
    CONF_SLEEP,
    CONF_WAKE,
    CONF_WINDOW,
    DOMAIN,
)

# key: allowed domains, several values, what the entity is for
ENTITY_FIELDS: dict[str, tuple[tuple[str, ...], bool, str]] = {
    CONF_SENSOR: (("sensor",), False, "Temperature sensor in the room, away from the radiator. Never a sensor of the thermostat itself."),
    CONF_HUMIDITY: (("sensor",), False, "Humidity sensor in the room."),
    CONF_HEATERS: (("climate",), True, "All radiator thermostats of the room."),
    CONF_COOLER: (("climate",), False, "Air conditioner of the room."),
    CONF_WINDOW: (("binary_sensor",), False, "Window contact of the room, or a group of them."),
    CONF_OUTDOOR: (("sensor",), False, "Outdoor temperature."),
    CONF_PRESENCE: (("person", "device_tracker", "binary_sensor"), False, "The person who lives here, or a group that says somebody is home."),
    CONF_SLEEP: (("binary_sensor", "input_boolean"), False, "Says the person is asleep."),
    CONF_WAKE: (("input_datetime",), False, "Holds the next alarm with date and time."),
    CONF_AIR_FAN: (("fan",), False, "Ceiling or room fan that can move the air of this room."),
    CONF_AIR_COMPARE: (("sensor",), False, "Second temperature sensor, under the ceiling or at the other end of the room. Only together with a fan."),
}
NUMBER_FIELDS = tuple(f"{side}_{preset}" for side in ("heat", "cool") for preset in ("eco", "comfort", "boost"))
CANDIDATE_DOMAINS = ("climate", "fan", "person", "device_tracker", "input_datetime", "input_boolean")
CANDIDATE_CLASSES = {"sensor": ("temperature", "humidity"), "binary_sensor": ("window", "door", "opening", "occupancy", "presence")}
MAX_CANDIDATES = 400


def candidates(hass: HomeAssistant) -> list[dict[str, str]]:
    """Describe what could be used: names and kinds only, no measured values and no states."""
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    areas = ar.async_get(hass)
    found: list[dict[str, str]] = []
    for state in hass.states.async_all():
        domain = state.domain
        kind = state.attributes.get("device_class")
        # A sleep sensor rarely has a class, its name has to tell
        sleepy = domain == "binary_sensor" and any(word in state.entity_id for word in ("sleep", "schlaf", "focus", "fokus"))
        if not (domain in CANDIDATE_DOMAINS or kind in CANDIDATE_CLASSES.get(domain, ()) or sleepy):
            continue
        entry = entities.async_get(state.entity_id)
        if entry is not None and (entry.platform == DOMAIN or entry.hidden_by or entry.disabled_by):
            continue
        area_id = entry.area_id if entry else None
        if entry is not None and area_id is None and entry.device_id and (device := devices.async_get(entry.device_id)):
            area_id = device.area_id
        area = areas.async_get_area(area_id) if area_id else None
        found.append({"id": state.entity_id, "name": state.name, **({"class": kind} if kind else {}), **({"area": area.name} if area else {})})
    return found[:MAX_CANDIDATES]


def structure() -> dict[str, Any]:
    """Tell the AI what to answer with."""
    fields: dict[str, Any] = {"reason": {"description": "Two sentences on the choice and what is still unclear.", "required": True, "selector": {"text": {"multiline": True}}}}
    for key, (_domains, multiple, purpose) in ENTITY_FIELDS.items():
        fields[key] = {"description": f"{purpose} Leave out if nothing fits.", "required": False, "selector": {"text": {"multiple": multiple}}}
    for key in NUMBER_FIELDS:
        fields[key] = {"description": f"Target in °C for preset {key}.", "required": False, "selector": {"number": {"min": 5, "max": 30, "step": 0.5}}}
    return fields


def clean(hass: HomeAssistant, answer: Any) -> dict[str, Any]:
    """Keep what is known and fits. An AI may invent entities and values, those never reach the form."""
    if not isinstance(answer, dict):
        return {}
    result: dict[str, Any] = {}

    def usable(entity_id: Any, domains: tuple[str, ...]) -> bool:
        state = hass.states.get(entity_id) if isinstance(entity_id, str) else None
        return state is not None and state.domain in domains

    for key, (domains, multiple, _purpose) in ENTITY_FIELDS.items():
        value = answer.get(key)
        if multiple:
            chosen = [e for e in (value if isinstance(value, list) else [value]) if usable(e, domains)]
            if chosen:
                result[key] = list(dict.fromkeys(chosen))
        elif usable(value, domains):
            result[key] = value
    for key in NUMBER_FIELDS:
        value = answer.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 5 <= value <= 30:
            result[key] = float(value)
    return result


async def async_suggest(hass: HomeAssistant, ai_entity: str, room: str, current: dict[str, Any], wish: str) -> tuple[dict[str, Any], str]:
    """Ask the AI. Returns the usable suggestions and its short reason."""
    known = {key: current[key] for key in (*ENTITY_FIELDS, *NUMBER_FIELDS) if current.get(key) not in (None, "", [])}
    language = hass.config.language
    instructions = (
        "You set up a room thermostat in Home Assistant. It regulates radiators and an air conditioner on a separate room sensor.\n"
        f'Room name: "{room}". Pick only entities from the list that belong to this room or to the whole home, judging by name, area and class. '
        "Rather leave a field out than guess. Keep target temperatures unless there is a reason to change them.\n"
        f"Write the reason in the language with the code {language}.\n"
        f"Current settings: {json.dumps(known, ensure_ascii=False)}\n"
        f"Wish of the user: {wish or 'none'}\n"
        f"Entities: {json.dumps(candidates(hass), ensure_ascii=False)}"
    )
    response = await hass.services.async_call(
        "ai_task",
        "generate_data",
        {"task_name": f"ThermGenie {room}", "entity_id": ai_entity, "instructions": instructions, "structure": structure()},
        blocking=True,
        return_response=True,
    )
    answer = (response or {}).get("data")
    reason = answer.get("reason") if isinstance(answer, dict) else ""
    return clean(hass, answer), str(reason or "")
