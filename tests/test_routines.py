"""Tests of the humidity values, routines, cascade, learning and heating lock in the running thermostat."""

from pytest_homeassistant_custom_component.common import async_mock_service
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import ServiceValidationError
from homeassistant.components.climate import HVACMode
from custom_components.thermgenie.messages import say
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.thermgenie.climate import ThermGenieClimate
from custom_components.thermgenie.const import DOMAIN

from .test_climate import AC, ENTITY, KU, OUTDOOR, SENSOR, WINDOW, WZ, devices, radio, service, setup  # noqa: F401

SZ = "climate.sz"
SZ_ENTITY = "climate.schlafzimmer"
VALVE = "sensor.ventil"
HUM = "sensor.feuchte"
PERSON = "person.bewohner"
SLEEP = "binary_sensor.schlaf"
FOCUS = "binary_sensor.fokus"
FAN = "fan.nacht"
NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
LOCAL_NOON = datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)  # the test clock runs on US/Pacific


@pytest.fixture
def pushes(hass):
    messages = []

    async def _handler(call):
        messages.append(call.data)

    hass.services.async_register("notify", "handy", _handler)
    hass.services.async_register("notify", "echo", _handler)
    return messages


def fans(hass):
    seen = []

    async def _handler(call):
        seen.append((call.service, dict(call.data)))

    hass.services.async_register("fan", "set_percentage", _handler)
    hass.services.async_register("fan", "turn_off", _handler)
    return seen


async def tick(hass, freezer, minutes=2):
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def _cooled_before(hass):
    """Cooling was the last thing the room did, so the summer routines apply while it is off."""
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    await service(hass, "set_hvac_mode", hvac_mode="off")


@pytest.fixture(autouse=True)
def _german(hass):
    hass.config.language = "de"


async def test_humidex_is_the_reference_for_cooling_only(hass, radio):
    devices(hass)
    hass.states.async_set(HUM, "47")
    hass.states.async_set(SENSOR, "21.5")
    await setup(hass, humidity_sensor=HUM, reference_cool="humidex")
    state = hass.states.get(ENTITY)
    assert state.attributes["current_temperature"] == 21.5
    assert state.attributes["humidex"] == pytest.approx(22.66, abs=0.01)
    assert state.attributes["dew_point"] == pytest.approx(9.73, abs=0.01)
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    assert hass.states.get(ENTITY).attributes["current_temperature"] == 22.7


async def test_drying_passes_through_and_stops_on_an_open_window(hass, radio):
    devices(hass)
    hass.states.async_set(AC, "off", {"hvac_modes": ["off", "cool", "dry"], "min_temp": 16, "max_temp": 30})
    await setup(hass, window_open_delay=0)
    assert "dry" in hass.states.get(ENTITY).attributes["hvac_modes"]
    assert "fan_only" not in hass.states.get(ENTITY).attributes["hvac_modes"]
    await service(hass, "set_hvac_mode", hvac_mode="dry")
    assert radio.modes(AC) == ["dry"]
    assert hass.states.get(ENTITY).attributes["hvac_action"] == "drying"
    hass.states.async_set(WINDOW, "on")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert radio.modes(AC)[-1] == "off"


async def test_each_heater_has_its_own_brake(hass, radio):
    devices(hass)
    await setup(hass, kd_heaters={WZ: 0.8, KU: 0.4}, kd=0.1)
    climate = hass.data["climate"].get_entity(ENTITY)
    assert {d.entity_id: d.kd for d in climate._devices}[WZ] == 0.8
    assert {d.entity_id: d.kd for d in climate._devices}[KU] == 0.4


async def test_device_temperature_converts_the_setpoint(hass, radio):
    devices(hass)
    hass.states.async_set(WZ, "heat", {"hvac_modes": ["off", "heat"], "min_temp": 5, "max_temp": 30, "current_temperature": 24.0})
    hass.states.async_set(SENSOR, "21.0")
    await setup(hass, heaters=[WZ], offsets={}, cooler=None, use_device_temp=True)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    assert radio.setpoints(WZ)[-1] == 24.0


async def test_fan_turns_up_while_far_from_the_target(hass, radio):
    devices(hass)
    hass.states.async_set(AC, "cool", {"hvac_modes": ["off", "cool"], "min_temp": 16, "max_temp": 30, "fan_mode": "auto", "fan_modes": ["auto", "high"]})
    hass.states.async_set(SENSOR, "28.0")
    await setup(hass, fan_boost=True, kp_cool=0.0, ki_cool=0.0)
    await service(hass, "set_temperature", temperature=24.0, hvac_mode="cool")
    assert [c[2]["fan_mode"] for c in radio.calls if c[1] == "set_fan_mode"] == ["high"]


async def test_sleep_and_absence_follow_the_preset_in_winter_only(hass, radio):
    devices(hass)
    hass.states.async_set(PERSON, "home")
    hass.states.async_set(SLEEP, "off")
    await setup(hass, presence_entity=PERSON, sleep_entity=SLEEP)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "comfort"
    hass.states.async_set(SLEEP, "on")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "eco"
    hass.states.async_set(SLEEP, "off")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "comfort"
    hass.states.async_set(PERSON, "not_home")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "eco"
    hass.states.async_set(PERSON, "home")
    hass.states.async_set(SLEEP, "on")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["profiles"]["cool"]["preset"] == "comfort"


async def test_wake_up_heats_before_the_alarm(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    wake = NOW + timedelta(minutes=50)
    hass.states.async_set("input_datetime.wecker", "x", {"timestamp": wake.timestamp()})
    await setup(hass, wake_entity="input_datetime.wecker", period_min=2)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    await service(hass, "set_preset_mode", preset_mode="eco")
    await tick(hass, freezer)
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "eco"
    await tick(hass, freezer, 2)
    await tick(hass, freezer, 2)
    await tick(hass, freezer, 2)
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "comfort"


async def test_the_card_tells_the_alarm_from_the_fixed_time(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    hass.states.async_set("input_datetime.wecker", "x", {"timestamp": (NOW - timedelta(hours=1)).timestamp()})
    await setup(hass, wake_entity="input_datetime.wecker", wake_fallback="07:15:00", wake_fallback_on=True)
    status = hass.states.get(ENTITY).attributes["routines"]
    assert status["wake_alarm"] is False
    assert dt_util.as_local(dt_util.parse_datetime(status["wake_at"])).strftime("%H:%M") == "07:15"
    alarm = NOW + timedelta(minutes=30)
    hass.states.async_set("input_datetime.wecker", "x", {"timestamp": alarm.timestamp()})
    await hass.async_block_till_done()
    status = hass.states.get(ENTITY).attributes["routines"]
    assert status["wake_alarm"] is True
    assert dt_util.parse_datetime(status["wake_at"]) == alarm - timedelta(minutes=45)


async def test_no_fixed_time_unless_wanted(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    hass.states.async_set("input_datetime.wecker", "x", {"timestamp": (NOW - timedelta(days=2)).timestamp()})
    await setup(hass, wake_entity="input_datetime.wecker", wake_fallback=(dt_util.as_local(NOW) + timedelta(minutes=3)).strftime("%H:%M:00"), period_min=2)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    await service(hass, "set_preset_mode", preset_mode="eco")
    for _ in range(4):
        await tick(hass, freezer, 2)
    state = hass.states.get(ENTITY)
    assert state.attributes["preset_mode"] == "eco"
    assert state.attributes["routines"]["wake_at"] is None


async def test_fixed_time_from_an_entity_goes_first_and_heats(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    soon = dt_util.as_local(NOW) + timedelta(minutes=3)
    hass.states.async_set("input_datetime.morgens", "x", {"hour": soon.hour, "minute": soon.minute})
    await setup(hass, wake_fallback_on=True, wake_fallback_entity="input_datetime.morgens", wake_fallback="01:00:00", period_min=2)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    await service(hass, "set_preset_mode", preset_mode="eco")
    for _ in range(4):
        await tick(hass, freezer, 2)
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "comfort"


async def test_an_alarm_that_rang_today_replaces_the_fixed_time(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    local = dt_util.as_local(NOW)
    hass.states.async_set("input_datetime.wecker", "x", {"timestamp": (NOW - timedelta(minutes=1)).timestamp()})
    await setup(hass, wake_entity="input_datetime.wecker", wake_fallback_on=True, wake_fallback=(local + timedelta(minutes=3)).strftime("%H:%M:00"), period_min=2)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    await service(hass, "set_preset_mode", preset_mode="eco")
    for _ in range(4):
        await tick(hass, freezer, 2)
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "eco"


async def test_air_runs_while_heating_only_on_a_difference(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    on = async_mock_service(hass, "fan", "turn_on")
    off = async_mock_service(hass, "fan", "turn_off")
    hass.states.async_set("fan.decke", "off")
    hass.states.async_set("sensor.oben", "21.5")
    await setup(hass, air_fan="fan.decke", air_compare_sensor="sensor.oben", air_percent=25, period_min=2)
    await service(hass, "set_temperature", temperature=24.0, hvac_mode="heat")
    await tick(hass, freezer, 2)
    assert not on
    hass.states.async_set("sensor.oben", "23.0")
    await tick(hass, freezer, 2)
    assert on[-1].data == {"entity_id": "fan.decke", "percentage": 25}
    assert hass.states.get(ENTITY).attributes["routines"]["air"] is True
    hass.states.async_set("fan.decke", "on")
    hass.states.async_set("sensor.oben", "21.2")
    await tick(hass, freezer, 2)
    assert off


async def test_air_leaves_a_fan_alone_that_was_on_before(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    on = async_mock_service(hass, "fan", "turn_on")
    off = async_mock_service(hass, "fan", "turn_off")
    hass.states.async_set("fan.decke", "on")
    await setup(hass, air_fan="fan.decke", period_min=2)
    await service(hass, "set_temperature", temperature=24.0, hvac_mode="heat")
    await tick(hass, freezer, 2)
    await service(hass, "set_hvac_mode", hvac_mode="off")
    await tick(hass, freezer, 2)
    assert not on and not off


async def test_messages_follow_the_system_language(hass):
    hass.config.language = "de"
    assert say(hass, "dry_title") == "Entfeuchten beendet"
    hass.config.language = "fr"
    assert say(hass, "dry_title") == "Drying stopped"


async def test_the_card_sees_what_the_routines_do(hass, radio, freezer):
    devices(hass)
    hass.states.async_set(PERSON, "not_home")
    hass.states.async_set(SLEEP, "off")
    hass.states.async_set("sensor.richtung", "towards")
    hass.states.async_set("sensor.distanz", "30000")
    freezer.move_to(NOW)
    wake = NOW + timedelta(minutes=50)
    hass.states.async_set("input_datetime.wecker", "x", {"timestamp": wake.timestamp()})
    await setup(hass, presence_entity=PERSON, sleep_entity=SLEEP, wake_entity="input_datetime.wecker", approach_direction="sensor.richtung", approach_distance="sensor.distanz", boost_minutes=10)
    status = hass.states.get(ENTITY).attributes["routines"]
    assert status["sleep"] == "away"
    assert status["way_home"] is False
    assert dt_util.parse_datetime(status["wake_at"]) == wake - timedelta(minutes=45)
    await service(hass, "set_preset_mode", preset_mode="boost")
    status = hass.states.get(ENTITY).attributes["routines"]
    assert dt_util.parse_datetime(status["boost_until"]) == NOW + timedelta(minutes=10)
    await service(hass, "set_preset_mode", preset_mode="eco")
    assert "boost_until" not in hass.states.get(ENTITY).attributes["routines"]


async def test_way_home_heats_once_and_leaves_manual_changes_alone(hass, radio):
    devices(hass)
    hass.states.async_set(PERSON, "not_home")
    hass.states.async_set("sensor.richtung", "stationary")
    hass.states.async_set("sensor.distanz", "30000")
    await setup(hass, presence_entity=PERSON, approach_direction="sensor.richtung", approach_distance="sensor.distanz", approach_target=21.5, kp=0.0, ki=0.0)
    hass.states.async_set("sensor.richtung", "towards")
    hass.states.async_set("sensor.distanz", "15000")
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert (state.state, state.attributes["temperature"]) == ("heat", 21.5)
    await service(hass, "set_temperature", temperature=20.0)
    hass.states.async_set("sensor.distanz", "12000")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["temperature"] == 20.0


async def test_boost_ends_after_its_time(hass, radio, freezer):
    devices(hass)
    freezer.move_to(NOW)
    await setup(hass, boost_minutes=10, cool_boost=16, cool_comfort=24.5)
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    await service(hass, "set_preset_mode", preset_mode="boost")
    assert hass.states.get(ENTITY).attributes["temperature"] == 16
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert (state.attributes["preset_mode"], state.attributes["temperature"]) == ("comfort", 24.5)


async def test_heat_guard_starts_the_cooler_when_hot_and_on_the_way(hass, radio, freezer, pushes):
    devices(hass)
    freezer.move_to(LOCAL_NOON)
    hass.states.async_set(PERSON, "not_home")
    hass.states.async_set("sensor.gefuehlt", "25")
    hass.states.async_set("sensor.distanz", "50000")
    await setup(hass, presence_entity=PERSON, guard_sensor="sensor.gefuehlt", guard_distance="sensor.distanz", notify_service="notify.handy", period_min=5)
    await _cooled_before(hass)
    for _ in range(4):
        await tick(hass, freezer, 5)
    assert hass.states.get(ENTITY).state == "off"  # the off time has to pass
    for _ in range(3):
        await tick(hass, freezer, 5)
    state = hass.states.get(ENTITY)
    assert (state.state, state.attributes["preset_mode"]) == ("cool", "eco")
    assert [p["title"] for p in pushes] == ["Klima automatisch gestartet"]
    await service(hass, "set_hvac_mode", hvac_mode="off")
    for _ in range(8):
        await tick(hass, freezer, 5)
    assert hass.states.get(ENTITY).state == "off"  # cooldown


async def test_heat_guard_waits_while_the_heating_settings_are_in_use(hass, radio, freezer, pushes):
    devices(hass)
    freezer.move_to(LOCAL_NOON)
    hass.states.async_set(PERSON, "not_home")
    hass.states.async_set("sensor.gefuehlt", "25")
    hass.states.async_set("sensor.distanz", "50000")
    await setup(hass, presence_entity=PERSON, guard_sensor="sensor.gefuehlt", guard_distance="sensor.distanz", notify_service="notify.handy")
    for _ in range(8):
        await tick(hass, freezer, 5)
    assert hass.states.get(ENTITY).state == "off"


async def test_heat_guard_stays_off_with_somebody_at_home(hass, radio, freezer):
    devices(hass)
    freezer.move_to(LOCAL_NOON)
    hass.states.async_set(PERSON, "home")
    hass.states.async_set("sensor.gefuehlt", "25")
    hass.states.async_set("sensor.distanz", "50000")
    await setup(hass, presence_entity=PERSON, guard_sensor="sensor.gefuehlt", guard_distance="sensor.distanz")
    await _cooled_before(hass)
    for _ in range(12):
        await tick(hass, freezer, 5)
    assert hass.states.get(ENTITY).state == "off"


async def test_drying_stops_at_the_limit_after_the_hold_time(hass, radio, freezer, pushes):
    devices(hass)
    hass.states.async_set(AC, "off", {"hvac_modes": ["off", "cool", "dry"], "min_temp": 16, "max_temp": 30})
    freezer.move_to(NOW)
    hass.states.async_set("sensor.tau", "8")
    await setup(hass, dry_dew_sensor="sensor.tau", notify_service="notify.handy")
    await service(hass, "set_hvac_mode", hvac_mode="dry")
    await tick(hass, freezer, 5)
    await tick(hass, freezer, 5)
    assert hass.states.get(ENTITY).state == "dry"
    for _ in range(4):
        await tick(hass, freezer, 5)
    assert hass.states.get(ENTITY).state == "off"
    assert pushes[-1]["title"] == "Entfeuchten beendet"


def cascade_entities(hass, fan_pct=30):
    hass.states.async_set(PERSON, "home")
    hass.states.async_set(FOCUS, "off")
    hass.states.async_set(FAN, "on", {"percentage": fan_pct})
    hass.states.async_set("sensor.bett_gefuehlt", "24.4")
    hass.states.async_set("sensor.bett", "23.0")


CASCADE = {
    "presence_entity": PERSON,
    "cascade_focus": FOCUS,
    "cascade_fan": FAN,
    "cascade_felt": "sensor.bett_gefuehlt",
    "cascade_real": "sensor.bett",
    "cool_comfort": 24.5,
}


async def test_cascade_drives_the_fan_and_steps_the_cooler_every_quarter(hass, radio, freezer):
    devices(hass)
    freezer.move_to(datetime(2026, 7, 1, 23, 10, 30, tzinfo=timezone.utc))
    cascade_entities(hass)
    seen = fans(hass)
    await setup(hass, **CASCADE, kp_cool=0.0, ki_cool=0.0)
    await service(hass, "set_hvac_mode", hvac_mode="cool")
    hass.states.async_set(FOCUS, "on")
    await hass.async_block_till_done()
    assert seen[-1] == ("set_percentage", {"entity_id": FAN, "percentage": 60})
    assert isinstance(seen[-1][1]["percentage"], int)
    assert hass.states.get(ENTITY).attributes["temperature"] == 24.5  # not on a quarter
    hass.states.async_set(FAN, "on", {"percentage": 60})
    freezer.move_to(datetime(2026, 7, 1, 23, 15, 0, tzinfo=timezone.utc))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["temperature"] == 24.0


async def test_cascade_morning_in_winter_leaves_the_heating_alone(hass, radio, freezer):
    devices(hass)
    freezer.move_to(datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc))
    cascade_entities(hass)
    seen = fans(hass)
    await setup(hass, **CASCADE)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(FOCUS, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(hours=7))
    hass.states.async_set(FOCUS, "off")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "heat"
    assert seen[-1][0] == "turn_off"


async def test_cascade_morning_in_summer_hands_back_the_room(hass, radio, freezer):
    devices(hass)
    freezer.move_to(datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc))
    cascade_entities(hass)
    seen = fans(hass)
    await setup(hass, **CASCADE, kp_cool=0.0, ki_cool=0.0)
    await service(hass, "set_temperature", temperature=22.0, hvac_mode="cool")
    hass.states.async_set(FOCUS, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(hours=7))
    hass.states.async_set(FOCUS, "off")
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert (state.state, state.attributes["profiles"]["cool"]["target"]) == ("off", 24.5)
    assert seen[-1][0] == "turn_off"


async def test_learning_uses_the_factor_of_the_flow_range_and_stores_it(hass, radio, freezer):
    devices(hass)
    hass.config.language = "en"
    freezer.move_to(NOW)
    hass.states.async_set("sensor.vorlauf", "65")
    hass.states.async_set(SENSOR, "20.0")
    entry = await setup(hass, learn=True, flow_sensor="sensor.vorlauf", kd=0.5, kd_heaters={WZ: 0.8, KU: 0.4}, offsets={WZ: 0.0, KU: 0.0}, period_min=2)
    climate = hass.data["climate"].get_entity(ENTITY)
    await service(hass, "set_temperature", temperature=21.0, hvac_mode="heat")
    for room in (20.0, 20.5, 21.0, 21.5, 21.5, 21.2):
        hass.states.async_set(SENSOR, str(room))
        await tick(hass, freezer)
    assert entry.runtime_data.learner.factor(65) == 1.1
    await tick(hass, freezer)
    device = next(d for d in climate._devices if d.entity_id == WZ)
    assert device.regulator.kd == pytest.approx(0.88)
    assert hass.states.get("sensor.wohnbereich_overshoot").state == "0.5"
    assert hass.states.get("sensor.wohnbereich_brake_factor").state == "1.1"
    await hass.services.async_call("thermgenie", "reset_learning", {"entity_id": ENTITY}, blocking=True)
    assert entry.runtime_data.learner.factor(65) == 1.0


async def lock_setup(hass, **extra):
    hass.states.async_set(SZ, "heat", {"hvac_modes": ["heat"], "min_temp": 6.0, "max_temp": 30})
    hass.states.async_set(SENSOR, "18.0")
    hass.states.async_set(VALVE, "0")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Schlafzimmer",
        data={
            "temperature_sensor": SENSOR,
            "heaters": [SZ],
            "lock_enabled": True,
            "lock_valve": VALVE,
            "notify_service": "notify.handy",
            "tts_service": "notify.echo",
            "tts_targets": ["media_player.x"],
            **extra,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _heat(hass):
    """The way past the refused services: a mode restored after a restart, say."""
    await hass.data["climate"].get_entity(SZ_ENTITY).async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()


async def test_lock_turns_heating_off_without_any_heat_command(hass, radio, pushes):
    await lock_setup(hass)
    await _heat(hass)
    assert hass.states.get(SZ_ENTITY).state == "off"
    assert set(radio.setpoints(SZ)) == {6.0}
    assert "abgeschaltet" in pushes[0]["title"]
    assert hass.states.get(SZ_ENTITY).attributes["heat_lock"] is True


async def test_lock_works_without_a_valve_sensor(hass, radio, pushes):
    await lock_setup(hass, lock_valve=None)
    await _heat(hass)
    assert hass.states.get(SZ_ENTITY).state == "off"
    assert "eingeschaltet" in pushes[0]["message"]


async def test_lock_refuses_every_access_from_outside(hass, radio, pushes):
    await lock_setup(hass)
    calls = {
        "set_hvac_mode": {"hvac_mode": "heat"},
        "set_temperature": {"temperature": 22.0},
        "set_preset_mode": {"preset_mode": "comfort"},
        "turn_on": {},
    }
    for name, data in calls.items():
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call("climate", name, {"entity_id": SZ_ENTITY, **data}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(SZ_ENTITY).state == "off"
    assert radio.modes(SZ).count("heat") == 0
    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": SZ_ENTITY, "hvac_mode": "off"}, blocking=True)


async def test_lock_is_off_by_default(hass, radio, pushes):
    await lock_setup(hass, lock_enabled=False)
    await _heat(hass)
    assert hass.states.get(SZ_ENTITY).state == "heat"
    assert not pushes


async def test_open_valve_gets_the_off_command_again(hass, radio, pushes):
    await lock_setup(hass)
    sent = len(radio.setpoints(SZ))
    hass.states.async_set(VALVE, "40")
    await hass.async_block_till_done()
    assert len(radio.setpoints(SZ)) == sent + 1
    hass.states.async_set(VALVE, "0")
    await hass.async_block_till_done()
    assert all(p["data"]["push"]["interruption-level"] != "critical" for p in pushes)


async def test_only_frost_breaks_the_lock_until_the_room_is_warmer(hass, radio, pushes, freezer):
    freezer.move_to(NOW)
    await lock_setup(hass)
    # 7 degrees and an open valve: not frost yet, the lock holds
    hass.states.async_set(SENSOR, "7.0")
    hass.states.async_set(VALVE, "40")
    await hass.async_block_till_done()
    hass.states.async_set(VALVE, "0")
    await hass.async_block_till_done()
    assert not hass.states.get(SZ_ENTITY).attributes["frost_active"]
    pushes.clear()

    hass.states.async_set(SENSOR, "6.0")
    await tick(hass, freezer, 5)
    state = hass.states.get(SZ_ENTITY)
    assert state.attributes["frost_active"] and state.attributes["hvac_action"] == "heating"
    assert radio.setpoints(SZ)[-1] == 8.0
    assert [p["title"] for p in pushes] == ["Schlafzimmer: Frostschutz aktiv"]

    # Still below the end of the frost case: an open valve is wanted now
    hass.states.async_set(SENSOR, "7.5")
    hass.states.async_set(VALVE, "60")
    await tick(hass, freezer, 5)
    assert hass.states.get(SZ_ENTITY).attributes["frost_active"]
    assert radio.setpoints(SZ)[-1] == 8.0
    assert len(pushes) == 1

    # Warm again: closed, and no alarm while the valve is on its way
    hass.states.async_set(SENSOR, "8.0")
    await tick(hass, freezer, 5)
    assert not hass.states.get(SZ_ENTITY).attributes["frost_active"]
    assert radio.setpoints(SZ)[-1] == 6.0
    assert len(pushes) == 1


async def test_stuck_valve_escalates_loud(hass, radio, pushes):
    hass.states.async_set("person.x", "home")
    await lock_setup(hass, lock_wait_sec=0.01, presence_entity="person.x")
    hass.states.async_set(VALVE, "40")
    await hass.async_block_till_done()
    climate = hass.data["climate"].get_entity(SZ_ENTITY)
    await climate.lock._task
    await hass.async_block_till_done()
    levels = [(p.get("data") or {}).get("push", {}).get("interruption-level") for p in pushes]
    assert "critical" in levels
    assert any(p.get("target") == ["media_player.x"] for p in pushes)


async def test_a_routine_switched_off_stays_quiet_and_comes_back(hass, radio):
    devices(hass)
    hass.states.async_set(PERSON, "home")
    hass.states.async_set(SLEEP, "off")
    await setup(hass, presence_entity=PERSON, sleep_entity=SLEEP)
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    await hass.services.async_call(DOMAIN, "set_routine", {"entity_id": ENTITY, "routine": "sleep", "enabled": False}, blocking=True)
    assert hass.states.get(ENTITY).attributes["routines_off"] == ["sleep"]
    hass.states.async_set(SLEEP, "on")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "comfort"
    await hass.services.async_call(DOMAIN, "set_routine", {"entity_id": ENTITY, "routine": "sleep", "enabled": True}, blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY)
    assert (state.attributes["routines_off"], state.attributes["preset_mode"]) == ([], "eco")


async def test_lock_takes_the_valve_of_the_old_settings_along(hass, radio, pushes):
    entry = await lock_setup(hass)
    assert entry.version == 3
    assert "lock_valve" not in {**entry.data, **entry.options}
    assert entry.options["valves"] == {SZ: VALVE}


async def test_lock_turns_a_knob_back_at_once_without_any_option(hass, radio, pushes, freezer):
    await lock_setup(hass)
    await hass.async_block_till_done()
    freezer.tick(120)
    radio.calls.clear()
    hass.states.async_set(SZ, "heat", {**hass.states.get(SZ).attributes, "temperature": 28})
    await hass.async_block_till_done()
    # This valve has no off mode, its lowest setpoint means closed
    assert radio.setpoints(SZ)[-1] == 6.0


async def _valve_room(hass, own):
    hass.states.async_set(SZ, "heat", {"hvac_modes": ["off", "heat"], "min_temp": 5, "max_temp": 30, "current_temperature": own})
    hass.states.async_set(SENSOR, "21.0")
    hass.states.async_set("sensor.ventil", "0")
    entry = MockConfigEntry(domain=DOMAIN, title="Bad", data={"temperature_sensor": SENSOR, "heaters": [SZ], "valves": {SZ: "sensor.ventil"}, "notify_service": "notify.handy"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call("climate", "set_temperature", {"entity_id": entry.runtime_data.climate.entity_id, "temperature": 22.0, "hvac_mode": "heat"}, blocking=True)
    await hass.async_block_till_done()
    return entry


async def _valve_open_for_an_hour(hass, freezer):
    hass.states.async_set("sensor.ventil", "40")
    await hass.async_block_till_done()
    freezer.tick(60 * 60)
    hass.states.async_set("sensor.ventil", "41")
    await hass.async_block_till_done()


async def test_a_warm_radiator_in_a_room_that_needs_heat_is_no_fault(hass, radio, pushes, freezer):
    await _valve_room(hass, own=26.0)
    await _valve_open_for_an_hour(hass, freezer)
    assert not pushes


async def test_a_radiator_that_was_shut_and_stays_open_gets_a_warning(hass, radio, pushes, freezer):
    entry = await _valve_room(hass, own=23.0)
    hass.states.async_set(SENSOR, "22.6")
    await entry.runtime_data.climate._async_regulate()
    await _valve_open_for_an_hour(hass, freezer)
    assert len(pushes) == 1


async def test_a_valve_that_stays_open_gets_a_warning_after_the_waiting_time(hass, radio, pushes, freezer):
    hass.states.async_set(SZ, "heat", {"hvac_modes": ["off", "heat"], "min_temp": 5, "max_temp": 30, "current_temperature": 21})
    hass.states.async_set(SENSOR, "21.0")
    hass.states.async_set("sensor.ventil", "0")
    entry = MockConfigEntry(domain=DOMAIN, title="Bad", data={"temperature_sensor": SENSOR, "heaters": [SZ], "valves": {SZ: "sensor.ventil"}, "notify_service": "notify.handy"}, version=3)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    problem = er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_valve_stuck")
    assert hass.states.get(problem).state == "off"

    hass.states.async_set("sensor.ventil", "40")
    await hass.async_block_till_done()
    freezer.tick(60 * 29)
    hass.states.async_set("sensor.ventil", "41")
    await hass.async_block_till_done()
    assert hass.states.get(problem).state == "off"
    assert not pushes

    freezer.tick(60 * 2)
    hass.states.async_set("sensor.ventil", "42")
    await hass.async_block_till_done()
    assert hass.states.get(problem).state == "on"
    assert len(pushes) == 1
    hass.states.async_set("sensor.ventil", "43")
    await hass.async_block_till_done()
    assert len(pushes) == 1  # once is enough

    hass.states.async_set("sensor.ventil", "0")
    await hass.async_block_till_done()
    assert hass.states.get(problem).state == "off"
