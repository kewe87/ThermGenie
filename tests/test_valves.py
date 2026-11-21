"""The room watch finds an open valve that reports closed."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.thermgenie.valves import ValveWatch


class Room:
    def __init__(self):
        self.hass = SimpleNamespace(config=SimpleNamespace(language="de"))
        self.conf = {}
        self.room = "Wohnbereich"
        self.current_temperature = 23.6
        self.current_humidity = 50.0
        self.hvac_mode = HVACMode.HEAT
        self.hvac_action = HVACAction.IDLE
        self.lock = SimpleNamespace(frost_active=False, enabled=False)
        self.pushes, self.logs = [], []

    async def async_log(self, message):
        self.logs.append(message)

    async def async_notify(self, title, message, level=None, extra=None):
        self.pushes.append((title, message))


def _run(room, temps, start=datetime(2026, 11, 21, 22, 35, tzinfo=timezone.utc), humidity=None):
    watch = ValveWatch(room)
    for i, t in enumerate(temps):
        room.current_temperature = t
        if humidity:
            room.current_humidity = humidity[i]
        asyncio.run(watch._async_check_room(start + timedelta(minutes=5 * i)))
    return watch


def test_a_room_that_keeps_warming_while_nothing_heats_is_reported():
    room = Room()
    watch = _run(room, [23.6 + 0.09 * i for i in range(14)])  # like the evening of the firmware update
    assert len(room.pushes) == 1 and "wärmer" in room.pushes[0][1]
    assert "room" in watch.stuck


def test_after_heat_that_flattens_is_not_reported():
    room = Room()
    _run(room, [23.1, 23.3, 23.5, 23.6, 23.6, 23.6, 23.5, 23.5, 23.4, 23.4, 23.3, 23.3])
    assert room.pushes == []


def test_a_shower_is_not_an_open_valve():
    room = Room()
    _run(room, [21.9 + 0.1 * i for i in range(12)], humidity=[47 + 2 * i for i in range(12)])
    assert room.pushes == []


def test_heating_resets_the_watch():
    room = Room()
    watch = ValveWatch(room)
    start = datetime(2026, 11, 21, 22, 0, tzinfo=timezone.utc)
    for i in range(14):
        room.current_temperature = 22.0 + 0.1 * i
        room.hvac_action = HVACAction.HEATING if i == 8 else HVACAction.IDLE
        asyncio.run(watch._async_check_room(start + timedelta(minutes=5 * i)))
    assert room.pushes == []
