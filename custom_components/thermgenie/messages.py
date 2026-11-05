"""Pushes, announcements and logbook entries: German on a German system, English everywhere else."""

from homeassistant.core import HomeAssistant

_TEXTS: dict[str, tuple[str, str]] = {
    # key: German, English
    "valve_watch_title": ("{name}: Ventil schließt nicht", "{name}: valve does not close"),
    "valve_watch_body": (
        "{device} sollte zu sein, das Ventil steht seit {minutes} Minuten noch auf {valve} %.",
        "{device} should be closed, its valve has been at {valve} % for {minutes} minutes.",
    ),
    "valve_watch_ok": ("{device}: Das Ventil ist wieder zu oder darf offen sein.", "{device}: the valve is closed again or may be open."),
    "tuning_step": ("Regelung angepasst: {reason}. Jetzt kp {kp}, ki {ki}.", "Regulation adjusted: {reason}. Now kp {kp}, ki {ki}."),
    "tuning_proposal": ("Vorschlag zur Regelung: {reason}. Empfohlen sind kp {kp}, ki {ki}.", "Suggestion for the regulation: {reason}. Recommended are kp {kp}, ki {ki}."),
    "tuning_swinging": ("Der Raum pendelt um das Ziel", "the room swings around the target"),
    "tuning_overshoot": ("Der Raum schießt über das Ziel hinaus", "the room overshoots the target"),
    "tuning_sagging": ("Der Raum fällt nach dem Ziel wieder ab", "the room drops again after the target"),
    "tuning_slow": ("Der Raum heizt langsam auf", "the room heats up slowly"),
    "tuning_back": ("Der letzte Schritt hat es verschlechtert und wurde zurückgenommen", "the last step made it worse and was taken back"),
    "device_held": ("{device} wurde am Gerät verstellt und wird zurückgesetzt.", "{device} was changed at the device and is being set back."),
    "guard_log": ("Hitzeschutz: {felt} gefühlt, im Eco-Preset gestartet (Ziel {target}).", "Heat guard: felt {felt}, started on the eco preset (target {target})."),
    "guard_title": ("Klima automatisch gestartet", "Air conditioner started automatically"),
    "guard_body": (
        "Es war {felt} Grad gefühlt. Die Klima läuft jetzt im Eco-Preset auf {target} als Hitzeschutz. Einfach ausschalten, falls nicht gewünscht.",
        "It felt like {felt} degrees. The air conditioner now runs on the eco preset at {target} as a heat guard. Just switch it off if you do not want that.",
    ),
    "guard_failed_title": ("Hitzeschutz fehlgeschlagen", "Heat guard failed"),
    "guard_failed_body": (
        "Es war {felt} Grad gefühlt, die Klima ließ sich aber nicht starten. Bitte von Hand einschalten.",
        "It felt like {felt} degrees, but the air conditioner did not start. Please switch it on by hand.",
    ),
    "dry_body": (
        "Entfeuchten beendet bei Taupunkt {dew} und {humidity} % Feuchte. Trockener sollte es nicht werden.",
        "Drying stopped at dew point {dew} and {humidity} % humidity. It should not get any drier.",
    ),
    "dry_title": ("Entfeuchten beendet", "Drying stopped"),
    "cascade_name": ("Nachtklima", "Night climate"),
    "woke_up": ("Aufgestanden nach {hours} h, Klima und Ventilator aus.", "Up after {hours} h, air conditioner and fan off."),
    "cascade_log": (
        "[{scenario}] {felt} gefühlt / {real} real | Basis {base} | Lücke {gap} K -> Bedarf {demand} % | Deckel {cap} Boden {floor} | Lüfter {fan_now} -> {fan} %{extra} | Ziel {target} | {hours} h Schlaf",
        "[{scenario}] {felt} felt / {real} real | base {base} | gap {gap} K -> demand {demand} % | cap {cap} floor {floor} | fan {fan_now} -> {fan} %{extra} | target {target} | {hours} h asleep",
    ),
    "cascade_cold": (" | KALT", " | COLD"),
    "cascade_hot": (" | HITZE", " | HOT"),
    "cascade_target": (
        "Ziel {target} -> {new} (Bedarf {demand} %, Deckel {cap} %, Untergrenze {lower}).",
        "Target {target} -> {new} (demand {demand} %, cap {cap} %, lower limit {lower}).",
    ),
    "frost_log": ("Heizsperre: Frostschutz bei {room} Grad, Sperre ausgesetzt bis {target} Grad.", "Heating lock: frost protection at {room} degrees, lock set aside until {target} degrees."),
    "frost_title": ("{name}: Frostschutz aktiv", "{name}: frost protection active"),
    "frost_body": (
        "Nur noch {room} Grad. Die Heizsperre ist ausgesetzt, geheizt wird bis {target} Grad.{hint}",
        "Only {room} degrees left. The heating lock is set aside, heating up to {target} degrees.{hint}",
    ),
    "frost_end": ("Heizsperre: Frostschutz beendet bei {room} Grad, Sperre wieder aktiv.", "Heating lock: frost protection ended at {room} degrees, lock active again."),
    "window_hint": (" Das Fenster steht offen.", " The window is open."),
    "reason_valve": ("Das Ventil stand auf {valve} %", "The valve was at {valve} %"),
    "reason_heat": ("Die Heizung wurde eingeschaltet", "The heating was switched on"),
    "lock_log": ("Heizsperre: {reason} bei {room} Grad, kein Frostfall. Abgeschaltet.", "Heating lock: {reason} at {room} degrees, no frost. Switched off."),
    "lock_title": ("{name}: Heizung sofort abgeschaltet", "{name}: heating switched off at once"),
    "lock_body": (
        "{reason} bei {room} Grad Raumtemperatur. Hier gilt die Heizsperre, nur Frost hebt sie auf.",
        "{reason} at a room temperature of {room} degrees. The heating lock applies here, only frost lifts it.",
    ),
    "valve_closed": ("Heizsperre: Ventil ist zu.", "Heating lock: valve is closed."),
    "valve_repeat": ("Heizsperre: Ventil nach der Wartezeit noch offen, Befehl wiederholt.", "Heating lock: valve still open after the wait, command repeated."),
    "valve_closed_2": ("Heizsperre: Ventil nach dem zweiten Befehl zu.", "Heating lock: valve closed after the second command."),
    "valve_stuck": (
        "Das Ventil steht nach zwei Abschaltbefehlen immer noch auf {valve} %. Es lässt sich per Funk nicht schließen, bitte am Heizkörper nachsehen.",
        "The valve is still at {valve} % after two commands to close. It cannot be closed by radio, please check the radiator.",
    ),
    "valve_log": ("Heizsperre: ESKALATION. {message}", "Heating lock: ESCALATION. {message}"),
    "valve_title": ("{name}: Ventil klemmt", "{name}: valve is stuck"),
    "valve_say": ("Achtung. Das Heizungsventil im Raum {name} lässt sich nicht schließen.", "Attention. The heating valve in the room {name} cannot be closed."),
}


def say(hass: HomeAssistant, key: str, **values: object) -> str:
    """Return the text in the language of the system."""
    german, english = _TEXTS[key]
    return (german if hass.config.language.startswith("de") else english).format(**values)
