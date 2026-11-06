"""Constants of ThermGenie."""

DOMAIN = "thermgenie"

CONF_NAME = "name"
CONF_SENSOR = "temperature_sensor"
CONF_HEATERS = "heaters"
CONF_COOLER = "cooler"
CONF_WINDOW = "window_sensor"
CONF_OFFSETS = "offsets"
ROUTINE_NAMES = ("sleep", "wake", "way_home", "guard", "cascade", "dry", "air")
CONF_OUTDOOR = "outdoor_sensor"
CONF_OUTDOOR_OFF = "outdoor_off_above"
CONF_OUTDOOR_ON = "outdoor_on_below"
CONF_KP = "kp"
CONF_KI = "ki"
CONF_KD = "kd"
CONF_OFFSET_MAX = "offset_max"
CONF_PERIOD = "period_min"
CONF_DTEMP = "dtemp"
CONF_SENSOR_TIMEOUT = "sensor_timeout_min"
CONF_WINDOW_OPEN_DELAY = "window_open_delay"
CONF_WINDOW_CLOSE_DELAY = "window_close_delay"

CONF_HUMIDITY = "humidity_sensor"
CONF_REFERENCE_HEAT = "reference_heat"
CONF_REFERENCE_COOL = "reference_cool"
CONF_KD_HEATERS = "kd_heaters"
CONF_KP_COOL = "kp_cool"
CONF_KI_COOL = "ki_cool"
CONF_KD_COOL = "kd_cool"
CONF_OFFSET_MAX_COOL = "offset_max_cool"
CONF_INTEGRAL_LIMIT = "integral_limit"
CONF_INTEGRAL_LIMIT_COOL = "integral_limit_cool"
CONF_DEVICE_TEMP = "use_device_temp"
CONF_FAN_BOOST = "fan_boost"
CONF_LEARN = "learn"
CONF_FLOW = "flow_sensor"
CONF_BOOST_MINUTES = "boost_minutes"

CONF_NOTIFY = "notify_service"
CONF_TTS = "tts_service"
CONF_TTS_TARGETS = "tts_targets"
CONF_QUIET = "quiet_entity"
CONF_PRESENCE = "presence_entity"

CONF_SLEEP = "sleep_entity"
CONF_WAKE = "wake_entity"
CONF_WAKE_LEAD = "wake_lead_min"
CONF_WAKE_FALLBACK = "wake_fallback"
CONF_WAKE_FALLBACK_ON = "wake_fallback_on"
CONF_WAKE_FALLBACK_ENTITY = "wake_fallback_entity"
CONF_AIR_FAN = "air_fan"
CONF_AIR_HEAT = "air_while_heating"
CONF_AIR_COOL = "air_while_cooling"
CONF_AIR_COMPARE = "air_compare_sensor"
CONF_AIR_ON = "air_difference_on"
CONF_AIR_OFF = "air_difference_off"
CONF_AIR_PERCENT = "air_percent"
CONF_APPROACH_DIRECTION = "approach_direction"
CONF_APPROACH_DISTANCE = "approach_distance"
CONF_APPROACH_BELOW = "approach_below"
CONF_APPROACH_TARGET = "approach_target"

CONF_LOCK = "lock_enabled"
CONF_LOCK_VALVE = "lock_valve"  # before version 3 of the settings, now in CONF_VALVES
CONF_LOCK_FROST_ON = "lock_frost_on"
CONF_LOCK_FROST_OFF = "lock_frost_off"
CONF_LOCK_WAIT = "lock_wait_sec"

CONF_TUNING = "tuning"
TUNING_MANUAL = "manual"
TUNING_OBSERVE = "observe"
TUNING_AUTOMATIC = "automatic"
CONF_HEAT_SOURCE = "heat_source"
HEAT_RADIATORS = "radiators"
HEAT_AIR_CONDITIONER = "air_conditioner"
HEAT_BOTH = "both"
CONF_HOLD_DEVICES = "hold_devices"
CONF_VALVES = "valves"
CONF_VALVE_LIMIT = "valve_limit"
CONF_VALVE_WAIT = "valve_wait_min"

CONF_GUARD_SENSOR = "guard_sensor"
CONF_GUARD_ABOVE = "guard_above"
CONF_GUARD_DISTANCE = "guard_distance"
CONF_GUARD_BELOW = "guard_below"
CONF_GUARD_FROM = "guard_from"
CONF_GUARD_UNTIL = "guard_until"
CONF_DRY_DEW = "dry_dew_sensor"
CONF_DRY_DEW_BELOW = "dry_dew_below"
CONF_DRY_HUMIDITY = "dry_humidity_sensor"
CONF_DRY_HUMIDITY_BELOW = "dry_humidity_below"

CONF_CASCADE_FOCUS = "cascade_focus"
CONF_CASCADE_FAN = "cascade_fan"
CONF_CASCADE_FELT = "cascade_felt"
CONF_CASCADE_REAL = "cascade_real"
CONF_CASCADE_FRESH = "cascade_fresh"
CONF_CASCADE_START = "cascade_sleep_start"
CASCADE_NUMBERS = {
    "cascade_base": ("base", 22.4),
    "cascade_drift": ("drift", 0.15),
    "cascade_fan_cap": ("fan_cap", 60),
    "cascade_fan_cap_hot": ("fan_cap_hot", 80),
    "cascade_fan_floor": ("fan_floor", 15),
    "cascade_fan_floor_cooling": ("fan_floor_cooling", 30),
    "cascade_hot": ("hot", 24.0),
    "cascade_cold": ("cold", 21.0),
    "cascade_limit_early": ("limit_early", 20.5),
    "cascade_limit_mid": ("limit_mid", 21.0),
    "cascade_limit_late": ("limit_late", 22.0),
}

REFERENCE_TEMPERATURE = "temperature"
REFERENCE_HUMIDEX = "humidex"
REFERENCE_COMFORT = "comfort"

PRESET_FROST = "frost"
PRESET_ECO = "eco"
PRESET_COMFORT = "comfort"
PRESET_BOOST = "boost"

DEFAULT_PRESETS = {
    "heat_frost": 7.0,
    "heat_eco": 19.0,
    "heat_comfort": 21.0,
    "heat_boost": 23.0,
    "cool_eco": 26.0,
    "cool_comfort": 24.0,
    "cool_boost": 22.0,
}

DEFAULTS = {
    CONF_OUTDOOR_OFF: 20.0,
    CONF_OUTDOOR_ON: 17.0,
    CONF_KP: 0.3,
    CONF_KI: 0.05,
    CONF_KD: 0.0,
    CONF_OFFSET_MAX: 2.0,
    CONF_PERIOD: 5,
    CONF_DTEMP: 0.5,
    CONF_SENSOR_TIMEOUT: 120,
    CONF_WINDOW_OPEN_DELAY: 120,
    CONF_WINDOW_CLOSE_DELAY: 30,
    CONF_REFERENCE_HEAT: REFERENCE_TEMPERATURE,
    CONF_REFERENCE_COOL: REFERENCE_TEMPERATURE,
    CONF_KP_COOL: 0.3,
    CONF_KI_COOL: 0.05,
    CONF_KD_COOL: 0.0,
    CONF_OFFSET_MAX_COOL: 2.0,
    CONF_INTEGRAL_LIMIT: 20.0,
    CONF_INTEGRAL_LIMIT_COOL: 20.0,
    CONF_DEVICE_TEMP: False,
    CONF_FAN_BOOST: False,
    CONF_LEARN: False,
    CONF_TUNING: TUNING_MANUAL,
    CONF_BOOST_MINUTES: 0,
    CONF_WAKE_LEAD: 45,
    CONF_WAKE_FALLBACK: "07:15:00",
    CONF_WAKE_FALLBACK_ON: False,
    CONF_AIR_HEAT: True,
    CONF_AIR_COOL: True,
    CONF_AIR_ON: 1.5,
    CONF_AIR_OFF: 0.5,
    CONF_AIR_PERCENT: 30,
    CONF_APPROACH_BELOW: 20000.0,
    CONF_APPROACH_TARGET: 21.0,
    CONF_LOCK: False,
    CONF_LOCK_FROST_ON: 6.0,
    CONF_LOCK_FROST_OFF: 8.0,
    CONF_LOCK_WAIT: 300,
    CONF_HEAT_SOURCE: HEAT_RADIATORS,
    CONF_HOLD_DEVICES: False,
    CONF_VALVE_LIMIT: 5.0,
    CONF_VALVE_WAIT: 30,
    CONF_GUARD_ABOVE: 23.2,
    CONF_GUARD_BELOW: 100000.0,
    CONF_GUARD_FROM: "08:00:00",
    CONF_GUARD_UNTIL: "20:00:00",
    CONF_DRY_DEW_BELOW: 9.0,
    CONF_DRY_HUMIDITY_BELOW: 40.0,
    **{key: value for key, (_, value) in CASCADE_NUMBERS.items()},
    **DEFAULT_PRESETS,
}

FAN_BOOST_GAP = 2.0  # K between room and setpoint that turns the fan up
FAN_QUIET_MODES = ("mute", "quiet", "low", "1", "one", "speed_1", "auto")
HOLD_SEC = 1200  # sensor conditions of the routines have to hold this long
GUARD_OFF_SEC = 1800
GUARD_COOLDOWN_SEC = 43200
OUTDOOR_HOLD_SEC = 1800
COMMAND_TIMEOUT_SEC = 30
HOLD_WAIT_SEC = 30  # after a command a radio device may still report its old value, and the radio has a budget
CLOSE_ABOVE = 0.5  # K past the target that shut a radiator instead of slowly counting its setpoint down
CLOSE_RELEASE = 0.2  # K past the target at which it regulates again
