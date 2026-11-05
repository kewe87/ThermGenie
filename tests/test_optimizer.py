"""Tests of the optimizer on its own and in the running thermostat."""

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.thermgenie.optimizer import FACTOR_MAX, FACTOR_MIN, PHASES_PER_STEP, Optimizer, PhaseObserver, advice, measure

from .test_climate import AC, ENTITY, SENSOR, devices, radio, service, setup  # noqa: F401

HOUR = 3600


def phase(overshoot=0.0, undershoot=0.0, swings=0, hours_per_k=1.0):
    return {"overshoot": overshoot, "undershoot": undershoot, "swings": swings, "hours_per_k": hours_per_k}


def feed(optimizer, apply=True, rounds=PHASES_PER_STEP, **values):
    result = None
    for _ in range(rounds):
        result = optimizer.add(phase(**values), apply, 0.0)
    return result


def test_a_phase_measures_rise_overshoot_undershoot_and_swings():
    observer = PhaseObserver()
    samples = [(0, 19.0), (HOUR, 20.0), (2 * HOUR, 21.0), (2.5 * HOUR, 21.4), (3 * HOUR, 20.8), (4 * HOUR, 21.2)]
    assert all(observer.update(t, room, 21.0, True) is None for t, room in samples)
    result = observer.update(5 * HOUR, 21.0, 21.0, True)
    assert result["reached"] is True
    assert result["overshoot"] == 0.4
    assert result["undershoot"] == 0.2
    assert result["swings"] == 2
    assert result["hours_per_k"] == 1.0


def test_a_small_gap_is_no_phase():
    observer = PhaseObserver()
    observer.update(0, 20.7, 21.0, True)
    assert observer.active is False


def test_a_spoiled_rise_counts_for_nothing():
    observer = PhaseObserver()
    observer.update(0, 19.0, 21.0, True)
    assert observer.update(HOUR, 19.5, 21.0, False) is None
    assert observer.active is False
    observer.update(2 * HOUR, 19.0, 21.0, True)
    assert observer.update(3 * HOUR, 19.5, 20.0, True) is None
    assert observer.active is False


def test_a_new_target_while_settling_keeps_what_was_seen_if_long_enough():
    observer = PhaseObserver()
    observer.update(0, 19.0, 21.0, True)
    observer.update(HOUR, 21.0, 21.0, True)
    assert observer.update(HOUR + 600, 21.1, 19.0, True) is None  # too short
    observer.update(2 * HOUR, 19.0, 21.0, True)
    observer.update(3 * HOUR, 21.0, 21.0, True)
    observer.update(3.5 * HOUR, 21.3, 21.0, True)
    assert observer.update(4.5 * HOUR, 21.2, 19.0, True)["overshoot"] == 0.3


def test_a_room_that_never_gets_there_counts_as_slow():
    observer = PhaseObserver()
    observer.update(0, 19.0, 21.0, True)
    result = observer.update(9 * HOUR, 19.5, 21.0, True)
    assert result["reached"] is False
    assert result["hours_per_k"] == 18.0
    assert advice(measure([result])) == "slow"


def test_the_median_leaves_out_a_single_outlier():
    values = measure([phase(overshoot=2.0), phase(), phase(), phase(), phase()])
    assert values["overshoot"] == 0.0
    assert advice(values) is None


def test_nothing_moves_before_enough_phases_came_together():
    optimizer = Optimizer()
    assert feed(optimizer, rounds=PHASES_PER_STEP - 1, overshoot=1.0) is None
    assert optimizer.ki_factor == 1.0


def test_each_finding_has_its_small_step():
    optimizer = Optimizer()
    assert feed(optimizer, overshoot=0.5)["reason"] == "overshoot"
    assert (optimizer.kp_factor, optimizer.ki_factor) == (1.0, 0.85)
    optimizer = Optimizer()
    assert feed(optimizer, swings=3)["reason"] == "swinging"
    assert (optimizer.kp_factor, optimizer.ki_factor) == (0.9, 0.85)
    optimizer = Optimizer()
    assert feed(optimizer, undershoot=0.5)["reason"] == "sagging"
    assert optimizer.ki_factor == 1.1
    optimizer = Optimizer()
    assert feed(optimizer, hours_per_k=5.0)["reason"] == "slow"
    assert optimizer.kp_factor == 1.1


def test_a_good_regulation_stays_as_it_is():
    optimizer = Optimizer()
    assert feed(optimizer, overshoot=0.2, undershoot=0.1) is None
    assert (optimizer.kp_factor, optimizer.ki_factor) == (1.0, 1.0)
    assert optimizer.steps == []


def test_observing_only_proposes():
    optimizer = Optimizer()
    result = feed(optimizer, apply=False, overshoot=0.5)
    assert result == {"reason": "overshoot", "kp_factor": 1.0, "ki_factor": 0.85}
    assert optimizer.proposal == result
    assert optimizer.ki_factor == 1.0


def test_the_factors_stay_within_their_bounds():
    optimizer = Optimizer()
    for _ in range(40):
        feed(optimizer, overshoot=0.5)
        optimizer.best = None
    assert optimizer.ki_factor == FACTOR_MIN
    optimizer = Optimizer()
    for _ in range(40):
        feed(optimizer, hours_per_k=5.0)
        optimizer.best = None
    assert optimizer.kp_factor == FACTOR_MAX


def test_a_step_that_made_it_worse_is_taken_back_and_not_tried_again_soon():
    optimizer = Optimizer()
    assert feed(optimizer, overshoot=0.5)["reason"] == "overshoot"
    assert feed(optimizer, overshoot=1.0)["reason"] == "back"
    assert optimizer.ki_factor == 1.0
    assert feed(optimizer, overshoot=0.5) is None  # blocked
    assert optimizer.ki_factor == 1.0


def test_everything_survives_a_restart_and_a_reset_goes_back():
    optimizer = Optimizer()
    feed(optimizer, overshoot=0.5)
    optimizer.add(phase(), True, 0.0)
    again = Optimizer(optimizer.as_dict())
    assert again.ki_factor == 0.85
    assert len(again.phases) == 1
    again.reset()
    assert (again.kp_factor, again.ki_factor) == (1.0, 1.0)
    assert again.phases == []
    assert again.history


def _entity(hass, entry, key):
    return next(e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) if e.translation_key == key)


async def _heating_phase(hass, climate, freezer, room_peak=21.5):
    """One heating phase from below the target up to past it and settled."""
    for room, hours in ((19.0, 0.5), (20.5, 1), (21.0, 0.5), (room_peak, 1), (21.0, 2.1)):
        hass.states.async_set(SENSOR, str(room))
        await hass.async_block_till_done()
        climate._track_phase()
        freezer.tick(hours * HOUR)
    hass.states.async_set(SENSOR, "21.0")
    await hass.async_block_till_done()
    climate._track_phase()


async def test_observing_measures_but_leaves_the_regulation_alone(hass, radio, freezer):
    devices(hass)
    entry = await setup(hass, tuning="observe")
    climate = entry.runtime_data.climate
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    for _ in range(PHASES_PER_STEP):
        await _heating_phase(hass, climate, freezer)
    assert hass.states.get(_entity(hass, entry, "tuning_state")).state == "proposal"
    assert entry.runtime_data.optimizer.proposal["reason"] == "overshoot"
    assert entry.runtime_data.optimizer.ki_factor == 1.0
    assert climate.tuned_gains == (climate.conf["kp"], climate.conf["ki"])


async def test_automatic_tuning_changes_the_radiators_only(hass, radio, freezer):
    devices(hass)
    entry = await setup(hass, tuning="automatic")
    climate = entry.runtime_data.climate
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    ki = climate.conf["ki"]
    for _ in range(PHASES_PER_STEP):
        await _heating_phase(hass, climate, freezer)
    assert entry.runtime_data.optimizer.ki_factor == 0.85
    regulators = {d.entity_id: d.regulator for d in climate.devices}
    assert regulators["climate.wz"].ki == round(ki * 0.85, 4)
    assert regulators[AC].ki == climate.conf["ki_cool"]
    assert entry.options.get("ki") is None  # what the user set stays


async def test_a_window_spoils_the_phase(hass, radio, freezer):
    devices(hass)
    entry = await setup(hass, tuning="observe", window_open_delay=0)
    climate = entry.runtime_data.climate
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(SENSOR, "19.0")
    await hass.async_block_till_done()
    climate._track_phase()
    assert entry.runtime_data.optimizer.observer.active
    hass.states.async_set("binary_sensor.fenster", "on")
    await hass.async_block_till_done()
    freezer.tick(1)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    climate._track_phase()
    assert not entry.runtime_data.optimizer.observer.active


async def test_a_change_at_the_device_spoils_the_phase(hass, radio, freezer):
    devices(hass)
    entry = await setup(hass, tuning="observe")
    climate = entry.runtime_data.climate
    await service(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(SENSOR, "19.0")
    await hass.async_block_till_done()
    climate._track_phase()
    observer = entry.runtime_data.optimizer.observer
    assert observer.active
    freezer.tick(120)
    old = hass.states.get("climate.wz")
    hass.states.async_set("climate.wz", "heat", {**old.attributes, "temperature": 30.0})
    await hass.async_block_till_done()
    assert not observer.active


async def test_the_mode_is_a_live_setting_and_going_manual_restores_the_values(hass, radio):
    devices(hass)
    entry = await setup(hass)
    climate = entry.runtime_data.climate
    optimizer = entry.runtime_data.optimizer
    optimizer.ki_factor = 0.5
    select = _entity(hass, entry, "tuning")
    assert hass.states.get(select).state == "manual"
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "automatic"}, blocking=True)
    await hass.async_block_till_done()
    ki = climate.conf["ki"]
    assert climate.devices[0].regulator.ki == round(ki * 0.5, 4)
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "manual"}, blocking=True)
    await hass.async_block_till_done()
    assert climate.devices[0].regulator.ki == ki
    assert hass.states.get(_entity(hass, entry, "tuning_state")).state == "off"


async def test_the_button_forgets_it(hass, radio):
    devices(hass)
    entry = await setup(hass, tuning="automatic")
    optimizer = entry.runtime_data.optimizer
    optimizer.ki_factor = 0.5
    await hass.services.async_call("button", "press", {"entity_id": _entity(hass, entry, "reset_learning")}, blocking=True)
    await hass.async_block_till_done()
    assert optimizer.ki_factor == 1.0
    assert entry.runtime_data.climate.devices[0].regulator.ki == entry.runtime_data.climate.conf["ki"]


async def test_a_locked_room_offers_no_tuning(hass, radio):
    devices(hass)
    entry = await setup(hass, lock_enabled=True)
    keys = {e.translation_key for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert not keys & {"tuning", "tuning_state", "tuned_kp", "reset_learning"}
