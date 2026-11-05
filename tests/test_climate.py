"""Tests of the thermostat and its mask."""

from datetime import timedelta
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.core import SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.thermgenie.climate import ThermGenieClimate
from custom_components.thermgenie.const import DOMAIN

ENTITY = "climate.wohnbereich"
WZ = "climate.wz"
KU = "climate.ku"
AC = "climate.ac"
TC = "climate.az"
SENSOR = "sensor.couch"
WINDOW = "binary_sensor.fenster"
OUTDOOR = "sensor.aussen"


class Radio:
    """Records what would go over the radio."""

    def __init__(self):
        self.calls = []
        self.fail = set()

    def setpoints(self, entity):
        return [c[2]["temperature"] for c in self.calls if c[0] == entity and c[1] == "set_temperature"]

    def modes(self, entity):
        return [c[2]["hvac_mode"] for c in self.calls if c[0] == entity and c[1] == "set_hvac_mode"]


@pytest.fixture
async def radio(hass: HomeAssistant):
    """Replace the device commands. The devices follow like real ones."""
    rec = Radio()

    async def _call(self, service, device, data):
        if device.entity_id in rec.fail:
            raise HomeAssistantError("radio dead")
        rec.calls.append((device.entity_id, service, data))
        if service == "set_hvac_mode":
            old = hass.states.get(device.entity_id)
            hass.states.async_set(device.entity_id, data["hvac_mode"], old.attributes)

    with patch.object(ThermGenieClimate, "_async_call", _call):
        yield rec


def devices(hass):
    attrs = {"hvac_modes": ["off", "heat"], "min_temp": 4.5, "max_temp": 30.5}
    hass.states.async_set(WZ, "heat", attrs)
    hass.states.async_set(KU, "heat", attrs)
    hass.states.async_set(AC, "off", {"hvac_modes": ["off", "cool", "heat"], "min_temp": 16, "max_temp": 30})
    hass.states.async_set(TC, "heat", {"hvac_modes": ["heat"], "min_temp": 6.0, "max_temp": 30})
    hass.states.async_set(SENSOR, "21.0")
    hass.states.async_set(WINDOW, "off")
    hass.states.async_set(OUTDOOR, "5")


async def setup(hass, **extra):
    data = {
        "temperature_sensor": SENSOR,
        "heaters": [WZ, KU],
        "cooler": AC,
        "offsets": {WZ: -0.5, KU: 0.0},
        "window_sensor": WINDOW,
        "outdoor_sensor": OUTDOOR,
        **extra,
    }
    entry = MockConfigEntry(domain=DOMAIN, title="Wohnbereich", data=data)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def service(hass, name, **data):
    await hass.services.async_call("climate", name, {"entity_id": ENTITY, **data}, blocking=True)
    await hass.async_block_till_done()


async def test_new_thermostat_starts_off_and_closes_everything(hass, radio):
    devices(hass)
    await setup(hass)
    assert hass.states.get(ENTITY).state == "off"
    assert radio.modes(WZ) == ["off"]
    assert radio.modes(KU) == ["off"]
    assert radio.modes(AC) == []  # already off


async def test_heating_applies_the_offset_per_radiator(hass, radio):
    devices(hass)
    await setup(hass)
    await service(hass, "set_temperature", temperature=21.0)
    radio.calls.clear()
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert radio.setpoints(WZ) == [20.5]  # room is 0.5 K above 20.5, shift rounds back up
    assert radio.setpoints(KU) == [21.0]
    assert radio.modes(AC) == []


async def test_room_below_target_raises_both_commands(hass, radio):
    devices(hass)
    hass.states.async_set(SENSOR, "19.0")
    await setup(hass)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    assert radio.setpoints(KU)[-1] > 21.0
    assert radio.setpoints(WZ)[-1] > 20.5


async def test_cooling_never_touches_heaters_and_vice_versa(hass, radio):
    devices(hass)
    hass.states.async_set(SENSOR, "27.0")
    await setup(hass)
    radio.calls.clear()
    await service(hass, "set_temperature", temperature=24.0, hvac_mode="cool")
    assert radio.modes(AC) == ["cool"]
    assert radio.setpoints(AC)[-1] < 24.0
    assert radio.setpoints(WZ) == []
    assert radio.setpoints(KU) == []


async def test_cooler_started_behind_our_back_in_winter_is_stopped(hass, radio):
    devices(hass)
    await setup(hass)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    radio.calls.clear()
    hass.states.async_set(AC, "cool", hass.states.get(AC).attributes)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert radio.modes(AC) == ["off"]


async def test_valve_without_off_mode_gets_the_lowest_setpoint_once(hass, radio):
    devices(hass)
    await setup(hass, heaters=[TC], cooler=None, offsets={})
    assert radio.setpoints(TC) == [6.0]
    assert radio.modes(TC) == []
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert radio.setpoints(TC) == [6.0]


async def test_dead_device_does_not_block_the_others(hass, radio):
    devices(hass)
    hass.states.async_set(WZ, "unavailable")
    hass.states.async_set(SENSOR, "19.0")
    await setup(hass)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    assert radio.setpoints(WZ) == []
    assert radio.setpoints(KU)
    assert hass.states.get(ENTITY).attributes["devices"][WZ]["available"] is False


async def test_device_gets_its_command_when_it_comes_back(hass, radio):
    devices(hass)
    attrs = hass.states.get(WZ).attributes
    hass.states.async_set(WZ, "unavailable")
    await setup(hass)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    hass.states.async_set(WZ, "heat", attrs)
    await hass.async_block_till_done()
    assert radio.setpoints(WZ)


async def test_failed_command_is_repeated_in_the_next_cycle(hass, radio):
    devices(hass)
    await setup(hass)
    radio.fail.add(KU)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    assert radio.setpoints(WZ)
    assert radio.setpoints(KU) == []
    radio.fail.clear()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert radio.setpoints(KU)


async def test_no_radio_command_while_nothing_changes(hass, radio):
    devices(hass)
    await setup(hass, kp=0.0, ki=0.0)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    radio.calls.clear()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert radio.calls == []


async def test_silent_sensor_falls_back_to_the_plain_target(hass, radio):
    devices(hass)
    hass.states.async_set(SENSOR, "unavailable")
    await setup(hass)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    assert radio.setpoints(KU)[-1] == 21.0
    assert radio.setpoints(WZ)[-1] == 20.5
    assert hass.states.get(ENTITY).attributes["sensor_stale"] is True


async def test_open_window_goes_to_frost_after_the_delay_and_back(hass, radio):
    devices(hass)
    hass.states.async_set(SENSOR, "21.0")
    await setup(hass)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    radio.calls.clear()
    hass.states.async_set(WINDOW, "on")
    await hass.async_block_till_done()
    assert radio.setpoints(KU) == []
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=121))
    await hass.async_block_till_done()
    assert radio.setpoints(KU) == [7.0]
    assert hass.states.get(ENTITY).attributes["blocked_by"] == "window"
    hass.states.async_set(WINDOW, "off")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=152))
    await hass.async_block_till_done()
    assert radio.setpoints(KU)[-1] == 21.0
    assert hass.states.get(ENTITY).attributes["blocked_by"] is None


async def test_warm_day_blocks_heating_only_after_the_hold_time(hass, radio, freezer):
    devices(hass)
    await setup(hass)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(OUTDOOR, "21")

    async def cycles(count):
        for _ in range(count):
            freezer.tick(timedelta(minutes=6))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
            hass.states.async_set(SENSOR, "21.0", force_update=True)

    await cycles(5)
    assert hass.states.get(ENTITY).attributes["blocked_by"] is None
    await cycles(2)
    state = hass.states.get(ENTITY)
    assert state.attributes["blocked_by"] == "outdoor"
    assert state.state == "heat"
    assert hass.states.get(WZ).state == "off"

    # Between the limits the block stays, below the lower limit it ends after the hold time
    hass.states.async_set(OUTDOOR, "18")
    await cycles(7)
    assert hass.states.get(ENTITY).attributes["blocked_by"] == "outdoor"
    hass.states.async_set(OUTDOOR, "16")
    await cycles(7)
    assert hass.states.get(ENTITY).attributes["blocked_by"] is None
    assert hass.states.get(WZ).state == "heat"


async def test_sensor_counts_as_silent_only_after_the_timeout(hass, radio, freezer):
    devices(hass)
    await setup(hass)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    freezer.tick(timedelta(minutes=100))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["sensor_stale"] is False
    # The same value reported again also counts as a sign of life
    hass.states.async_set(SENSOR, "21.0")
    freezer.tick(timedelta(minutes=100))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["sensor_stale"] is False
    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["sensor_stale"] is True


async def test_off_means_no_target_and_no_preset(hass, radio):
    devices(hass)
    await setup(hass)
    await service(hass, "set_preset_mode", preset_mode="eco")
    off = hass.states.get(ENTITY)
    assert (off.state, off.attributes["temperature"], off.attributes["preset_mode"]) == ("off", None, None)
    assert off.attributes["current_temperature"] is not None
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    on = hass.states.get(ENTITY)
    assert (on.attributes["temperature"], on.attributes["preset_mode"]) == (19.0, "eco")


async def test_setup_wizard_stays_short(hass, radio):
    devices(hass)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert flow["step_id"] == "user"

    bad = await hass.config_entries.flow.async_configure(flow["flow_id"], {"name": "Wohnbereich", "temperature_sensor": SENSOR})
    assert bad["errors"] == {"base": "no_device"}

    page = await hass.config_entries.flow.async_configure(flow["flow_id"], {"name": "Wohnbereich", "temperature_sensor": SENSOR, "heaters": [WZ, KU], "cooler": AC})
    assert page["step_id"] == "offsets"
    page = await hass.config_entries.flow.async_configure(flow["flow_id"], {"offset_1": -0.5, "kd_1": 0.8, "offset_2": 0.0, "kd_2": 0.4})
    assert page["step_id"] == "outdoor"
    page = await hass.config_entries.flow.async_configure(flow["flow_id"], {"outdoor_off_above": 20, "outdoor_on_below": 17})
    assert page["step_id"] == "presets"
    page = await hass.config_entries.flow.async_configure(flow["flow_id"], {"heating": {"heat_eco": 19}, "cooling": {}})
    assert page["step_id"] == "routines"
    done = await hass.config_entries.flow.async_configure(flow["flow_id"], {"messages": {}, "daily": {"wake_entity": "input_datetime.wecker"}, "way_home": {}})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["title"] == "Wohnbereich"
    assert done["data"]["offsets"] == {WZ: -0.5, KU: 0.0}
    assert done["data"]["kd_heaters"] == {WZ: 0.8, KU: 0.4}
    assert done["data"]["heat_eco"] == 19
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["hvac_modes"][:3] == ["off", "heat", "cool"]


async def _page(hass, flow, step):
    return await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": step})


async def test_settings_menu_reaches_every_page_and_saves_at_the_end(hass, radio):
    devices(hass)
    entry = await setup(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] is FlowResultType.MENU
    assert flow["menu_options"] == ["devices", "outdoor", "presets", "regulation", "routines", "air", "lock", "valves", "summer", "save"]

    page = await _page(hass, flow, "regulation")
    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"heating": {"kp": 0.4}, "learning": {"learn": True}, "cooling": {"reference_cool": "humidex"}, "timing": {}})
    assert page["type"] is FlowResultType.MENU
    page = await _page(hass, flow, "routines")
    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"messages": {"notify_service": "notify.handy"}, "daily": {"wake_fallback": "07:15:00"}, "way_home": {}})
    page = await _page(hass, flow, "lock")
    bad = await hass.config_entries.options.async_configure(flow["flow_id"], {"lock_enabled": True, "lock_frost_on": 8, "lock_frost_off": 6})
    assert bad["errors"] == {"base": "frost_limits"}
    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"lock_enabled": True})
    page = await _page(hass, flow, "valves")
    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"hold_devices": True, "valve_1": "sensor.ventil"})
    page = await _page(hass, flow, "summer")
    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"heat_guard": {}, "drying": {}, "cascade": {"cascade_fan": "fan.nacht"}, "cascade_fine": {}})
    done = await _page(hass, flow, "save")
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["data"]["kp"] == 0.4
    assert done["data"]["reference_cool"] == "humidex"
    assert done["data"]["lock_enabled"] is True
    assert done["data"]["hold_devices"] is True
    assert done["data"]["valves"] == {WZ: "sensor.ventil"}
    assert done["data"]["cascade_fan"] == "fan.nacht"


async def test_settings_can_empty_an_optional_field(hass, radio):
    devices(hass)
    entry = await setup(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    page = await _page(hass, flow, "devices")
    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"temperature_sensor": SENSOR, "heaters": [KU]})
    assert page["type"] is FlowResultType.MENU
    assert "summer" not in page["menu_options"]
    page = await _page(hass, flow, "outdoor")
    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"outdoor_off_above": 20, "outdoor_on_below": 17})
    done = await _page(hass, flow, "save")
    assert "cooler" not in done["data"]
    assert "outdoor_sensor" not in done["data"]
    assert "window_sensor" not in done["data"]


async def test_learning_measures_against_the_heater_that_closes_first(hass, radio):
    devices(hass)
    await setup(hass, learn=True)
    climate = hass.data["climate"].get_entity(ENTITY)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    with patch.object(climate._phase, "update", return_value=None) as update:
        climate._track_phase()
    assert update.call_args.args[2] == climate.active_target - 0.5


async def test_the_mode_alone_decides_between_heating_and_cooling(hass, radio):
    devices(hass)
    await setup(hass)
    assert hass.states.get(ENTITY).attributes["hvac_modes"][:3] == ["off", "heat", "cool"]
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    radio.calls.clear()
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    state = hass.states.get(ENTITY)
    assert state.state == "cool"
    assert radio.modes(WZ) == ["off"]
    assert radio.modes(KU) == ["off"]
    assert radio.modes(AC) == ["cool"]


async def test_each_mode_keeps_its_own_target_also_while_off(hass, radio):
    devices(hass)
    await setup(hass)
    await service(hass, "set_temperature", temperature=22.0, hvac_mode="heat")
    await service(hass, "set_temperature", temperature=25.0, hvac_mode="cool")
    await service(hass, "set_hvac_mode", hvac_mode="off")
    state = hass.states.get(ENTITY)
    assert state.attributes["profile"] == "cool"
    assert state.attributes["profiles"]["heat"]["target"] == 22.0
    assert state.attributes["profiles"]["cool"]["target"] == 25.0
    await service(hass, "turn_on")
    assert hass.states.get(ENTITY).state == "cool"
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert hass.states.get(ENTITY).attributes["temperature"] == 22.0


async def test_preset_uses_the_value_of_the_mode(hass, radio):
    devices(hass)
    await setup(hass)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    await service(hass, "set_preset_mode", preset_mode="eco")
    assert hass.states.get(ENTITY).attributes["profiles"]["heat"]["target"] == 19.0
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    assert "frost" not in hass.states.get(ENTITY).attributes["preset_modes"]
    await service(hass, "set_preset_mode", preset_mode="eco")
    assert hass.states.get(ENTITY).attributes["profiles"]["cool"]["target"] == 26.0


async def test_old_entries_lose_the_season(hass, radio):
    devices(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Wohnbereich", version=1, data={"temperature_sensor": SENSOR, "heaters": [WZ], "season_entity": "input_select.x"}, options={"winter_state": "Winter", "season_auto_on": True})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 3
    assert "season_entity" not in entry.data
    assert entry.options == {}


def _config_entities(hass, entry):
    registry = er.async_get(hass)
    return {e.translation_key or e.unique_id: e for e in er.async_entries_for_config_entry(registry, entry.entry_id) if e.entity_category is EntityCategory.CONFIG}


async def _set_number(hass, entry, key, value):
    entity = _config_entities(hass, entry)[key]
    await hass.services.async_call("number", "set_value", {"entity_id": entity.entity_id, "value": value}, blocking=True)
    await hass.async_block_till_done()


async def test_settings_are_entities_on_the_device_page(hass, radio):
    devices(hass)
    entry = await setup(hass)
    entities = _config_entities(hass, entry)
    assert {"heat_comfort", "cool_comfort", "outdoor_off_above", "heater_offset", "hold_devices"} <= set(entities)
    assert "wake_lead_min" not in entities  # nothing set up to wake for
    assert "lock_frost_on" not in entities
    assert entities["kp"].disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entities["heat_comfort"].disabled_by is None
    assert hass.states.get(entities["heat_comfort"].entity_id).state == "21.0"
    assert er.async_get(hass).async_get(ENTITY).device_id == entities["heat_comfort"].device_id


async def test_a_locked_room_offers_nothing_about_its_heating(hass, radio):
    devices(hass)
    entry = await setup(hass, lock_enabled=True)
    entities = _config_entities(hass, entry)
    assert "heat_comfort" not in entities
    assert "kp" not in entities
    assert "heater_offset" not in entities
    assert "hold_devices" not in entities
    assert "cool_comfort" in entities


async def test_a_changed_setting_applies_without_a_new_setup(hass, radio):
    devices(hass)
    entry = await setup(hass)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    climate = hass.data["climate"].get_entity(ENTITY)
    climate._devices[0].regulator.integral = 3.5
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "comfort"

    await _set_number(hass, entry, "heat_comfort", 22.5)
    assert entry.options["heat_comfort"] == 22.5
    assert hass.data["climate"].get_entity(ENTITY) is climate
    assert climate._devices[0].regulator.integral == pytest.approx(3.5, abs=0.01)
    assert hass.states.get(ENTITY).attributes["temperature"] == 22.5
    assert hass.states.get(ENTITY).attributes["presets"]["heat_comfort"] == 22.5


async def test_a_radiator_offset_reaches_the_regulation(hass, radio):
    devices(hass)
    entry = await setup(hass)
    registry = er.async_get(hass)
    entity = registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_heater_offset_{KU}")
    await hass.services.async_call("number", "set_value", {"entity_id": entity, "value": 1.5}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["offsets"][KU] == 1.5
    assert entry.options["offsets"][WZ] == -0.5
    climate = hass.data["climate"].get_entity(ENTITY)
    assert [d.offset for d in climate._devices if d.entity_id == KU] == [1.5]


async def test_limits_have_to_stay_in_order(hass, radio):
    devices(hass)
    entry = await setup(hass)
    with pytest.raises(ServiceValidationError):
        await _set_number(hass, entry, "outdoor_on_below", 25)
    assert "outdoor_on_below" not in entry.options


async def test_a_setting_that_needs_it_sets_the_thermostat_up_again(hass, radio):
    devices(hass)
    entry = await setup(hass)
    climate = hass.data["climate"].get_entity(ENTITY)
    registry = er.async_get(hass)
    registry.async_update_entity(_config_entities(hass, entry)["period_min"].entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    climate = hass.data["climate"].get_entity(ENTITY)
    await _set_number(hass, entry, "period_min", 10)
    assert hass.data["climate"].get_entity(ENTITY) is not climate
    assert hass.data["climate"].get_entity(ENTITY).conf["period_min"] == 10


async def test_comfort_values_and_diagnosis_are_sensors(hass, radio):
    devices(hass)
    hass.states.async_set("sensor.feuchte", "50")
    entry = await setup(hass, humidity_sensor="sensor.feuchte")
    registry = er.async_get(hass)
    humidex = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_dew_point")
    assert registry.async_get(humidex).entity_category is None
    assert float(hass.states.get(humidex).state) == hass.states.get(ENTITY).attributes["dew_point"]
    blocked = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_blocked_by")
    assert registry.async_get(blocked).entity_category is EntityCategory.DIAGNOSTIC
    assert hass.states.get(blocked).state == "none"
    command = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_device_command_{WZ}")
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert hass.states.get(command).state != "unknown"


async def test_routine_switch_and_service_stay_the_same(hass, radio):
    devices(hass)
    hass.states.async_set("input_boolean.schlaf", "off")
    entry = await setup(hass, sleep_entity="input_boolean.schlaf")
    switch = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_routine_sleep")
    assert hass.states.get(switch).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["routines_off"] == ["sleep"]
    await hass.services.async_call(DOMAIN, "set_routine", {"entity_id": ENTITY, "routine": "sleep", "enabled": True}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(switch).state == "on"


async def test_what_no_longer_applies_leaves_the_device_page(hass, radio):
    devices(hass)
    entry = await setup(hass)
    assert "outdoor_off_above" in _config_entities(hass, entry)
    data = {k: v for k, v in entry.data.items() if k != "outdoor_sensor"}
    hass.config_entries.async_update_entry(entry, data=data)
    await hass.async_block_till_done()
    assert "outdoor_off_above" not in _config_entities(hass, entry)


async def test_heating_uses_the_radiators_unless_chosen_otherwise(hass, radio):
    devices(hass)
    await setup(hass)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert radio.setpoints(WZ)
    assert radio.modes(AC) == []
    assert radio.setpoints(AC) == []


async def test_heating_with_the_air_conditioner_only(hass, radio):
    devices(hass)
    await setup(hass, heat_source="air_conditioner")
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert radio.modes(AC)[-1] == "heat"
    assert radio.setpoints(AC)
    assert radio.setpoints(WZ) == []
    assert hass.states.get(WZ).state == "off"
    # Too cold in the room: the air conditioner gets a raised setpoint like a radiator would
    assert radio.setpoints(AC)[-1] >= hass.states.get(ENTITY).attributes["temperature"] - 0.5


async def test_heating_with_both_and_cooling_is_not_affected(hass, radio):
    devices(hass)
    await setup(hass, heat_source="both")
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert radio.setpoints(WZ)
    assert radio.modes(AC)[-1] == "heat"
    radio.calls.clear()
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    assert radio.modes(AC)[-1] == "cool"
    assert radio.setpoints(WZ) == []
    assert hass.states.get(WZ).state == "off"


async def test_an_air_conditioner_that_cannot_heat_leaves_it_to_the_radiators(hass, radio):
    devices(hass)
    hass.states.async_set(AC, "off", {"hvac_modes": ["off", "cool"], "min_temp": 16, "max_temp": 30})
    await setup(hass, heat_source="air_conditioner")
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert radio.setpoints(WZ)
    assert radio.modes(AC) == []


async def test_the_heat_source_can_be_changed_while_heating(hass, radio):
    devices(hass)
    entry = await setup(hass)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert radio.modes(AC) == []
    select = _config_entities(hass, entry)["heat_source"].entity_id
    assert hass.states.get(select).state == "radiators"
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "both"}, blocking=True)
    await hass.async_block_till_done()
    assert radio.modes(AC)[-1] == "heat"


async def _touch(hass, entity, state, **attributes):
    """Somebody turns the device by hand."""
    hass.states.async_set(entity, state, {**hass.states.get(entity).attributes, **attributes})
    await hass.async_block_till_done()


async def test_devices_are_left_alone_unless_they_are_held(hass, radio, freezer):
    devices(hass)
    await setup(hass)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    freezer.tick(120)
    radio.calls.clear()
    await _touch(hass, WZ, "heat", temperature=28)
    assert radio.setpoints(WZ) == []


async def test_a_held_device_is_set_back_at_once(hass, radio, freezer):
    devices(hass)
    await setup(hass, hold_devices=True)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    command = hass.data["climate"].get_entity(ENTITY)._devices[0].command
    hass.states.async_set(WZ, "heat", {**hass.states.get(WZ).attributes, "temperature": command})
    freezer.tick(120)
    await hass.async_block_till_done()
    radio.calls.clear()

    await _touch(hass, WZ, "heat", temperature=28)
    assert radio.setpoints(WZ)
    assert radio.setpoints(WZ)[-1] != 28


async def test_our_own_echo_is_not_a_change_by_hand(hass, radio, freezer):
    devices(hass)
    await setup(hass, hold_devices=True)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    climate = hass.data["climate"].get_entity(ENTITY)
    command = climate._devices[0].command
    radio.calls.clear()
    # The old value comes in late, then the value we sent, rounded by the device
    await _touch(hass, WZ, "heat", temperature=19)
    assert radio.setpoints(WZ) == []
    freezer.tick(120)
    await _touch(hass, WZ, "heat", temperature=command + 0.2, target_temp_step=0.5)
    assert radio.setpoints(WZ) == []


async def test_turning_a_knob_on_is_set_back_too_without_flooding_the_radio(hass, radio, freezer):
    devices(hass)
    await setup(hass, hold_devices=True)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    freezer.tick(120)
    radio.calls.clear()
    await _touch(hass, WZ, "heat", temperature=26)
    assert len(radio.setpoints(WZ)) == 1

    # The next steps come right behind the correction: nothing goes out yet, nothing gets lost either
    await _touch(hass, WZ, "heat", temperature=27)
    await _touch(hass, WZ, "heat", temperature=28)
    assert len(radio.setpoints(WZ)) == 1
    freezer.tick(31)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(radio.setpoints(WZ)) == 2


async def _ai_flow(hass, entry, answer):
    async def _generate(call):
        _ai_flow.call = call
        return {"data": answer, "conversation_id": "x"}

    hass.services.async_register("ai_task", "generate_data", _generate, supports_response=SupportsResponse.ONLY)
    hass.states.async_set("ai_task.helper", "unknown")
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["menu_options"][0] == "ai"
    await _page(hass, flow, "ai")
    return flow, await hass.config_entries.options.async_configure(flow["flow_id"], {"ai_entity": "ai_task.helper", "wish": "warm"})


async def test_ai_suggestions_only_fill_a_form(hass, radio):
    devices(hass)
    hass.states.async_set("sensor.wz_temp", "21", {"device_class": "temperature", "friendly_name": "Wohnzimmer"})
    hass.states.async_set("sensor.wz_feucht", "50", {"device_class": "humidity"})
    entry = await setup(hass)
    answer = {"reason": "Passt zum Raum.", "temperature_sensor": "sensor.wz_temp", "cooler": "sensor.wz_feucht", "humidity_sensor": "sensor.erfunden", "heat_comfort": 21.5, "heat_eco": 99, "kp": 5}
    flow, page = await _ai_flow(hass, entry, answer)
    assert page["step_id"] == "ai_review"
    assert page["description_placeholders"]["reason"] == "Passt zum Raum."
    shown = {str(key): key.description["suggested_value"] for key in page["data_schema"].schema}
    assert shown == {"temperature_sensor": "sensor.wz_temp", "heat_comfort": 21.5}
    sent = _ai_flow.call.data["instructions"]
    assert "sensor.wz_temp" in sent and '"21"' not in sent
    assert entry.options == {}

    page = await hass.config_entries.options.async_configure(flow["flow_id"], {"temperature_sensor": "sensor.wz_temp"})
    assert page["type"] is FlowResultType.MENU
    assert entry.options == {}
    done = await _page(hass, flow, "save")
    assert done["data"]["temperature_sensor"] == "sensor.wz_temp"
    assert "heat_comfort" not in done["data"]


async def test_ai_without_anything_usable_stays_on_the_page(hass, radio):
    devices(hass)
    entry = await setup(hass)
    _flow, page = await _ai_flow(hass, entry, {"reason": "?", "temperature_sensor": "sensor.erfunden"})
    assert page["step_id"] == "ai"
    assert page["errors"] == {"base": "ai_empty"}


def test_ai_structure_uses_valid_selectors():
    from custom_components.thermgenie.ai import structure

    for field in structure().values():
        assert selector.selector(field["selector"])


async def test_the_card_learns_what_the_room_is_regulated_on(hass, radio):
    devices(hass)
    await setup(hass, humidity_sensor=SENSOR, reference_heat="comfort", reference_cool="humidex")
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert hass.states.get(ENTITY).attributes["reference"] == "comfort"
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    assert hass.states.get(ENTITY).attributes["reference"] == "humidex"
