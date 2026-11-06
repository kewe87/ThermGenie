# ThermGenie Handbuch

**Deutsch** · [English](../en/manual.md) · [Zurück zur Übersicht](../../README.md)

Dieses Handbuch beschreibt alle Funktionen von ThermGenie: was sie tun, wann sie auslösen, was sie brauchen und womit sie
sich einstellen lassen. Für einen ersten Überblick genügt die [README](../../README.md).

## Inhalt

1. [Grundprinzip](#1-grundprinzip)
2. [Einrichtung](#2-einrichtung)
3. [Bedienung](#3-bedienung)
4. [Regelung](#4-regelung)
5. [Automatiken im Alltag](#5-automatiken-im-alltag)
6. [Automatiken für Luft und Sommer](#6-automatiken-für-luft-und-sommer)
7. [Schutz und Überwachung](#7-schutz-und-überwachung)
8. [Entitäten und Dienste](#8-entitäten-und-dienste)
9. [Meldungen](#9-meldungen)
10. [Fehlersuche](#10-fehlersuche)

## 1. Grundprinzip

Ein ThermGenie-Thermostat steht für einen Raum. Es besitzt einen **Raumfühler** und führt bis zu sechs **Heizgeräte** sowie
ein **Klimagerät**. Alle sind vorhandene `climate`-Entitäten aus Home Assistant.

ThermGenie misst nicht selbst und schaltet kein Ventil direkt. Es vergleicht den Raumfühler mit dem Sollwert und gibt jedem
Gerät einen verschobenen Sollwert. Das Gerät regelt dann mit seiner eigenen Technik weiter. Ist es im Raum zu kalt, erhält
das Gerät einen höheren Wert, ist es zu warm, einen niedrigeren.

Drei Regeln gelten immer:

- **Eine Betriebsart zur selben Zeit.** Heizen und Kühlen laufen nie gleichzeitig. Einen automatischen Wechsel zwischen beiden
  gibt es nicht, mit Ausnahme des [Hitzeschutzes](#hitzeschutz).
- **Eine Funktion ist aus, solange ihre Entität fehlt.** Sie müssen nichts abschalten, was Sie nicht eingerichtet haben.
- **Fällt etwas aus, läuft der Rest weiter.** Siehe [Ausfälle](#ausfälle).

## 2. Einrichtung

### Neues Thermostat anlegen

Unter *Einstellungen → Geräte & Dienste → Integration hinzufügen → ThermGenie* führt ein Assistent durch diese Schritte:

| Schritt | Inhalt |
| --- | --- |
| Neues Thermostat | Name, Raumfühler, Luftfeuchte, Heizgeräte, Klimaanlage, Fensterkontakt |
| Versatz und Bremse | Je Heizgerät, siehe [Mehrere Heizgeräte](#mehrere-heizgeräte) |
| Warme Tage | Außenfühler und Grenzwerte |
| Temperaturen | Werte der Profile |
| Alltag und Meldungen | Dienste und Entitäten der Automatiken |

Erforderlich sind nur der Raumfühler und mindestens ein Gerät. Alles andere lässt sich später ergänzen.

### Raumfühler wählen

Wählen Sie den Fühler dort, wo die Temperatur zählt, also im Aufenthaltsbereich. Er sollte nicht in der Sonne, über dem
Heizkörper oder in der Zugluft stehen. Er sollte zudem regelmäßig senden: Bleibt er länger aus als *Raumfühler gilt als
ausgefallen nach* (Standard 120 Minuten), gilt er als ausgefallen.

### Einstellungen ändern

Es gibt zwei Orte:

| Ort | Was dort liegt | Wirkung |
| --- | --- | --- |
| **Geräteseite** des Thermostats | Temperaturen, Grenzwerte, Zeiten, Automatiken, Reglerwerte | Sofort, der Regler behält seinen Zustand |
| **Konfigurieren** in der Integration | Zuordnung der Entitäten, Heizsperre, Frostgrenzen, alle Werte zusätzlich | Mit *Speichern und schließen*, das Thermostat startet dabei neu |

Einige Werte sind auf der Geräteseite zunächst deaktiviert, etwa kp und ki. Sie lassen sich dort einzeln aktivieren.
In einem Raum mit Heizsperre sind Heizwerte ausgeblendet, weil sie dort nichts bewirken.

### Einrichtung mit KI

Ist ein KI-Dienst (`ai_task`) eingerichtet, bietet das Menü *Per KI einrichten*. Die KI schlägt Geräte, Fühler und
Temperaturen vor, Sie prüfen diese, und erst das Speichern übernimmt sie. An den Anbieter gehen Namen, Bereiche und Arten der
infrage kommenden Entitäten sowie die aktuellen Einstellungen des Thermostats, jedoch keine Messwerte oder Zustände.

## 3. Bedienung

### Karte

```yaml
type: custom:thermgenie-card
entity: climate.wohnzimmer
```

Die Karte zeigt Status, Raumtemperatur und Sollwert. Ein Tipp öffnet das Bedienfeld. Sie erscheint automatisch in der
Kartenauswahl. Gesperrte Räume zeigen keinen Sollwert.

### Bedienfeld

**Bedienung** enthält Drehregler, Betriebsart und Profile. **Details** enthält:

- **Automatik:** Alle eingerichteten Automatiken. Ein Tipp schaltet eine Automatik für dieses Thermostat ein oder aus.
- **Raumklima:** Luftfeuchte und Taupunkt. Regelt der Raum nach Humidex oder gefühlter Temperatur, steht dieser Wert dabei.
- **Geräte:** Stellwert und Zustand jedes Geräts.
- **Letzte 24 Stunden:** Raumtemperatur, Sollwert und Laufzeiten.
- **Gerät und Einstellungen:** Führt Administratoren zur Geräteseite.

### Betriebsarten

| Betriebsart | Verhalten |
| --- | --- |
| **Aus** | Alle Geräte werden ausgeschaltet. Geräte ohne Aus-Modus gehen auf ihren niedrigsten Sollwert. |
| **Heizen** | Die gewählte [Heizquelle](#heizquelle) arbeitet, die übrigen Geräte sind aus. |
| **Kühlen** | Das Klimagerät arbeitet, die Heizgeräte sind aus. |
| **Trocknen, Lüfter** | Sofern das Klimagerät sie anbietet. Es arbeitet dann nach eigener Logik, ohne Eingriff des Reglers. |

Ein Klimagerät, das ThermGenie nicht gestartet hat, wird im nächsten Regeltakt wieder ausgeschaltet, wenn es gerade nicht
arbeiten soll.

### Profile

Heizen und Kühlen haben getrennte Werte. Das Thermostat merkt sich beide.

| Profil | Heizen, Standard | Kühlen, Standard |
| --- | --- | --- |
| Frostschutz | 7 °C | |
| Eco | 19 °C | 26 °C |
| Komfort | 21 °C | 24 °C |
| Boost | 23 °C | 22 °C |

Ändern Sie den Sollwert von Hand, ist kein Profil mehr aktiv. Ändern Sie den Wert eines Profils, folgt ein Thermostat, das
gerade in diesem Profil steht, sofort.

## 4. Regelung

### So entsteht der Stellwert

In jedem Regeltakt (Standard 5 Minuten) rechnet ThermGenie für jedes Gerät:

```
Stellwert = Sollwert + Versatz + P-Anteil + I-Anteil − Bremse
```

| Teil | Bedeutung | Einstellung, Standard |
| --- | --- | --- |
| **P-Anteil** | Abweichung mal Faktor. Reagiert sofort, gleicht aber nicht alles aus. | P-Anteil, 0,3 |
| **I-Anteil** | Summiert die Abweichung über die Zeit und gleicht so den Rest aus. Hinter dem Ziel halbiert sich die Summe je Takt. | I-Anteil, 0,05, Grenze 20 |
| **Bremse** | Nimmt kurz vor dem Ziel Leistung weg, abhängig vom Temperaturanstieg der letzten 30 Minuten. Wirkt erst innerhalb von 1 K vor dem Ziel. | D-Anteil, 0, also aus |
| **Begrenzung** | Die Korrektur aus den drei Teilen bleibt innerhalb dieser Grenze. | Größte Sollwert-Verschiebung, 2 K |

Das Ergebnis wird auf die Schrittweite gerundet und auf den Bereich des Geräts begrenzt. Ein neuer Befehl geht nur hinaus,
wenn sich der Wert um mindestens *Kleinster Schritt je Funkbefehl* (Standard 0,5 K) ändert. Das schont Funkkanal und
Batterien. Nach einer Bedienung werden die Geräte sofort angeglichen.

**Zwei Ausnahmen für Heizkörper,** weil Thermostatventile träge schließen:

- **Raum deutlich zu warm:** Ab 0,5 K über dem Sollwert erhält der Heizkörper seinen niedrigsten Sollwert, statt langsam herunterzuzählen. Unter 0,2 K über dem Sollwert regelt er wieder normal. Die Grenzen gelten auch mit *Sollwert auf den Gerätefühler umrechnen*.
- **Niedrigerer Sollwert:** Der aufgesammelte I-Anteil wird sofort gelöscht, damit er das neue Ziel nicht überheizt.

Fürs Kühlen gibt es einen eigenen Satz dieser Werte. Die Standardwerte passen für die meisten Räume. Ändern Sie nur in kleinen
Schritten und beobachten Sie danach einige Tage.

### Regeln nach

Mit einem Feuchtefühler berechnet ThermGenie drei Werte. Getrennt für Heizen und Kühlen wählen Sie, nach welchem geregelt wird:

| Auswahl | Rechnung | Geeignet für |
| --- | --- | --- |
| **Echte Temperatur** | Der Wert des Raumfühlers | Heizen, Standard |
| **Humidex** | Kanadische Standardformel. Die Feuchte zählt immer und ohne Grenze, der Wert liegt oft einige Grad über der Temperatur. | Kühlen im Hochsommer |
| **Gefühlte Temperatur** | Temperatur plus 0,5 K je Grad Taupunkt über 16 °C, höchstens 2,5 K | Kühlen und Nacht, auch für Innenräume mit normaler Luft |

Die Raumtemperatur in Karte und Bedienfeld zeigt immer den gewählten Wert. Der Sollwert bezieht sich ebenfalls darauf. Bei
Humidex entspricht ein Sollwert von 26 also nicht 26 °C Lufttemperatur. Stellen Sie den Sollwert entsprechend ein. Ohne
Feuchtefühler gilt immer die echte Temperatur.

### Heizquelle

Hat ein Thermostat Heizgeräte **und** ein Klimagerät, legt *Heizen mit* fest, was in der Betriebsart Heizen arbeitet:

| Auswahl | Verhalten |
| --- | --- |
| **Nur Heizkörper** | Standard. Das Klimagerät bleibt aus. |
| **Nur Klimaanlage** | Das Klimagerät heizt, die Heizkörper bleiben aus. |
| **Heizkörper und Klimaanlage** | Beide arbeiten auf denselben Sollwert. |

Die Umstellung wirkt sofort. Es gelten folgende Besonderheiten:

- Bietet das Klimagerät keinen Heizmodus an oder ist es nicht erreichbar, übernehmen die Heizkörper.
- Das Klimagerät nutzt auch beim Heizen die Reglerwerte aus dem Abschnitt Kühlen.
- Bei offenem Fenster geht das Klimagerät aus, Heizkörper gehen auf Frostschutz.
- Thermostate ohne Heizkörper bieten Heizen nicht an, auch wenn das Klimagerät es könnte.

### Mehrere Heizgeräte

Sie können ein Thermostat mehrere Heizkörper führen lassen, auch über mehrere verbundene Räume.

- **Versatz:** Verschiebt den Sollwert dieses Heizkörpers, zum Beispiel −0,5 K für einen, der näher am Raumfühler steht.
- **Bremse:** Ein großer Heizkörper heizt lange nach und braucht eine stärkere Bremse als ein kleiner.

Jeder Heizkörper hat seinen eigenen Regler. Der Ausfall eines Heizkörpers beeinträchtigt die anderen nicht.

### Gerätefühler berücksichtigen

*Sollwert auf den Gerätefühler umrechnen* ist für Geräte gedacht, deren eigener Fühler deutlich vom Raum abweicht, etwa direkt
am warmen Heizkörper. Der Stellwert wird dann um die Differenz zwischen Gerätefühler und Raumfühler verschoben.

### Lernende Bremse

*Bremse aus dem Überschwingen lernen* passt die Bremse nach jeder sauberen Heizphase an. Sie wirkt nur, wenn die Bremse größer
als 0 eingestellt ist, denn sie verändert deren Wert über einen Faktor.

- Eine Heizphase beginnt mindestens 0,3 K unter dem Ziel und endet, sobald die Temperatur 0,1 K unter ihren Höchstwert fällt.
- Überschwingen über 0,3 K: Faktor mal 1,1. Unter 0,1 K: Faktor mal 0,95. Der Faktor bleibt zwischen 0,25 und 2,5.
- Mit einem *Vorlauffühler* wird getrennt für unter 60 °C, 60 bis 70 °C und über 70 °C gelernt.

### Regelung optimieren

Während die Bremse nur das Anfahren des Ziels betrifft, bewertet diese Funktion die Regelung insgesamt und passt kp und ki an.

| Stufe | Verhalten |
| --- | --- |
| **Manuell** | Standard. Es wird nichts gemessen. |
| **Nur beobachten** | Es wird gemessen und vorgeschlagen, die Regelung bleibt unverändert. |
| **Automatisch** | Kleine Schritte werden selbst ausgeführt. |

**Gemessen** wird jede Heizphase, die mindestens 0,5 K unter dem Ziel beginnt: die Aufheizdauer je Kelvin, danach drei Stunden
lang Überschwingen, Unterschreiten und Pendeln um das Ziel. Erreicht der Raum das Ziel nicht binnen acht Stunden, zählt das als
langsame Phase.

**Nicht gezählt** werden Phasen mit offenem Fenster, Sperre durch warme Tage, ausgefallenem Fühler, geändertem Sollwert oder
einer Verstellung am Gerät. Ändert sich der Sollwert frühestens eine Stunde nach Erreichen des Ziels, zählt das bis dahin
Gemessene noch. Heizt nur die Klimaanlage, wird nicht gemessen.

**Ausgewertet** wird nach fünf Phasen mit dem Median, sodass ein Ausreißer, etwa Sonne auf dem Fühler, nichts bewirkt:

| Befund (Median) | Schritt |
| --- | --- |
| Mindestens 2 Pendelbewegungen | kp mal 0,9, ki mal 0,85 |
| Überschwingen über 0,3 K | ki mal 0,85 |
| Unterschreiten über 0,3 K | ki mal 1,1 |
| Über 3 Stunden je Kelvin und Überschwingen unter 0,1 K | kp mal 1,1 |
| Sonst | Keine Änderung |

Die Faktoren bleiben zwischen 0,5 und 2. Ihre eingestellten Werte bleiben dabei unberührt und bilden die Grundlage. Wird das
Ergebnis nach einem Schritt schlechter, nimmt ThermGenie ihn zurück und versucht ihn für drei Auswertungen nicht erneut.

**Stand ablesen:** Unter Diagnose zeigt *Optimierung* Aus, Misst oder Vorschlag liegt vor. Die Attribute enthalten die Anzahl
der Phasen, die Faktoren, die letzte Messung, den Vorschlag und die letzten Schritte. *Aktuelles kp* und *Aktuelles ki* zeigen,
womit gerade geregelt wird. Vorschläge und Schritte stehen zudem im Logbuch.

**Zurücksetzen:** *Gelerntes vergessen* setzt Bremsfaktoren und Optimierung auf Anfang. Das Protokoll der Phasen bleibt.

**Empfehlung:** Beginnen Sie mit *Nur beobachten*. Bei ein bis zwei Heizphasen am Tag vergehen bis zum ersten Vorschlag etwa
drei bis fünf Tage. Die Optimierung betrifft nur das Heizen über Heizkörper. Thermostatventile mit eigener Regelung reagieren
träge, deshalb sind die Schritte bewusst klein.

## 5. Automatiken im Alltag

Jede Automatik hat einen Schalter *Automatik: …* auf der Geräteseite und einen Eintrag in den Details. Der Dienst
`thermgenie.set_routine` schaltet sie ebenfalls. Der Zustand bleibt über Neustarts erhalten.

### Schlaf und Anwesenheit

| | |
| --- | --- |
| **Zweck** | Absenken, wenn niemand die Wärme braucht |
| **Benötigt** | *Schlafen*. *Anwesenheit* ist optional und wirkt nur zusammen mit *Schlafen*. |
| **Auslöser** | Änderung einer der beiden Entitäten |
| **Verhalten** | Schlaf an oder niemand zu Hause: Profil Eco. Sonst: Profil Komfort. |

Die Automatik wirkt nur auf die Heizwerte und schaltet die Betriebsart nicht um. Ist ein Zustand unbekannt, geschieht nichts.
Ein von Hand gesetzter Sollwert übersteht einen Neustart von Home Assistant.

### Aufheizen zum Wecken

| | |
| --- | --- |
| **Zweck** | Warm, wenn der Wecker klingelt |
| **Benötigt** | *Wecker* (`input_datetime`) oder *Ohne Wecker trotzdem aufheizen* |
| **Auslöser** | Weckzeit minus *Vorheizen vor dem Wecker* (Standard 45 Minuten) |
| **Verhalten** | Wechsel auf Komfort, sofern nicht bereits aktiv |

Ist kein künftiger Wecker gestellt, gilt die feste Zeit *Vorheizen ohne Wecker um* (Standard 07:15), wenn Sie dies wünschen.
Mit *Uhrzeit aus Entität* kommt sie aus einer Entität und hat dann Vorrang. Hat der Wecker heute bereits geklingelt, gilt die
feste Zeit erst wieder morgen. Der Sensor *Nächstes Aufheizen* zeigt den Zeitpunkt.

Die Automatik wirkt nur auf die Heizwerte und startet ein ausgeschaltetes Thermostat nicht.

### Heimweg

| | |
| --- | --- |
| **Zweck** | Warm beim Heimkommen |
| **Benötigt** | *Richtung*, *Entfernung*, *Anwesenheit* |
| **Auslöser** | Richtung meldet `towards`, Entfernung unter *Vorheizen unter* (Standard 20 km), Anwesenheit ist `not_home` |
| **Verhalten** | Betriebsart Heizen mit *Zieltemperatur* (Standard 21 °C) |

Geeignet sind die Sensoren der Integration *Proximity*. Die Automatik löst einmal beim Eintritt in diesen Zustand aus, sodass
ein unterwegs geänderter Sollwert bestehen bleibt. **Sie schaltet die Heizung auch ein, wenn das Thermostat aus war.** Bei
Heizsperre löst sie nicht aus.

### Boost

*Boost endet nach* legt fest, wann das Profil Boost auf Komfort zurückfällt. Bei 0 bleibt es, bis Sie es ändern. Details zeigen
die Endzeit an.

### Fenster

| Situation | Heizkörper | Klimagerät |
| --- | --- | --- |
| Fenster offen, nach Verzögerung (Standard 120 s) | Frostschutz-Wert | Aus |
| Fenster zu, nach Verzögerung (Standard 30 s) | Regeln wie zuvor | Regeln wie zuvor |

Kurzes Öffnen löst also nichts aus. Mehrere Kontakte fassen Sie vorab in einer Gruppe zusammen.

### Warme Tage

| | |
| --- | --- |
| **Zweck** | Nicht heizen, wenn es draußen warm ist |
| **Benötigt** | *Außenfühler* |
| **Verhalten** | Über *Heizung sperren über* (Standard 20 °C) wird Heizen gesperrt, unter *Sperre aufheben unter* (Standard 17 °C) wieder freigegeben. |

Der Wechsel erfolgt erst, wenn der Zustand 30 Minuten besteht. Zwischen beiden Werten bleibt der bisherige Zustand. Die
Betriebsart bleibt auf Heizen, das Thermostat zeigt „Draußen warm“. Kühlen ist davon nicht betroffen.

## 6. Automatiken für Luft und Sommer

### Luft verteilen

| | |
| --- | --- |
| **Zweck** | Warme oder kalte Luft im Raum verteilen |
| **Benötigt** | *Ventilator* (`fan`). *Zweiter Fühler* ist optional. |
| **Auslöser** | Das Thermostat heizt oder kühlt gerade tatsächlich, je nach *Beim Heizen* und *Beim Kühlen* |
| **Verhalten** | Der Ventilator läuft auf *Stufe* (Standard 30 %) und stoppt, sobald die Bedingung entfällt |

Mit einem zweiten Fühler, etwa unter der Decke, läuft er nur, wenn der Unterschied zum Raumfühler mindestens *Einschalten ab
Unterschied* (Standard 1,5 K) beträgt. Er stoppt unter *Ausschalten unter Unterschied* (Standard 0,5 K).

Ein von Hand eingeschalteter Ventilator bleibt unberührt, ThermGenie stoppt nur, was es selbst gestartet hat. Läuft die
Nachtkaskade mit demselben Ventilator, hat sie Vorrang.

### Hitzeschutz

Startet die Kühlung vorausschauend, wenn es heiß ist und jemand auf dem Heimweg ist. Benötigt werden *Gefühlte Temperatur*,
*Entfernung von zu Hause* und *Anwesenheit*. **Alle** Bedingungen müssen erfüllt sein:

- Gefühlte Temperatur über *Starten über* (Standard 23,2 °C), seit mindestens 20 Minuten
- Anwesenheit ist `not_home`, seit mindestens 20 Minuten
- Entfernung unter *Nur unter* (Standard 100 km)
- Thermostat seit mindestens 30 Minuten aus, Fenster zu
- Zuletzt verwendetes Profil ist Kühlen, oder die Sperre für [warme Tage](#warme-tage) ist aktiv
- Uhrzeit zwischen *Frühestens um* und *Spätestens bis* (Standard 08:00 bis 20:00)
- Letzter Start liegt mindestens 12 Stunden zurück

Dann startet das Thermostat im Kühlen mit Profil Eco und meldet dies per Push. Springt das Klimagerät nicht an, erhalten Sie
eine dringende Meldung.

### Entfeuchtungsgrenze

Beendet die Betriebsart Trocknen, bevor die Luft zu trocken wird. Das geschieht, wenn der *Taupunkt* unter *Stoppen unter*
(Standard 9 °C) oder die *Luftfeuchte* unter *Stoppen unter* (Standard 40 %) liegt, jeweils seit 20 Minuten. Das Thermostat
geht aus und meldet dies per Push. Ein Fühler genügt.

### Nachtkaskade

Regelt das Schlafklima, indem ein Ventilator die feine, schnelle Arbeit übernimmt und das Klimagerät nur langsam folgt. So
bleibt es leise und das Klimagerät läuft möglichst wenig.

**Benötigt:** *Schlaf-Fokus*, *Ventilator*, *Anwesenheit*, *Gefühlte Temperatur am Bett* und *Echte Temperatur am Bett*.
Optional sind *Fühler, die aktuell sein müssen* und *Schlafbeginn*.

**Läuft nur, wenn** der Schlaf-Fokus an ist, der **Ventilator bereits läuft** (er wird nicht von der Kaskade eingeschaltet),
jemand zu Hause ist und mindestens ein Fühler in den letzten 90 Minuten gemeldet hat. Fehlt ein Temperaturwert, rechnet sie
mit 23 °C.

**Ablauf alle 5 Minuten:**

1. **Nullpunkt:** *Nullpunkt* (Standard 22,4 °C) plus *Wanderung je Stunde Schlaf* (Standard 0,15 K), bis 7 Stunden. Der Körper
   braucht zum Morgen hin weniger Kühlung.
2. **Bedarf:** Der Abstand der gefühlten Temperatur zum Nullpunkt ergibt 0 bis 100 %. Bei 2 K sind es 100 %.
3. **Grenzen:** Der Ventilator bleibt zwischen *Lüfter mindestens* (15 %) und *Lüfter höchstens* (60 %). Während des Kühlens gilt
   *Lüfter mindestens beim Kühlen* (30 %). In einer Hitzenacht ab *Hitzenacht ab* (24 °C echt) sind *Lüfter höchstens in
   Hitzenächten* (80 %) erlaubt. Unter *Zu kalt unter* (21 °C echt) oder bei kaum Bedarf wird auf das Minimum gedrosselt.
4. **Ventilator:** Ein Befehl geht nur hinaus, wenn er sich um mindestens 8 % ändert.
5. **Klimagerät:** Nur im Kühlen und nur alle 15 Minuten. Reicht der Ventilator nicht, sinkt der Sollwert um 0,5 K. Ist der Bedarf
   unter dem Minimum des Kühlens, steigt er um 0,5 K bis zum Komfort-Wert.

**Untergrenze des Klimageräts:** *ab Schlafbeginn* 20,5 °C, *ab 4 Stunden* 21 °C, *ab 6 Stunden* 22 °C, und nie mehr als 2 K unter
dem Komfort-Wert.

**Am Morgen:** Geht der Schlaf-Fokus nach mehr als 3 Stunden aus, stoppt der Ventilator. Das Thermostat geht zurück auf Komfort
und aus. Eine laufende Heizung bleibt davon unberührt. Das Logbuch zeigt jeden Durchlauf mit allen Werten.

## 7. Schutz und Überwachung

### Heizsperre

Für Räume, die nicht beheizt werden sollen. Sie wird unter *Konfigurieren → Heizsperre* eingeschaltet und ist bewusst keine
Entität, damit sie sich nicht über Dashboards oder Sprachassistenten aufheben lässt.

**Heizen wird abgelehnt**, egal ob von Karte, Automation oder Sprachassistent. Aus und Kühlen bleiben möglich. Die
**Geräte werden immer gehalten** (siehe unten).

**Wird die Heizung dennoch aktiv oder öffnet ein Ventil:**

1. Das Gerät wird sofort geschlossen, es folgt eine dringende Push-Meldung.
2. ThermGenie wartet *Wartezeit auf das Schließen* (Standard 300 s) auf das Ventil.
3. Bleibt es offen, wird der Befehl wiederholt und erneut gewartet.
4. Bleibt es weiter offen, folgt ein kritischer Alarm, der auch Ruhemodi durchbricht, und eine Sprachausgabe.

**Frost:** Fällt der Raum auf *Frostschutz beginnt bei* (Standard 6 °C), ist die Sperre ausgesetzt und es wird bis *Frostschutz
endet bei* (Standard 8 °C) geheizt. Danach gilt die Sperre wieder. Sie erhalten eine Meldung, mit Hinweis, falls das Fenster
offen steht. Der Binärsensor *Frostschutz aktiv* zeigt diesen Zustand.

### Gerät halten

Mit *Gerät gegen Verstellen halten* setzt ThermGenie jede Änderung am Gerät sofort zurück und vermerkt dies im Logbuch. Geräte
ohne Aus-Modus werden über ihren niedrigsten Sollwert geschlossen.

Direkt nach einem eigenen Befehl wartet ThermGenie 30 Sekunden, weil Funkgeräte kurz noch den alten Wert melden können.
**Grenze:** ThermGenie erkennt nur, was das Gerät meldet. Manche Funkthermostate melden Änderungen am Drehrad nicht zuverlässig.
Eine hinterlegte Ventilstellung deckt diese Fälle ab.

### Ventilüberwachung

Hinterlegen Sie unter *Gerät halten und Ventile* für jeden Heizkörper einen Sensor mit der Ventilöffnung in Prozent.

Ein Heizkörper **soll geschlossen sein**, wenn er aus ist oder sein Sollwert mindestens 1 K unter seiner eigenen Messung liegt.
Steht das Ventil dann mindestens auf *Ventil gilt als offen ab* (Standard 5 %), und das *Warnen nach* (Standard 30 Minuten) lang,
gibt es eine dringende Meldung. Der Binärsensor *Ventil schließt nicht* wird aktiv. Schließt das Ventil, wird er wieder inaktiv
und das Logbuch vermerkt dies.

Thermostatventile regeln selbst und nicht immer nach dem Sollwert. Bekommen Sie Warnungen, obwohl alles in Ordnung ist, erhöhen
Sie die Grenze oder die Wartezeit. In einem Raum mit Heizsperre löst ein offenes Ventil die Sperre aus.

### Ausfälle

| Ausfall | Verhalten |
| --- | --- |
| **Raumfühler** meldet nichts mehr | Die Geräte erhalten den Sollwert und regeln selbst. Binärsensor *Raumfühler ausgefallen*. |
| **Ein Gerät** ist nicht erreichbar | Die übrigen laufen weiter. Kommt es zurück, wird es sofort angeglichen. |
| **Befehl** schlägt fehl | Er wird im nächsten Regeltakt wiederholt. |
| **Home Assistant** startet neu | Betriebsart, Profile, I-Anteil und abgeschaltete Automatiken bleiben erhalten. Eine laufende Messphase der Optimierung geht verloren. |

## 8. Entitäten und Dienste

Geben Sie an Sprachassistenten und Matter-Brücken nur die `climate`-Entität frei. Welche Betriebsarten dort erscheinen, bestimmen
die Brücke und der Assistent.

### Sensoren

| Entität | Inhalt | Voraussetzung |
| --- | --- | --- |
| Humidex, Taupunkt, Gefühlte Temperatur | Rechenwerte | Feuchtefühler |

### Diagnose

| Entität | Inhalt | Voraussetzung |
| --- | --- | --- |
| Gesperrt durch | Keine, Fenster oder Warme Tage | |
| Stellwert *Gerät* | Letzter Befehl; Attribute: Versatz, Bremse, I-Speicher | Je Gerät |
| Raumfühler ausgefallen | Ein/Aus | |
| Frostschutz aktiv | Ein/Aus | Heizsperre |
| Ventil schließt nicht | Ein/Aus | Ventilsensor |
| Nächstes Aufheizen | Zeitpunkt | Wecker oder Schlaf |
| Überschwingen, Bremsfaktor | Letzte Heizphase, gelernter Faktor | Lernende Bremse |
| Optimierung, Aktuelles kp, Aktuelles ki | Siehe [Regelung optimieren](#regelung-optimieren) | Heizgeräte |

### Dienste

| Dienst | Wirkung |
| --- | --- |
| `climate.set_hvac_mode`, `set_temperature`, `set_preset_mode`, `turn_on`, `turn_off` | Standarddienste, bei Heizsperre wird Heizen abgelehnt |
| `thermgenie.set_routine` | Schaltet eine Automatik: `sleep`, `wake`, `way_home`, `guard`, `cascade`, `dry`, `air` |
| `thermgenie.reset_learning` | Vergisst Bremsfaktoren und Optimierung |

```yaml
action: thermgenie.set_routine
target:
  entity_id: climate.wohnzimmer
data:
  routine: way_home
  enabled: false
```

## 9. Meldungen

Hinterlegen Sie einen *Push-Dienst* (`notify.…`). Für Sprachausgabe kommen *Sprachausgabe-Dienst* und *Lautsprecher* hinzu.
Gesprochen wird nur, wenn jemand zu Hause ist und *Keine Sprachausgabe, wenn an* nicht aktiv ist.

| Anlass | Push | Logbuch | Sprache |
| --- | --- | --- | --- |
| Hitzeschutz gestartet | Normal | Ja | |
| Hitzeschutz fehlgeschlagen | Dringend | Ja | |
| Entfeuchten beendet | Normal | Ja | |
| Ventil schließt nicht | Dringend | Ja | |
| Heizsperre hat abgeschaltet | Dringend | Ja | |
| Frostschutz beginnt | Dringend | Ja | |
| Ventil klemmt bei Heizsperre | Kritisch | Ja | Ja |
| Gerät zurückgesetzt, Nachtkaskade, Optimierung | | Ja | |

Dringende und kritische Stufen sind Angaben im Format der iOS-Companion-App. Andere Empfänger ignorieren sie.

## 10. Fehlersuche

| Beobachtung | Mögliche Ursache |
| --- | --- |
| Raum erreicht das Ziel nicht | Korrektur am Limit (*Größte Sollwert-Verschiebung*), Stellwert unter Diagnose prüfen. Gerät am Maximum oder keine Heizleistung. |
| Raum schießt über das Ziel | Bremse ist standardmäßig aus: *D-Anteil* erhöhen, etwa auf 0,5, und lernen lassen |
| Stellwert steht auf dem Minimum des Geräts | Der Raum liegt mindestens 0,5 K über dem Sollwert. Das ist Absicht. |
| Regelung reagiert träge | Regeltakt und kleinster Schritt prüfen. Änderungen unter 0,5 K gehen nicht hinaus. |
| Heizt nicht trotz Betriebsart Heizen | *Gesperrt durch* unter Diagnose prüfen. Fenster offen oder warme Tage? Heizquelle richtig? |
| Klimaanlage heizt nicht | *Heizen mit* prüfen. Bietet das Gerät den Modus `heat` an und ist es erreichbar? |
| Raumtemperatur auf der Karte stimmt nicht mit dem Fühler überein | *Regeln nach* steht auf Humidex oder Gefühlte Temperatur. |
| Abwesenheit senkt nicht ab | *Schlafen* ist nicht hinterlegt, oder die Automatik ist aus. |
| Aufheizen zum Wecken passiert nicht | Thermostat ist aus oder steht auf Kühlen. Wecker liegt in der Vergangenheit. |
| Nachtkaskade tut nichts | Der Ventilator muss laufen. Fokus an, jemand zu Hause, Fühler aktuell? Logbuch prüfen. |
| Hitzeschutz startet nicht | Alle Bedingungen müssen gleichzeitig zutreffen, siehe [Hitzeschutz](#hitzeschutz). |
| Warnung „Ventil schließt nicht“ ohne echten Fehler | Das Ventil regelt selbst. Grenze oder Wartezeit erhöhen. |
| Optimierung zeigt lange nur „Misst“ | Es braucht fünf saubere Phasen ab 0,5 K Abstand. Diagnose-Attribut *phases* prüfen. |
| Einstellung fehlt auf der Geräteseite | Zunächst deaktiviert: In der Entitätenliste aktivieren. Bei Heizsperre sind Heizwerte ausgeblendet. |
| Karte zeigt alten Stand | Browser-Cache leeren oder die App neu laden. |
