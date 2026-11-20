<p align="center">
  <img src="custom_components/thermgenie/brand/logo@2x.png" alt="ThermGenie" height="128">
</p>

<p align="center"><b>Room climate control for Home Assistant, based on a reference sensor of your choice.</b></p>

<p align="center"><a href="README.md">Deutsch</a> · <b>English</b></p>

ThermGenie combines the heating and cooling devices of a room into one thermostat and regulates them on a sensor
of your choice. Your existing devices stay in place: ThermGenie controls them through their `climate` entity and
corrects their setpoint until the room reaches the desired temperature.

This solves a common problem: radiator thermostats and air conditioners measure the temperature where they are
installed. It is usually warmer or colder there than in the occupied area, so the value you set never actually
reaches the room.

<p align="center">
  <img src="docs/en/control.png" alt="Control panel with dial, mode and presets" width="720">
</p>

The [manual](docs/en/manual.md) describes every function and routine in detail.

## Comparison with Generic Thermostat

The [Generic Thermostat](https://www.home-assistant.io/integrations/generic_thermostat/) included in Home Assistant
switches an actuator on and off based on a sensor. This is sufficient for simple heaters or fans. ThermGenie is
intended for rooms with controllable devices and more demanding requirements.

| | Generic Thermostat | ThermGenie |
| --- | --- | --- |
| **Actuator** | One switchable entity | Up to six heating devices and one air conditioner (`climate`) |
| **Control method** | Two-point control with tolerance | PI control with an approach brake, acting on the device setpoint, optionally self-optimizing |
| **Modes** | Heat or cool, fixed per instance | Off, heat and cool in one thermostat; dry and fan if the air conditioner offers them |
| **Several devices in a room** | Not intended | Offset and brake per heating device |
| **Controlled value** | Temperature | Temperature, humidex or comfort temperature |
| **Daily routine** | Presets, automations to be created separately | Sleep, absence, alarm, way home and boost built in |
| **Windows, outdoor temperature** | Separate automations | Built in, with delays and hysteresis |
| **Failure handling** | Optional shutdown on a stale sensor | Falls back to device control, failed devices do not block the others, valve verification |
| **Interface** | Standard dialog | Dedicated card and control panel |

## How it works

At a fixed interval, ThermGenie compares the reference sensor with the target and calculates a shifted setpoint for
each device. A room below the target receives a higher setpoint, a room that is too warm a lower one. Shortly before
reaching the target the controller brakes to avoid overshoot. Optionally, it learns this brake from completed heating
phases, separately per flow temperature. Commands are only sent when the value changes noticeably, which saves radio
traffic and batteries.

Each thermostat operates independently in its own mode. There is no automatic changeover between heating and
cooling.

### Direct drive of the valves

Radiator thermostats whose valve opening can be set (for example the Sonoff TRVZB via Zigbee2MQTT) can be driven by
ThermGenie directly. Instead of a shifted setpoint the valve gets an opening in percent. For this ThermGenie keeps
learning a small heat model of the room: how strongly the radiators heat at which flow temperature, how fast the room
loses heat to the outside and how slow the radiators are. With it, the opening is planned two hours ahead and the valve
closes in time before the room overshoots. Until the model knows the room, usually after two to three days, a simple
regulator drives the valves. What was learned survives restarts and shows up as the sensor *Valve opening*,
including a curve of the opening needed per outdoor temperature.

The thermostat keeps the setpoint as a fallback. If the room sensor fails, it gets its valve back and regulates on its
own. With an open window, heating off or a warm day the valve closes. Radiators without valve control stay in setpoint
mode, and both kinds can be mixed in one room. It is set up under *Settings → Direct drive*, the valve entities are
found on the device.

If the thermostat takes a room temperature from outside (on the TRVZB *External temperature*), it also gets a safety
net for the case Home Assistant stops: ThermGenie sends it the room temperature, on a change of 0.3 °C or more and else
once an hour, and sets its setpoint 2 °C above the target. Day to day ThermGenie drives the valve, the thermostat only
closes when the room gets clearly too warm. Should Home Assistant go silent, it closes on its own, and after two hours
without new values it goes on with its own sensor. The rare values cost hardly any battery.

### Thermal Wellbeing: by feeling instead of numbers

**Background.** Whether a room is comfortable depends only partly on the air temperature. Humidity, draughts, the
warmth of walls and windows, clothing, activity, the time of day and the season all play a part, and everybody feels
differently. Comfort research has described this for a long time (Fanger's PMV model, ISO 7730), yet a thermostat only
knows a number. So people set 21 °C, still find it chilly and turn it up to 23 °C, or they see "19 °C" and feel cold
before they have even noticed how the room feels. Thermal Wellbeing turns this around. It does not ask for a number but
for how it feels, and learns from that what is really comfortable in this room at which time.

**Switching.** Every room can be switched between *Thermostat* and *Thermal Wellbeing*: with the switch at the bottom of
the popup, with the switch *Thermal Wellbeing* on the device page or with the action `thermgenie.set_wellbeing`. The
room does not jump, it starts where it is. In Thermal Wellbeing there is no number anymore, neither on the card nor in
the popup nor in the push question.

**Answers.** One only says how it feels: 🥶 cold, 🙁 a bit cool, 😊 fine, 😐 a bit warm, 🥵 too warm. That works with the
faces, with plus and minus in the popup, with the buttons of a push notification or with the action `thermgenie.feel`.
The knob of the thermostat is an answer as well: turned up a bit means a bit cool, down a bit means a bit warm, from
1.5 degrees on cold or too warm. Afterwards ThermGenie sets the knob back to where the room is heading. When the
thermostat has a child lock, ThermGenie sets it itself: on in the thermostat mode and under a heating lock, off in
Thermal Wellbeing. A second answer within two minutes replaces the first one, for example after a mis-tap.

**Learning.** ThermGenie keeps every answer with the time of day, the weekday, the outdoor temperature and the preset.
From that it knows for every moment how far the comfortable temperature lies from the preset: answers at a similar hour,
in similar weather and under the same preset count most, old answers fade. What was said today counts at once and fades
out over a few hours, so a single chilly evening does not decide the whole week. Without answers, what was learned
slowly goes back to the preset. The presets Comfort, Eco and so on stay and learn along. In the thermostat mode
ThermGenie learns as well: a setpoint changed by hand counts as a quiet answer.

**Asking.** After a change ThermGenie asks by push once the room has been where the answer sent it for about an hour,
until the answers around a time of day settle. Then it no longer asks there. It does not ask with the window open, and
answers with the window open are kept but not learned. If an answer is far from what was learned for this time, a
second question follows: is something special going on? The choice is sport, unwell, just got home, a reason of one's
own to type in, or "all normal". With a special reason the answer does not count for later, when unwell only for today.
This way ThermGenie learns the everyday and not the exceptions.

**What you see.** Instead of a number the card shows a face and a tendency: getting warmer, holding or getting cooler,
also as the sensor *Tendency*. The face of the last answer stays until the room got there or the devices cannot do more,
for example when a room that is too warm and has no air conditioner can only cool down by itself. After two hours
without a further answer it is neutral at the latest: no further word means it fits.
*Details* tells in words what was learned so far: for mornings, midday, evenings and late evenings, whether it should be
warmer or cooler than set, how sure that is already and where ThermGenie no longer asks. Below are the answers that do
not count for later because of a special reason.

Thermal Wellbeing works with any kind of radiator thermostat, with direct drive of the valves only more finely.

### Optimize regulation

The controller values can be set by hand or adjusted automatically. The *Optimize regulation* selection has three levels:

| Level | Behavior |
| --- | --- |
| **Manual** | Only the values you set apply. |
| **Observe only** | Heating phases are measured, suggestions appear under *Diagnostic* and in the logbook. The regulation stays unchanged. |
| **Automatic** | kp and ki are adjusted in small steps. The values you set are kept as the basis. |

Overshoot, undershoot, swinging around the target and heat-up time are measured. A change only happens after five
comparable heating phases, based on the median, and stays between 0.5 and 2 times the values you set. Phases with an
open window, a changed target or a manual change at the device do not count. A step that makes the result worse is
taken back. Because an adjustment needs several heating phases, the optimization takes effect over days to weeks. It
only covers heating with radiators.

## Features

### Daily routine

- **Sleep and absence:** Setback to the eco preset, followed by a return to comfort
- **Heating up before waking:** Lead time ahead of an alarm, optionally a fixed time or a time from an entity
- **Way home:** Preheating based on direction and distance
- **Boost:** Raised setpoint with an optional end time
- **Windows:** Reaction to open windows with adjustable delays
- **Heat source:** With an air conditioner that can heat, choose whether to heat with the radiators, the air conditioner or both
- **Warm days:** Heating block through an outdoor sensor with hysteresis and hold time

### Air and summer operation

- **Move the air:** A fan runs while heating, while cooling or on a temperature difference between two sensors. Fans started manually are left alone.
- **Heat guard:** Starts cooling ahead of time when it is hot and someone is on the way home
- **Drying limit:** Ends drying before the air becomes too dry
- **Night cascade:** Regulates the felt temperature at the bed, first through a fan and only secondarily through the air conditioner

### Protection and monitoring

- **Heating lock:** For rooms that should not be heated. The device is closed immediately and any adjustment is set back, heating commands from outside are refused. Only frost protection suspends the lock temporarily.
- **Hold devices:** Optionally, manual changes made directly at the device are set back right away. Devices without an off mode are closed through their lowest setpoint.
- **Valve monitoring:** If a valve stays open although the heating device should close, a warning appears after an adjustable time. In a locked room, an open valve triggers the lock and leads to an alarm if the fault persists.
- **Fault tolerance:** If the reference sensor fails, the devices regulate on their own sensors. The failure of one device does not affect the others.

## Integrating with your system

Only the reference sensor and at least one device are required. Every other function becomes active once its entity
is assigned.

| Purpose | Entity | Function |
| --- | --- | --- |
| **Room temperature** (required) | `sensor` | Control reference |
| **Heating devices, air conditioner** (at least one) | `climate` | Actuators |
| Humidity | `sensor` | Humidex, dew point, comfort temperature |
| Window | `binary_sensor` | Window detection |
| Outdoor temperature | `sensor` | Heating block on warm days |
| Valve position per heating device | `sensor` | Valve monitoring, heating lock |
| Flow temperature | `sensor` | Learning the brake |
| Presence | `person`, `device_tracker`, `binary_sensor` | Setback during absence (together with sleep), way home, heat guard, night cascade |
| Sleep | `binary_sensor`, `input_boolean` | Night setback |
| Alarm, fixed time | `input_datetime`, `sensor` | Heating up before waking |
| Direction and distance | `sensor` | Way home, heat guard |
| Fan | `fan` | Move the air, night cascade |
| Notification, speech | `notify`, `media_player` | Messages and warnings |

Several ThermGenie thermostats work independently of each other, one thermostat is created per room.

### Voice control and Matter

ThermGenie provides a regular `climate` entity and can therefore be exposed through Home Assistant integrations and
Matter bridges such as Home Assistant Matter Hub. The modes available there are determined by the bridge and the
voice assistant. Expose only the `climate` entity, not the settings entities of the device.

## Interface

`thermgenie-card` shows status, room temperature and target and is automatically available in the card picker.

```yaml
type: custom:thermgenie-card
entity: climate.living_room
```

<p align="center">
  <img src="docs/en/cards.png" alt="Cards for several rooms" width="480">
</p>

A dedicated control panel replaces the standard dialog for all ThermGenie thermostats. It offers operation by dial,
mode and presets, as well as a details view with active automations, indoor climate, device state and the temperature
history of the last 24 hours.

<p align="center">
  <img src="docs/en/details.png" alt="Details view" width="720">
</p>
<p align="center">
  <img src="docs/en/dark.png" alt="Control panel in the dark theme" width="720">
</p>
<p align="center">
  <img src="docs/en/phone.png" alt="Control panel on a phone" width="360">
</p>

## Settings

All values are available as entities on the thermostat's device page and can therefore also be used in dashboards and
automations. Changes take effect immediately, and the controller keeps its state.

| Section | Content |
| --- | --- |
| **Controls** | The thermostat |
| **Sensors** | Humidex, dew point, comfort temperature |
| **Configuration** | Heat source, optimization of the regulation, regulation on real temperature, humidex or comfort temperature, preset temperatures, offset and brake per heating device, limits, times, routines. Controller parameters start disabled and can be enabled when needed. |
| **Diagnostic** | Setpoint per device, reason for a block, next heating up, sensor failure, stuck valve, learned values, optimization status |

Entity assignments are managed under *Configure*. The heating lock is a switch among the settings of the device. Like
all settings it is not exposed to voice assistants by itself.

## Installation

1. Under *Settings → Marketplace*, search for **ThermGenie**, install it and restart Home Assistant.

   If ThermGenie does not show up there, add `https://github.com/kewe87/ThermGenie` as a custom repository. Without the Marketplace, copy `custom_components/thermgenie` to your Home Assistant directory. In both cases, restart Home Assistant afterwards.
2. Add the integration under *Settings → Devices & services → Add integration → ThermGenie*.
3. A wizard guides you through the basic setup. All further assignments are available under *Configure*.

### Setup with AI

With an AI service (`ai_task`) set up, the menu offers *Set up with AI*. The AI suggests suitable devices, sensors and
temperatures. You review the suggestions, and they only apply once you save. The provider receives names, areas and
types of the candidate entities plus the current settings of the thermostat, but no readings or states.

## Language

The interface, card, notifications and spoken messages appear in German on a German system and in English otherwise.

## Like ThermGenie?

Then I'd be happy about a ⭐ on [GitHub](https://github.com/kewe87/ThermGenie). It helps others find the project. Bugs and ideas are welcome as [issues](https://github.com/kewe87/ThermGenie/issues).

## License

Copyright (c) 2026 kewe87. ThermGenie is licensed under the [GNU General Public License v3.0](LICENSE). Anyone who
distributes a modified version must provide its source code under the same license.
