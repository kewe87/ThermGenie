# ThermGenie manual

[Deutsch](../de/handbuch.md) · **English** · [Back to the overview](../../README.en.md)

This manual describes every function of ThermGenie: what it does, when it triggers, what it needs and how it is configured. For
a first overview, the [README](../../README.en.md) is enough.

## Contents

1. [Basic principle](#1-basic-principle)
2. [Setup](#2-setup)
3. [Operation](#3-operation)
4. [Regulation](#4-regulation)
5. [Everyday routines](#5-everyday-routines)
6. [Air and summer routines](#6-air-and-summer-routines)
7. [Protection and monitoring](#7-protection-and-monitoring)
8. [Entities and services](#8-entities-and-services)
9. [Messages](#9-messages)
10. [Troubleshooting](#10-troubleshooting)

## 1. Basic principle

One ThermGenie thermostat stands for one room. It has a **room sensor** and leads up to six **heaters** and one **air
conditioner**. All of them are existing `climate` entities in Home Assistant.

ThermGenie does not measure anything itself and does not operate a valve directly. It compares the room sensor with the target
and gives each device a shifted setpoint. The device then keeps regulating with its own technology. If the room is too cold,
the device gets a higher value, if it is too warm, a lower one.

Three rules always apply:

- **One mode at a time.** Heating and cooling never run together. There is no automatic changeover between them, with the
  exception of the [heat guard](#heat-guard).
- **A function is off as long as its entity is missing.** You do not have to switch off what you have not set up.
- **If something fails, the rest keeps running.** See [Failures](#failures).

## 2. Setup

### Creating a thermostat

Under *Settings → Devices & services → Add integration → ThermGenie*, a wizard guides you through these steps:

| Step | Content |
| --- | --- |
| New thermostat | Name, room sensor, humidity, heaters, air conditioner, window sensor |
| Offset and brake | Per heater, see [Several heaters](#several-heaters) |
| Warm days | Outdoor sensor and limits |
| Temperatures | Values of the presets |
| Everyday life and messages | Services and entities of the routines |

Only the room sensor and at least one device are required. Everything else can be added later.

### Choosing the room sensor

Place the sensor where the temperature counts, in the occupied area. It should not sit in the sun, above the radiator or in a
draught. It should also report regularly: if it stays silent for longer than *Room sensor counts as failed after* (default 120
minutes), it counts as failed.

### Changing settings

There are two places:

| Place | What is there | Effect |
| --- | --- | --- |
| **Device page** of the thermostat | Temperatures, limits, times, routines, controller values | Immediately, the controller keeps its state |
| **Configure** in the integration | Entity assignments, heating lock, frost limits, all values as well | With *Save and close*, the thermostat restarts |

Some values start disabled on the device page, such as kp and ki. They can be enabled there one by one. In a room with a heating
lock, heating values are hidden because they have no effect there.

### Setup with AI

With an AI service (`ai_task`) set up, the menu offers *Set up with AI*. The AI suggests devices, sensors and temperatures, you
review them, and only saving applies them. The provider receives names, areas and types of the candidate entities plus the
current settings of the thermostat, but no readings or states.

## 3. Operation

### Card

```yaml
type: custom:thermgenie-card
entity: climate.living_room
```

The card shows status, room temperature and target. A tap opens the control panel. It appears automatically in the card picker.
Locked rooms show no target.

### Control panel

**Control** holds the dial, mode and presets. **Details** holds:

- **Routines:** All routines that are set up. A tap switches a routine on or off for this thermostat.
- **Indoor climate:** Humidity and dew point. If the room regulates on humidex or comfort temperature, that value is shown too.
- **Devices:** Setpoint and state of each device.
- **Last 24 hours:** Room temperature, target and running times.
- **Device and settings:** Takes administrators to the device page.

### Modes

| Mode | Behavior |
| --- | --- |
| **Off** | All devices are switched off. Devices without an off mode go to their lowest setpoint. |
| **Heat** | The chosen [heat source](#heat-source) works, the other devices are off. |
| **Cool** | The air conditioner works, the heaters are off. |
| **Dry, fan** | If the air conditioner offers them. It then follows its own logic, without the controller. |

An air conditioner that ThermGenie did not start is switched off again in the next cycle if it should not be working.

### Presets

Heating and cooling have separate values. The thermostat remembers both.

| Preset | Heating, default | Cooling, default |
| --- | --- | --- |
| Frost protection | 7 °C | |
| Eco | 19 °C | 26 °C |
| Comfort | 21 °C | 24 °C |
| Boost | 23 °C | 22 °C |

If you change the target by hand, no preset is active any more. If you change the value of a preset, a thermostat currently on
that preset follows immediately.

## 4. Regulation

### How the setpoint comes about

In every regulation period (default 5 minutes), ThermGenie calculates for each device:

```
Setpoint = target + offset + P part + I part − brake
```

| Part | Meaning | Setting, default |
| --- | --- | --- |
| **P part** | Deviation times a factor. Reacts at once, but does not close the whole gap. | P gain, 0.3 |
| **I part** | Sums up the deviation over time and closes the rest. Past the target, the sum halves per period. | I gain, 0.05, limit 20 |
| **Brake** | Takes power away shortly before the target, depending on the rise of the last 30 minutes. Only acts within 1 K of the target. | D gain, 0, which means off |
| **Limit** | The correction from the three parts stays within this limit. | Largest setpoint shift, 2 K |

The result is rounded to the step size and limited to the range of the device. A new command is only sent if the value changes by
at least *Smallest step per radio command* (default 0.5 K). This saves radio traffic and batteries. After you operate the
thermostat, the devices are brought in line at once.

Cooling has its own set of these values. The defaults fit most rooms. Change them only in small steps and then watch for a few
days.

### Regulate on

With a humidity sensor, ThermGenie calculates three values. Separately for heating and cooling, you choose which one to regulate
on:

| Selection | Calculation | Suitable for |
| --- | --- | --- |
| **Real temperature** | The value of the room sensor | Heating, default |
| **Humidex** | Canadian standard formula. Humidity always counts and without limit, the value is often several degrees above the temperature. | Cooling at the height of summer |
| **Comfort temperature** | Temperature plus 0.5 K per degree of dew point above 16 °C, at most 2.5 K | Cooling and nights, also for indoor rooms with normal air |

The room temperature on the card and in the panel always shows the chosen value, and the target refers to it as well. On humidex,
a target of 26 therefore does not mean 26 °C of air temperature, so set the target accordingly. Without a humidity sensor, the
real temperature always applies.

### Heat source

If a thermostat has heaters **and** an air conditioner, *Heat with* decides what works in heat mode:

| Selection | Behavior |
| --- | --- |
| **Radiators only** | Default. The air conditioner stays off. |
| **Air conditioner only** | The air conditioner heats, the radiators stay off. |
| **Radiators and air conditioner** | Both work towards the same target. |

The change takes effect at once. The following applies:

- If the air conditioner offers no heat mode or cannot be reached, the radiators take over.
- The air conditioner also uses the controller values from the cooling section while heating.
- With an open window, the air conditioner goes off and radiators go to frost protection.
- Thermostats without radiators do not offer heating, even if the air conditioner could.

### Several heaters

One thermostat can lead several radiators, also across several connected rooms.

- **Offset:** Shifts the target of this radiator, for example −0.5 K for one that is closer to the room sensor.
- **Brake:** A large radiator keeps heating for a long time and needs a stronger brake than a small one.

Each radiator has its own controller. The failure of one radiator does not affect the others.

### Using the device sensor

*Convert the setpoint to the device sensor* is meant for devices whose own sensor differs clearly from the room, for example right
next to the warm radiator. The setpoint is then shifted by the difference between the device sensor and the room sensor.

### Learning brake

*Learn the brake from the overshoot* adjusts the brake after each clean heating phase. It only has an effect if the brake is set
above 0, because it changes its value through a factor.

- A heating phase starts at least 0.3 K below the target and ends as soon as the temperature drops 0.1 K below its peak.
- Overshoot above 0.3 K: factor times 1.1. Below 0.1 K: factor times 0.95. The factor stays between 0.25 and 2.5.
- With a *Flow temperature sensor*, learning happens separately for below 60 °C, 60 to 70 °C and above 70 °C.

### Optimize regulation

While the brake only concerns the approach to the target, this function assesses the regulation as a whole and adjusts kp and ki.

| Level | Behavior |
| --- | --- |
| **Manual** | Default. Nothing is measured. |
| **Observe only** | Measures and suggests, the regulation stays unchanged. |
| **Automatic** | Small steps are carried out automatically. |

**Measured** is every heating phase that starts at least 0.5 K below the target: the heat-up time per kelvin, then for three hours
overshoot, undershoot and swinging around the target. A room that does not reach the target within eight hours counts as a slow
phase.

**Not counted** are phases with an open window, a block by warm days, a failed sensor, a changed target or a change at the device.
If the target changes at least one hour after reaching it, what was measured up to there still counts. If only the air conditioner
heats, nothing is measured.

**Evaluated** after five phases, using the median, so an outlier such as sun on the sensor has no effect:

| Finding (median) | Step |
| --- | --- |
| At least 2 swings | kp times 0.9, ki times 0.85 |
| Overshoot above 0.3 K | ki times 0.85 |
| Undershoot above 0.3 K | ki times 1.1 |
| Above 3 hours per kelvin and overshoot below 0.1 K | kp times 1.1 |
| Otherwise | No change |

The factors stay between 0.5 and 2. The values you set remain untouched and form the basis. If the result gets worse after a step,
ThermGenie takes it back and does not try it again for three evaluations.

**Reading the status:** Under Diagnostic, *Optimization* shows Off, Measuring or Suggestion available. Its attributes hold the number
of phases, the factors, the last measurement, the suggestion and the latest steps. *Current kp* and *Current ki* show what the
heating runs on right now. Suggestions and steps are also in the logbook.

**Resetting:** *Forget what was learned* resets the brake factors and the optimization. The log of the phases stays.

**Recommendation:** Start with *Observe only*. With one or two heating phases a day, it takes about three to five days until the
first suggestion. The optimization only covers heating with radiators. Radiator thermostats with their own control react slowly,
which is why the steps are deliberately small.

## 5. Everyday routines

Each routine has a switch *Routine: …* on the device page and an entry in the details. The service `thermgenie.set_routine` switches
it as well. The state survives restarts.

### Sleep and presence

| | |
| --- | --- |
| **Purpose** | Setback when nobody needs the warmth |
| **Needs** | *Sleeping*. *Presence* is optional and only works together with *Sleeping*. |
| **Trigger** | A change of either entity |
| **Behavior** | Asleep or nobody home: Eco preset. Otherwise: Comfort preset. |

The routine only acts on the heating values and does not change the mode. If a state is unknown, nothing happens. A target set by
hand survives a restart of Home Assistant.

### Wake-up heating

| | |
| --- | --- |
| **Purpose** | Warm when the alarm rings |
| **Needs** | *Alarm* (`input_datetime`) or *Heat up without an alarm too* |
| **Trigger** | Alarm time minus *Heat up before the alarm* (default 45 minutes) |
| **Behavior** | Changes to Comfort, unless already active |

Without a future alarm, the fixed time *Heat up without an alarm at* (default 07:15) applies, if you want that. With *Time from an
entity* it comes from an entity, which then takes priority. If the alarm has already rung today, the fixed time only applies again
tomorrow. The sensor *Next heating up* shows the moment.

The routine only acts on the heating values and does not start a thermostat that is off.

### Way home

| | |
| --- | --- |
| **Purpose** | Warm when you get home |
| **Needs** | *Direction*, *Distance*, *Presence* |
| **Trigger** | Direction reports `towards`, distance below *Heat up below* (default 20 km), presence is `not_home` |
| **Behavior** | Heat mode with *Target* (default 21 °C) |

The sensors of the *Proximity* integration are suitable. The routine triggers once on entering this state, so a target changed on
the road stays. **It also switches the heating on if the thermostat was off.** It does not trigger with a heating lock.

### Boost

*Boost ends after* decides when the Boost preset falls back to Comfort. At 0 it stays until you change it. The details show the end
time.

### Windows

| Situation | Radiators | Air conditioner |
| --- | --- | --- |
| Window open, after a delay (default 120 s) | Frost protection value | Off |
| Window closed, after a delay (default 30 s) | Regulates as before | Regulates as before |

A brief opening therefore triggers nothing. Combine several contacts in a group beforehand.

### Warm days

| | |
| --- | --- |
| **Purpose** | No heating when it is warm outside |
| **Needs** | *Outdoor sensor* |
| **Behavior** | Above *Block heating above* (default 20 °C), heating is blocked. Below *Release below* (default 17 °C), it is released. |

The change only happens once the state has held for 30 minutes. Between the two values, the previous state stays. The mode stays on
heat, the thermostat shows that it is warm outside. Cooling is not affected.

## 6. Air and summer routines

### Move the air

| | |
| --- | --- |
| **Purpose** | Distribute warm or cold air in the room |
| **Needs** | *Fan* (`fan`). *Second sensor* is optional. |
| **Trigger** | The thermostat is actually heating or cooling, depending on *While heating* and *While cooling* |
| **Behavior** | The fan runs at *Speed* (default 30 %) and stops once the condition ends |

With a second sensor, for example under the ceiling, it only runs if the difference to the room sensor is at least *Start at a
difference of* (default 1.5 K). It stops below *Stop below a difference of* (default 0.5 K).

A fan switched on by hand is left alone, ThermGenie only stops what it started itself. If the night cascade runs with the same fan,
it takes priority.

### Heat guard

Starts cooling ahead of time when it is hot and someone is on the way home. It needs *Felt temperature*, *Distance from home* and
*Presence*. **All** conditions have to be met:

- Felt temperature above *Start above* (default 23.2 °C), for at least 20 minutes
- Presence is `not_home`, for at least 20 minutes
- Distance below *Only below* (default 100 km)
- Thermostat off for at least 30 minutes, window closed
- Last used preset group is cooling, or the [warm days](#warm-days) block is active
- Time between *Not before* and *Not after* (default 08:00 to 20:00)
- Last start at least 12 hours ago

The thermostat then starts in cool mode with the Eco preset and reports this by push. If the air conditioner does not start, you
receive an urgent message.

### Drying limit

Ends dry mode before the air gets too dry. This happens when the *Dew point* is below *Stop below* (default 9 °C) or the *Humidity* is
below *Stop below* (default 40 %), each for 20 minutes. The thermostat goes off and reports this by push. One sensor is enough.

### Night cascade

Regulates the sleeping climate: a fan does the fine, fast work and the air conditioner only follows slowly. This keeps the room quiet
and the air conditioner running as little as possible.

**Needs:** *Sleep focus*, *Fan*, *Presence*, *Felt temperature at the bed* and *Real temperature at the bed*. *Sensors that have to be
current* and *Start of sleep* are optional.

**Only runs if** the sleep focus is on, the **fan is already running** (the cascade does not switch it on), someone is home and at
least one sensor has reported in the last 90 minutes. If a temperature is missing, it calculates with 23 °C.

**Sequence every 5 minutes:**

1. **Zero point:** *Zero point* (default 22.4 °C) plus *Drift per hour of sleep* (default 0.15 K), up to 7 hours. The body needs less
   cooling towards the morning.
2. **Demand:** The distance of the felt temperature to the zero point gives 0 to 100 %. At 2 K it is 100 %.
3. **Limits:** The fan stays between *Fan at least* (15 %) and *Fan at most* (60 %). While cooling, *Fan at least while cooling* (30 %)
   applies. On a hot night from *Hot night from* (24 °C real), *Fan at most on hot nights* (80 %) is allowed. Below *Too cold below*
   (21 °C real) or with hardly any demand, it is throttled to the minimum.
4. **Fan:** A command is only sent if it changes by at least 8 %.
5. **Air conditioner:** Only in cool mode and only every 15 minutes. If the fan is not enough, the target drops by 0.5 K. If demand is
   below the cooling minimum, it rises by 0.5 K up to the Comfort value.

**Lower limit of the air conditioner:** *at the start of sleep* 20.5 °C, *from 4 hours* 21 °C, *from 6 hours* 22 °C, and never more than
2 K below the Comfort value.

**In the morning:** If the sleep focus goes off after more than 3 hours, the fan stops. The thermostat returns to Comfort and goes off.
A running heating is not affected. The logbook shows every pass with all values.

## 7. Protection and monitoring

### Heating lock

For rooms that should not be heated. It is switched on under *Configure → Heating lock* and is deliberately not an entity, so that it
cannot be lifted through dashboards or voice assistants.

**Heating is refused**, whether from a card, an automation or a voice assistant. Off and cool remain possible. The **devices are always
held** (see below).

**If the heating becomes active anyway or a valve opens:**

1. The device is closed at once, followed by an urgent push message.
2. ThermGenie waits *Time to wait for closing* (default 300 s) for the valve.
3. If it stays open, the command is repeated and it waits again.
4. If it still stays open, a critical alarm follows, which also breaks through silent modes, plus a spoken message.

**Frost:** If the room falls to *Frost protection starts at* (default 6 °C), the lock is set aside and the room is heated up to *Frost
protection ends at* (default 8 °C). Then the lock applies again. You receive a message, with a hint if the window is open. The binary
sensor *Frost protection active* shows this state.

### Hold devices

With *Hold the devices against changes*, ThermGenie sets back every change at the device at once and notes it in the logbook. Devices
without an off mode are closed through their lowest setpoint.

Right after its own command, ThermGenie waits 30 seconds, because radio devices may still report the old value for a moment. **Limit:**
ThermGenie only sees what the device reports. Some radio thermostats do not reliably report changes at the dial. A valve position that
is set up covers these cases.

### Valve monitoring

Under *Hold devices and valves*, set a sensor with the valve opening in percent for each radiator.

A radiator **should be closed** if it is off or its setpoint is at least 1 K below its own measurement. If the valve is then at least at
*A valve counts as open from* (default 5 %), for as long as *Warn after* (default 30 minutes), you receive an urgent message. The binary
sensor *Valve does not close* becomes active. When the valve closes, it becomes inactive again and the logbook notes this.

Radiator thermostats regulate themselves and do not always follow the setpoint. If you get warnings although everything is fine, raise
the limit or the waiting time. In a room with a heating lock, an open valve triggers the lock.

### Failures

| Failure | Behavior |
| --- | --- |
| **Room sensor** goes silent | The devices receive the target and regulate themselves. Binary sensor *Room sensor failed*. |
| **One device** cannot be reached | The others keep running. When it returns, it is brought in line at once. |
| **A command** fails | It is repeated in the next cycle. |
| **Home Assistant** restarts | Mode, presets, I part and routines switched off stay. A running measurement of the optimization is lost. |

## 8. Entities and services

Expose only the `climate` entity to voice assistants and Matter bridges. The modes available there are determined by the bridge and the
assistant.

### Sensors

| Entity | Content | Requirement |
| --- | --- | --- |
| Humidex, Dew point, Comfort temperature | Calculated values | Humidity sensor |

### Diagnostic

| Entity | Content | Requirement |
| --- | --- | --- |
| Blocked by | None, window or warm days | |
| Setpoint *device* | Last command; attributes: offset, brake, I store | Per device |
| Room sensor failed | On/off | |
| Frost protection active | On/off | Heating lock |
| Valve does not close | On/off | Valve sensor |
| Next heating up | Moment | Alarm or sleep |
| Overshoot, Brake factor | Last heating phase, learned factor | Learning brake |
| Optimization, Current kp, Current ki | See [Optimize regulation](#optimize-regulation) | Heaters |

### Services

| Service | Effect |
| --- | --- |
| `climate.set_hvac_mode`, `set_temperature`, `set_preset_mode`, `turn_on`, `turn_off` | Standard services, heating is refused with a heating lock |
| `thermgenie.set_routine` | Switches a routine: `sleep`, `wake`, `way_home`, `guard`, `cascade`, `dry`, `air` |
| `thermgenie.reset_learning` | Forgets brake factors and optimization |

```yaml
action: thermgenie.set_routine
target:
  entity_id: climate.living_room
data:
  routine: way_home
  enabled: false
```

## 9. Messages

Set a *Push service* (`notify.…`). For spoken messages, *Speech service* and *Speakers* are added. Messages are only spoken if someone is
home and *No speech while on* is not active.

| Occasion | Push | Logbook | Speech |
| --- | --- | --- | --- |
| Heat guard started | Normal | Yes | |
| Heat guard failed | Urgent | Yes | |
| Drying stopped | Normal | Yes | |
| Valve does not close | Urgent | Yes | |
| Heating lock switched off | Urgent | Yes | |
| Frost protection starts | Urgent | Yes | |
| Valve stuck with a heating lock | Critical | Yes | Yes |
| Device set back, night cascade, optimization | | Yes | |

Urgent and critical levels use the format of the iOS Companion app. Other receivers ignore them.

## 10. Troubleshooting

| Observation | Possible cause |
| --- | --- |
| Room does not reach the target | Correction at its limit (*Largest setpoint shift*), check the setpoint under Diagnostic. Device at maximum or no heating power. |
| Room overshoots the target | The brake is off by default: raise *D gain*, for example to 0.5, and let it learn |
| Regulation reacts slowly | Check the regulation period and the smallest step. Changes below 0.5 K are not sent. |
| No heating despite heat mode | Check *Blocked by* under Diagnostic. Window open or warm days? Right heat source? |
| Air conditioner does not heat | Check *Heat with*. Does the device offer the `heat` mode and can it be reached? |
| Room temperature on the card differs from the sensor | *Regulate on* is set to humidex or comfort temperature. |
| Absence does not lower the temperature | *Sleeping* is not set, or the routine is off. |
| Wake-up heating does not happen | Thermostat is off or on cool. Alarm lies in the past. |
| Night cascade does nothing | The fan has to be running. Focus on, someone home, sensors current? Check the logbook. |
| Heat guard does not start | All conditions have to be met at once, see [Heat guard](#heat-guard). |
| "Valve does not close" warning without a real fault | The valve regulates itself. Raise the limit or waiting time. |
| Optimization shows only "Measuring" for a long time | It takes five clean phases from a gap of 0.5 K. Check the diagnostic attribute *phases*. |
| Setting missing on the device page | Disabled at first: enable it in the entity list. Heating values are hidden with a heating lock. |
| Card shows an old state | Clear the browser cache or reload the app. |
