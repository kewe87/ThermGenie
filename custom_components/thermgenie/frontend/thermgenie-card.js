// ThermGenie: a dashboard card and the popup that replaces the standard climate dialog.

const TEXT = {
  en: {
    off: "Off", heat: "Heat", cool: "Cool", dry: "Dry", fan_only: "Fan",
    heating: "Heating", cooling: "Cooling", drying: "Drying", fan: "Fan running", idle: "Holding",
    frost: "Frost", eco: "Eco", comfort: "Comfort", boost: "Boost",
    locked: "Off · heating lock", frostActive: "Frost protection up to {off}",
    window: "Window open",
    outdoor: "Warm outside",
    stale: "Room sensor silent",
    deviceDown: "not reachable", room: "Room", target: "Target", now: "now",
    humidity: "Humidity", humidex: "Humidex", dewPoint: "Dew point", felt: "Comfort",
    modes: "Mode", presets: "Presets", climate: "Indoor climate", routines: "Automation", devices: "Devices", history: "Last 24 hours",
    asleep: "Night setback active", away: "Away setback active", awake: "Sleep and presence", wakeAt: "Wake-up heating {time}", wakeFixed: "Heating up {time}, no alarm set", wakeNone: "Wake-up heating: no alarm set",
    airName: "Move the air", airOn: "Moving the air", allSettings: "Device and settings",
    offset: "Offset",
    air_percent: "Fan speed", air_difference_on: "Start at a difference of", air_difference_off: "Stop below a difference of",
    wayHomeOn: "On the way home: preheating", wayHomeOff: "Way home", boostUntil: "Boost until {time}",
    offset: "Offset", setpoint: "Setpoint", close: "Close",
    lower: "Lower target", raise: "Raise target", noHistory: "No history yet", heatingBand: "Running",
    failed: "Command failed", pickEntity: "Pick a ThermGenie thermostat", notFound: "not found",
    way_homeName: "Way home", sleepName: "Sleep and presence", wakeName: "Wake-up heating", guardName: "Heat guard", cascadeName: "Night cascade", dryName: "Drying limit",
    description: "Thermostat with custom popup", entity: "Thermostat", name: "Name", control: "Control", details: "Details",
  },
  de: {
    off: "Aus", heat: "Heizen", cool: "Kühlen", dry: "Trocknen", fan_only: "Lüfter",
    heating: "Heizt", cooling: "Kühlt", drying: "Trocknet", fan: "Lüfter läuft", idle: "Hält",
    frost: "Frost", eco: "Eco", comfort: "Komfort", boost: "Boost",
    locked: "Aus · Heizsperre", frostActive: "Frostschutz bis {off}",
    window: "Fenster offen",
    outdoor: "Draußen warm",
    stale: "Raumfühler meldet nichts",
    deviceDown: "nicht erreichbar", room: "Raum", target: "Soll", now: "jetzt",
    humidity: "Feuchte", humidex: "Humidex", dewPoint: "Taupunkt", felt: "Gefühlt",
    modes: "Betriebsart", presets: "Profile", climate: "Raumklima", routines: "Automatik", devices: "Geräte", history: "Letzte 24 Stunden",
    asleep: "Nachtabsenkung aktiv", away: "Absenkung: niemand zuhause", awake: "Schlaf und Anwesenheit", wakeAt: "Aufheizen zum Wecken {time}", wakeFixed: "Aufheizen {time}, kein Wecker gestellt", wakeNone: "Aufheizen zum Wecken: kein Wecker gestellt",
    airName: "Luft verteilen", airOn: "Luft wird verteilt", allSettings: "Gerät und Einstellungen",
    offset: "Versatz",
    air_percent: "Ventilatorstufe", air_difference_on: "Einschalten ab Unterschied", air_difference_off: "Ausschalten unter Unterschied",
    wayHomeOn: "Auf dem Heimweg: heizt vor", wayHomeOff: "Heimweg", boostUntil: "Boost bis {time}",
    offset: "Versatz", setpoint: "Sollwert", close: "Schließen",
    lower: "Soll senken", raise: "Soll erhöhen", noHistory: "Noch kein Verlauf", heatingBand: "Läuft",
    failed: "Befehl fehlgeschlagen", pickEntity: "ThermGenie-Thermostat wählen", notFound: "nicht gefunden",
    way_homeName: "Heimweg", sleepName: "Schlaf und Anwesenheit", wakeName: "Aufheizen zum Wecken", guardName: "Hitzeschutz", cascadeName: "Nachtkaskade", dryName: "Entfeuchtungs-Grenze",
    description: "Thermostat mit eigenem Popup", entity: "Thermostat", name: "Name", control: "Bedienung", details: "Details",
  },
};

const MODE_ICONS = { off: "mdi:power", heat: "mdi:fire", cool: "mdi:snowflake", dry: "mdi:water-percent", fan_only: "mdi:fan" };
const PRESET_ICONS = { frost: "mdi:snowflake-thermometer", eco: "mdi:leaf", comfort: "mdi:sofa", boost: "mdi:rocket-launch" };
const COOL = "#2a78d6";
const WARM = "#d9622b";
const NEUTRAL = "#a8a59c";
const NEUTRAL_AT = 20; // degrees where the dial turns from cool to warm
const COMMAND_DELAY_MS = 700;
const PENDING_MS = 8000;
const POLL_MS = 500;
const HISTORY_HOURS = 24;

const root = () => document.querySelector("home-assistant");
const liveHass = () => root()?.hass;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const text = (hass, key, vars = {}) => {
  const table = TEXT[(hass.locale?.language || hass.language || "en").slice(0, 2)] || TEXT.en;
  return (table[key] ?? TEXT.en[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => vars[name]);
};
const number = (hass, value, digits = 1) =>
  value === null || value === undefined ? "–" : Number(value).toLocaleString(hass.locale?.language || hass.language, { minimumFractionDigits: digits, maximumFractionDigits: digits });
const degrees = (hass, value) => `${number(hass, value)}°`;
const clock = (hass, value) => new Date(value).toLocaleTimeString(hass.locale?.language || hass.language, { hour: "2-digit", minute: "2-digit" });
const icon = (name) => `<ha-icon icon="${name}"></ha-icon>`;
const haptic = () => window.dispatchEvent(new CustomEvent("haptic", { detail: "selection" }));
const toast = (message) => root()?.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));

// Setpoints the user just picked: shown at once, sent after a short pause, shared by card and popup

const pending = new Map();

function shownTarget(state) {
  const wish = pending.get(state.entity_id);
  if (!wish) return state.attributes.temperature;
  if (!wish.timer && (state.attributes.temperature === wish.value || Date.now() > wish.until)) {
    pending.delete(state.entity_id);
    return state.attributes.temperature;
  }
  return wish.value;
}

function setTarget(entityId, value, delay = COMMAND_DELAY_MS) {
  clearTimeout(pending.get(entityId)?.timer);
  const wish = { value, until: Date.now() + PENDING_MS, timer: null };
  wish.timer = setTimeout(() => {
    wish.timer = null;
    wish.until = Date.now() + PENDING_MS;
    call("set_temperature", { entity_id: entityId, temperature: value }, () => pending.delete(entityId));
  }, delay);
  pending.set(entityId, wish);
}

function stepTarget(state, direction) {
  const { target_temp_step: step = 0.5, min_temp: low, max_temp: high } = state.attributes;
  const value = Math.min(high, Math.max(low, shownTarget(state) + direction * step));
  haptic();
  setTarget(state.entity_id, value);
}

function call(service, data, onError, domain = "climate") {
  const hass = liveHass();
  hass.callService(domain, service, data).catch((err) => {
    onError?.();
    toast(`${text(hass, "failed")}: ${err.message || err.code || ""}`);
  });
}

// What a thermostat is doing, in one place for card and popup

function describe(hass, state) {
  const a = state.attributes;
  if (a.frost_active) return { key: "frost", icon: "mdi:snowflake-alert", label: text(hass, "frostActive", { off: degrees(hass, a.lock_frost_off) }), tone: "heat" };
  if (a.heat_lock && state.state === "off") return { key: "lock", icon: "mdi:lock", label: text(hass, "locked"), tone: "off" };
  if (a.blocked_by === "window") return { key: "window", icon: "mdi:window-open-variant", label: text(hass, "window"), tone: "warn" };
  if (a.blocked_by === "outdoor") return { key: "outdoor", icon: "mdi:weather-sunny", label: text(hass, "outdoor"), tone: "idle" };
  if (state.state === "off") return { key: "off", icon: "mdi:power", label: text(hass, "off"), tone: "off" };
  const action = a.hvac_action || "idle";
  const tone = { heating: "heat", cooling: "cool", drying: "cool", fan: "cool" }[action] || "idle";
  const name = { heating: "mdi:fire", cooling: "mdi:snowflake", drying: "mdi:water-percent", fan: "mdi:fan" }[action] || "mdi:thermostat";
  return { key: action, icon: name, label: text(hass, action in TEXT.en ? action : "idle"), tone };
}

const canSetTarget = (state) => ["heat", "cool"].includes(state.state);

// Keep the keyboard focus when a part of the page is drawn again

function draw(host, container, html) {
  if (container.dataset.html === html) return;
  const focused = host.shadowRoot.activeElement?.dataset?.key;
  container.innerHTML = html;
  container.dataset.html = html;
  if (focused) container.querySelector(`[data-key="${focused}"]`)?.focus();
}

const SHARED_CSS = `
  * { box-sizing: border-box; }
  ha-icon { --mdc-icon-size: 20px; display: inline-flex; }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; -webkit-tap-highlight-color: transparent; }
  button:focus-visible, [tabindex]:focus-visible { outline: 2px solid var(--primary-color, ${COOL}); outline-offset: 2px; }
  button:disabled { cursor: default; opacity: .4; }
  .tone-heat { --tone: var(--state-climate-heat-color, ${WARM}); }
  .tone-cool { --tone: var(--state-climate-cool-color, ${COOL}); }
  .tone-warn { --tone: var(--warning-color, #e0a000); }
  .tone-idle { --tone: var(--primary-text-color); }
  .tone-off { --tone: var(--secondary-text-color); }
`;

// The card

class ThermGenieCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.keys(hass.entities || {}).find((id) => hass.entities[id].platform === "thermgenie" && id.startsWith("climate."));
    return { entity: entity || "" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "climate", integration: "thermgenie" } } },
        { name: "name", selector: { text: {} } },
      ],
      computeLabel: (schema) => text(liveHass(), schema.name),
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error(TEXT.en.pickEntity);
    this.config = config;
  }

  getCardSize() {
    return 1;
  }

  getGridOptions() {
    return { columns: 12, rows: 1, min_columns: 6, min_rows: 1 };
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  connectedCallback() {
    this.render();
  }

  render() {
    if (!this._hass || !this.config) return;
    if (!this.shadowRoot) this.build();
    const hass = this._hass;
    const state = hass.states[this.config.entity];
    if (!state) {
      draw(this, this.$body, `<div class="missing">${esc(this.config.entity)} ${text(hass, "notFound")}</div>`);
      return;
    }
    const a = state.attributes;
    const info = describe(hass, state);
    const down = Object.values(a.devices || {}).filter((d) => !d.available).length;
    const name = this.config.name || a.friendly_name;
    const controls = canSetTarget(state) && state.state !== "off"
      ? `<div class="stepper">
           <button data-key="down" data-step="-1" aria-label="${text(hass, "lower")}">${icon("mdi:minus")}</button>
           <span class="value"><small>${text(hass, "target")}</small>${degrees(hass, shownTarget(state))}</span>
           <button data-key="up" data-step="1" aria-label="${text(hass, "raise")}">${icon("mdi:plus")}</button>
         </div>`
      : "";
    draw(this, this.$body, `
      <button class="main tone-${info.tone}" data-key="open" aria-haspopup="dialog">
        <span class="badge ${info.tone === "heat" || info.tone === "cool" ? "running" : ""}">${icon(info.icon)}</span>
        <span class="names">
          <span class="name">${esc(name)}${down ? ` <ha-icon class="alert" icon="mdi:alert-circle"></ha-icon>` : ""}</span>
          <span class="status">${esc(info.label)}</span>
        </span>
        <span class="room"><small>${text(hass, "room")}</small>${degrees(hass, a.room_temperature ?? a.current_temperature)}</span>
      </button>
      ${controls}`);
  }

  build() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ${SHARED_CSS}
        ha-card { height: 100%; overflow: hidden; }
        #body { display: flex; align-items: center; gap: 4px; height: 100%; min-height: 56px; padding: 0 8px 0 0; }
        .main { flex: 1; min-width: 0; height: 100%; display: flex; align-items: center; gap: 10px; padding: 8px 4px 8px 10px; text-align: left; }
        .badge { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; color: var(--tone); background: color-mix(in srgb, var(--tone) 14%, transparent); }
        .badge.running { color: #fff; background: var(--tone); }
        .names { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.25; }
        .name, .status { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .name { font-weight: 500; font-size: 14px; color: var(--primary-text-color); }
        .name .alert { --mdc-icon-size: 14px; color: var(--error-color, #d33); vertical-align: -2px; }
        .status { font-size: 12px; color: var(--secondary-text-color); }
        .room, .stepper .value { display: flex; flex-direction: column; align-items: center; line-height: 1.15; font-weight: 500; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
        .room { flex: none; font-size: 16px; }
        small { font-size: 10px; font-weight: 400; color: var(--secondary-text-color); }
        .stepper { flex: none; display: flex; align-items: center; height: 36px; border-radius: 18px; background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); }
        .stepper button { width: 34px; height: 36px; display: grid; place-items: center; border-radius: 18px; color: var(--primary-text-color); }
        .stepper ha-icon { --mdc-icon-size: 16px; }
        .stepper .value { min-width: 38px; font-size: 13px; }
        .missing { padding: 16px; color: var(--error-color, #d33); }
      </style>
      <ha-card><div id="body"></div></ha-card>`;
    this.$body = this.shadowRoot.getElementById("body");
    this.$body.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      const state = this._hass.states[this.config.entity];
      if (button.dataset.step) {
        stepTarget(state, Number(button.dataset.step));
        this.render();
      } else {
        ThermGeniePopup.open(this.config.entity);
      }
    });
  }
}

// The dial of the popup

const DIAL = { size: 280, center: 140, radius: 116, start: 135, sweep: 270, segments: 54 };

function mix(from, to, part) {
  const channels = [1, 3, 5].map((i) => Math.round(parseInt(from.slice(i, i + 2), 16) * (1 - part) + parseInt(to.slice(i, i + 2), 16) * part));
  return `rgb(${channels.join(",")})`;
}

function scaleColor(value) {
  if (value <= NEUTRAL_AT) return mix(COOL, NEUTRAL, Math.max(0, (value - 8) / (NEUTRAL_AT - 8)));
  return mix(NEUTRAL, WARM, Math.min(1, (value - NEUTRAL_AT) / 6));
}

function dialPoint(degree, radius = DIAL.radius) {
  const angle = (degree * Math.PI) / 180;
  return [DIAL.center + radius * Math.cos(angle), DIAL.center + radius * Math.sin(angle)];
}

function dialSvg(low, high) {
  const gap = 1.1;
  const part = DIAL.sweep / DIAL.segments;
  let segments = "";
  for (let i = 0; i < DIAL.segments; i++) {
    const [x1, y1] = dialPoint(DIAL.start + i * part + gap / 2);
    const [x2, y2] = dialPoint(DIAL.start + (i + 1) * part - gap / 2);
    const value = low + ((i + 0.5) / DIAL.segments) * (high - low);
    segments += `<path class="seg" data-value="${value}" stroke="${scaleColor(value)}" d="M${x1.toFixed(2)} ${y1.toFixed(2)}A${DIAL.radius} ${DIAL.radius} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}"/>`;
  }
  return `<svg viewBox="0 0 ${DIAL.size} ${DIAL.size}" aria-hidden="true">${segments}
    <circle id="now" r="4"/><circle id="handle" r="13"/></svg>`;
}

// The popup

class ThermGeniePopup extends HTMLElement {
  static open(entityId) {
    if (ThermGeniePopup.current) ThermGeniePopup.current.close();
    const popup = document.createElement("thermgenie-popup");
    popup.entityId = entityId;
    popup.returnFocus = document.activeElement;
    ThermGeniePopup.current = popup;
    document.body.appendChild(popup);
  }

  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.build();
    this.update();
    this.timer = setInterval(() => this.update(), POLL_MS);
    this.onKey = (event) => this.key(event);
    document.addEventListener("keydown", this.onKey);
    this.shadowRoot.getElementById("close").focus();
  }

  disconnectedCallback() {
    clearInterval(this.timer);
    document.removeEventListener("keydown", this.onKey);
  }

  close() {
    if (ThermGeniePopup.current === this) ThermGeniePopup.current = null;
    this.remove();
    this.returnFocus?.focus?.();
  }

  key(event) {
    if (event.key === "Escape") {
      event.stopPropagation();
      this.close();
    } else if (event.key === "Tab") {
      const items = [...this.shadowRoot.querySelectorAll("button:not(:disabled), [tabindex='0']")].filter((item) => item.offsetParent);
      const at = items.indexOf(this.shadowRoot.activeElement);
      if (event.shiftKey && at <= 0) {
        event.preventDefault();
        items.at(-1).focus();
      } else if (!event.shiftKey && at === items.length - 1) {
        event.preventDefault();
        items[0].focus();
      }
    }
  }

  get state() {
    return liveHass()?.states[this.entityId];
  }

  build() {
    const a = this.state.attributes;
    this.low = a.min_temp;
    this.high = a.max_temp;
    this.shadowRoot.innerHTML = `
      <style>${SHARED_CSS}${POPUP_CSS}</style>
      <div id="backdrop"></div>
      <div id="sheet" role="dialog" aria-modal="true" aria-labelledby="title">
        <header>
          <div class="heading"><h2 id="title"></h2><div id="status"></div></div>
          <button id="close" class="round">${icon("mdi:close")}</button>
        </header>
        <div class="tabs" role="tablist">
          <button id="tab-control" role="tab" data-tab="control"></button>
          <button id="tab-details" role="tab" data-tab="details"></button>
        </div>
        <div id="page-control" role="tabpanel">
          <div id="notice"></div>
          <div id="dial">
            ${dialSvg(this.low, this.high)}
            <div id="center"><span id="label"></span><span id="big"></span><span id="small"></span></div>
            <button id="down" class="round step">${icon("mdi:minus")}</button>
            <button id="up" class="round step">${icon("mdi:plus")}</button>
          </div>
          <div id="sections"></div>
        </div>
        <div id="page-details" role="tabpanel" hidden>
          <div id="details"></div>
          <section class="s-chart"><h3 id="chart-title"></h3><div id="chart"></div></section>
          <div id="footer"></div>
        </div>
      </div>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    this.$ = { title: $("title"), status: $("status"), notice: $("notice"), label: $("label"), big: $("big"), small: $("small"), sections: $("sections"), details: $("details"), footer: $("footer"), chart: $("chart"), dial: $("dial"), sheet: $("sheet") };
    this.$.svg = this.$.dial.querySelector("svg");
    this.$.segments = [...this.$.svg.querySelectorAll(".seg")];
    this.$.handle = $("handle");
    this.$.now = $("now");
    $("backdrop").addEventListener("click", () => this.close());
    $("close").addEventListener("click", () => this.close());
    $("down").addEventListener("click", () => this.step(-1));
    $("up").addEventListener("click", () => this.step(1));
    this.$.sheet.addEventListener("click", (event) => this.click(event));
    this.bindDial();
  }

  step(direction) {
    stepTarget(this.state, direction);
    this.update();
  }

  click(event) {
    const button = event.target.closest("button");
    if (!button) return;
    const { mode, preset, go, tab, routine, enable } = button.dataset;
    if (routine) {
      haptic();
      call("set_routine", { entity_id: this.entityId, routine, enabled: enable === "true" }, null, "thermgenie");
    } else if (tab) {
      this.tab = tab;
      this.update();
      // The chart needs its width and is only worth loading when somebody looks at it
      if (tab === "details" && !this.historyLoaded) {
        this.historyLoaded = true;
        this.loadHistory();
      }
    } else if (mode) {
      haptic();
      call("set_hvac_mode", { entity_id: this.entityId, hvac_mode: mode });
    } else if (preset) {
      haptic();
      pending.delete(this.entityId);
      call("set_preset_mode", { entity_id: this.entityId, preset_mode: preset });
    } else if (go === "settings") {
      this.close();
      const device = liveHass()?.entities?.[this.entityId]?.device_id;
      history.pushState(null, "", device ? `/config/devices/device/${device}` : "/config/integrations/integration/thermgenie");
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }
  }

  // Dragging the dial

  bindDial() {
    const dial = this.$.svg;
    const valueAt = (event) => {
      const box = dial.getBoundingClientRect();
      const x = ((event.clientX - box.left) / box.width) * DIAL.size - DIAL.center;
      const y = ((event.clientY - box.top) / box.height) * DIAL.size - DIAL.center;
      if (Math.hypot(x, y) < DIAL.radius * 0.62) return null;
      let along = ((Math.atan2(y, x) * 180) / Math.PI - DIAL.start + 360) % 360;
      if (along > DIAL.sweep) along = along > (DIAL.sweep + 360) / 2 ? 0 : DIAL.sweep;
      const step = this.state.attributes.target_temp_step || 0.5;
      return Math.round((this.low + (along / DIAL.sweep) * (this.high - this.low)) / step) * step;
    };
    dial.addEventListener("pointerdown", (event) => {
      if (!canSetTarget(this.state)) return;
      const value = valueAt(event);
      if (value === null) return;
      dial.setPointerCapture(event.pointerId);
      this.dragging = value;
      this.update();
    });
    dial.addEventListener("pointermove", (event) => {
      if (this.dragging === undefined) return;
      const value = valueAt(event);
      // A jump across the gap at the bottom is a slip, not a wish for the other end of the scale
      if (value === null || value === this.dragging || Math.abs(value - this.dragging) > (this.high - this.low) / 2) return;
      this.dragging = value;
      haptic();
      this.update();
    });
    const release = () => {
      if (this.dragging === undefined) return;
      setTarget(this.entityId, this.dragging, 0);
      this.dragging = undefined;
      this.update();
    };
    dial.addEventListener("pointerup", release);
    dial.addEventListener("pointercancel", release);
    this.$.dial.setAttribute("tabindex", "0");
    this.$.dial.setAttribute("role", "slider");
    this.$.dial.addEventListener("keydown", (event) => {
      if (event.target !== this.$.dial || !canSetTarget(this.state)) return;
      const direction = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1 }[event.key];
      if (!direction) return;
      event.preventDefault();
      this.step(direction);
    });
  }

  // Drawing

  update() {
    const hass = liveHass();
    const state = this.state;
    if (!hass || !state) return;
    const a = state.attributes;
    const info = describe(hass, state);
    const editable = canSetTarget(state);
    const target = this.dragging ?? shownTarget(state);
    const room = a.room_temperature ?? a.current_temperature ?? null;
    this.$.title.textContent = a.friendly_name;
    this.$.sheet.className = hass.themes?.darkMode ? "dark" : "";
    draw(this, this.$.status, `<span class="pill tone-${info.tone}">${icon(info.icon)}${esc(info.label)}</span>`);
    this.shadowRoot.getElementById("close").setAttribute("aria-label", text(hass, "close"));

    draw(this, this.$.notice, a.sensor_stale ? `<p class="tone-warn">${text(hass, "stale")}</p>` : "");

    // Off means off: only the measured room temperature is left
    const showTarget = editable;
    this.$.label.textContent = showTarget ? text(hass, "target") : text(hass, "room");
    this.$.big.textContent = degrees(hass, showTarget ? target : room);
    this.$.small.textContent = showTarget && room !== null ? `${text(hass, "room")} ${degrees(hass, room)}` : "";
    const running = showTarget && room !== null;
    const from = Math.min(room, target);
    const to = Math.max(room, target);
    for (const segment of this.$.segments) {
      const value = Number(segment.dataset.value);
      segment.style.opacity = running && value >= from && value <= to ? 1 : 0.5;
    }
    const at = (value) => DIAL.start + ((value - this.low) / (this.high - this.low)) * DIAL.sweep;
    const [hx, hy] = dialPoint(at(target));
    this.$.handle.setAttribute("cx", hx);
    this.$.handle.setAttribute("cy", hy);
    this.$.handle.setAttribute("fill", scaleColor(target));
    this.$.handle.style.display = showTarget ? "" : "none";
    if (room !== null && room >= this.low && room <= this.high) {
      const [nx, ny] = dialPoint(at(room));
      this.$.now.setAttribute("cx", nx);
      this.$.now.setAttribute("cy", ny);
      this.$.now.style.display = "";
    } else {
      this.$.now.style.display = "none";
    }
    this.$.dial.classList.toggle("readonly", !editable);
    this.$.dial.setAttribute("aria-label", text(hass, "target"));
    this.$.dial.setAttribute("aria-valuemin", this.low);
    this.$.dial.setAttribute("aria-valuemax", this.high);
    this.$.dial.setAttribute("aria-valuenow", target);
    this.$.dial.setAttribute("tabindex", editable ? "0" : "-1");
    const down = this.shadowRoot.getElementById("down");
    const up = this.shadowRoot.getElementById("up");
    down.hidden = up.hidden = !editable;
    down.setAttribute("aria-label", text(hass, "lower"));
    up.setAttribute("aria-label", text(hass, "raise"));

    const tab = this.tab || "control";
    for (const name of ["control", "details"]) {
      const button = this.shadowRoot.getElementById(`tab-${name}`);
      button.textContent = text(hass, name);
      button.setAttribute("aria-selected", tab === name);
      this.shadowRoot.getElementById(`page-${name}`).hidden = tab !== name;
    }
    draw(this, this.$.sections, [this.routines(hass, state, true), this.modes(hass, state), this.presets(hass, state)].join(""));
    draw(this, this.$.details, [this.routines(hass, state), this.climate(hass, a), this.devices(hass, a)].join(""));
    this.shadowRoot.getElementById("chart-title").textContent = text(hass, "history");
    draw(this, this.$.footer, `
      ${hass.user?.is_admin ? `<button class="link" data-key="settings" data-go="settings">${icon("mdi:cog-outline")}${text(hass, "allSettings")}</button>` : ""}`);
  }

  modes(hass, state) {
    const locked = state.attributes.heat_lock;
    const modes = [...new Set(["off", ...(state.attributes.hvac_modes || [])])];
    const buttons = modes.map((mode) => {
      const blocked = locked && mode === "heat";
      return `<button class="choice ${state.state === mode ? "active" : ""} tone-${mode === "heat" ? "heat" : mode === "off" ? "idle" : "cool"}" data-key="mode-${mode}" data-mode="${mode}" aria-pressed="${state.state === mode}" ${blocked ? "disabled" : ""}>
        ${icon(blocked ? "mdi:lock" : MODE_ICONS[mode] || "mdi:thermostat")}<span>${text(hass, mode)}</span></button>`;
    });
    return `<section><h3>${text(hass, "modes")}</h3><div class="choices">${buttons.join("")}</div></section>`;
  }

  presets(hass, state) {
    const a = state.attributes;
    if (!canSetTarget(state)) return "";
    const buttons = (a.preset_modes || []).filter((p) => p !== "none").map((preset) => {
      const value = a.presets?.[`${a.profile}_${preset}`];
      return `<button class="choice ${a.preset_mode === preset ? "active" : ""} tone-${a.profile}" data-key="preset-${preset}" data-preset="${preset}" aria-pressed="${a.preset_mode === preset}">
        ${icon(PRESET_ICONS[preset] || "mdi:thermostat")}<span>${text(hass, preset)}</span><small>${degrees(hass, value)}</small></button>`;
    });
    return `<section><h3>${text(hass, "presets")}</h3><div class="choices">${buttons.join("")}</div></section>`;
  }

  routines(hass, state, activeOnly = false) {
    const a = state.attributes;
    const r = a.routines || {};
    const off = a.routines_off || [];
    const winter = a.profile === "heat";
    const rows = [];
    const add = (key, name, label, active) => {
      if (!off.includes(key)) rows.push({ key, name, label: label(), active });
      else rows.push({ key, name, label: text(hass, `${key}Name`), off: true });
    };
    if (r.way_home !== undefined && winter) add("way_home", "mdi:home-import-outline", () => text(hass, r.way_home ? "wayHomeOn" : "wayHomeOff"), r.way_home);
    if (r.sleep && winter) add("sleep", r.sleep === "asleep" ? "mdi:weather-night" : r.sleep === "away" ? "mdi:home-export-outline" : "mdi:bed-outline", () => text(hass, r.sleep), r.sleep !== "awake");
    if ("wake_at" in r && winter) add("wake", "mdi:alarm", () => (r.wake_at ? text(hass, r.wake_alarm === false ? "wakeFixed" : "wakeAt", { time: clock(hass, r.wake_at) }) : text(hass, "wakeNone")), false);
    if ("air" in r) add("air", "mdi:fan", () => text(hass, r.air ? "airOn" : "airName"), r.air);
    if (r.guard && !winter) add("guard", "mdi:shield-sun-outline", () => text(hass, "guardName"), false);
    if (r.cascade && !winter) add("cascade", "mdi:weather-night", () => text(hass, "cascadeName"), false);
    if (r.dry && !winter) add("dry", "mdi:water-percent", () => text(hass, "dryName"), false);
    const boost = r.boost_until ? `<span class="chip on">${icon("mdi:rocket-launch")}${esc(text(hass, "boostUntil", { time: clock(hass, r.boost_until) }))}</span>` : "";
    if (activeOnly) {
      const active = rows.filter((row) => row.active).map((row) => `<span class="chip on">${icon(row.name)}${esc(row.label)}</span>`);
      return boost || active.length ? `<section><div class="chips">${boost}${active.join("")}</div></section>` : "";
    }
    if (!rows.length && !boost) return "";
    const chips = rows.map((row) => `<button class="chip ${row.active ? "on" : ""} ${row.off ? "disabled" : ""}" data-key="routine-${row.key}" data-routine="${row.key}" data-enable="${!!row.off}" aria-pressed="${!row.off}">${icon(row.off ? "mdi:close-circle-outline" : row.name)}${esc(row.label)}</button>`);
    return `<section class="s-routines"><h3>${text(hass, "routines")}</h3><div class="chips">${boost}${chips.join("")}</div></section>`;
  }

  climate(hass, a) {
    const values = [
      ["humidity", a.current_humidity, (v) => `${number(hass, v, 0)} %`],
      // Of the two felt values only the one the room is regulated on says something here
      ["felt", a.reference === "comfort" ? a.comfort_temperature : null, (v) => degrees(hass, v)],
      ["humidex", a.reference === "humidex" ? a.humidex : null, (v) => number(hass, v)],
      ["dewPoint", a.dew_point, (v) => degrees(hass, v)],
    ].filter(([, value]) => value !== null && value !== undefined);
    if (!values.length) return "";
    const cells = values.map(([key, value, format]) => `<div><b>${format(value)}</b><span>${text(hass, key)}</span></div>`);
    return `<section class="s-climate"><h3>${text(hass, "climate")}</h3><div class="stats">${cells.join("")}</div></section>`;
  }

  devices(hass, a) {
    const tiles = Object.entries(a.devices || {}).map(([id, device]) => {
      const state = hass.states[id];
      const facts = [];
      let value = text(hass, "deviceDown");
      if (device.available) {
        value = typeof device.command === "number" ? degrees(hass, device.command) : text(hass, device.command || "off");
        if (state?.attributes.current_temperature !== undefined) facts.push(`${text(hass, "room")} ${degrees(hass, state.attributes.current_temperature)}`);
        if (device.offset) facts.push(`${text(hass, "offset")} ${device.offset > 0 ? "+" : ""}${number(hass, device.offset)}`);
      }
      return `<li class="${device.available ? "" : "down"}">
        <div class="device-name">${icon(device.role === "cool" ? "mdi:air-conditioner" : "mdi:radiator")}<span>${esc(state?.attributes.friendly_name || id)}</span></div>
        <b>${esc(value)}</b><small>${esc(facts.join(" · ")) || "&nbsp;"}</small></li>`;
    });
    return tiles.length ? `<section class="s-devices"><h3>${text(hass, "devices")}</h3><ul class="devices">${tiles.join("")}</ul></section>` : "";
  }

  // The chart: room temperature and target on one scale, running phases behind them

  async loadHistory() {
    const hass = liveHass();
    const end = new Date();
    const start = new Date(end - HISTORY_HOURS * 3600e3);
    try {
      const result = await hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: [this.entityId],
        minimal_response: false,
        no_attributes: false,
        significant_changes_only: false,
      });
      const points = (result[this.entityId] || []).map((row) => ({
        time: (row.lu ?? row.lc) * 1000,
        room: row.a?.current_temperature ?? null,
        target: row.s === "off" ? null : (row.a?.temperature ?? null),
        running: ["heating", "cooling", "drying", "fan"].includes(row.a?.hvac_action),
      }));
      this.chart(hass, points, start.getTime(), end.getTime());
    } catch (err) {
      this.$.chart.innerHTML = `<p class="empty">${text(hass, "noHistory")}</p>`;
    }
  }

  chart(hass, points, start, end) {
    const rooms = points.filter((p) => p.room !== null);
    if (rooms.length < 2) {
      this.$.chart.innerHTML = `<p class="empty">${text(hass, "noHistory")}</p>`;
      return;
    }
    const width = this.$.chart.clientWidth || 380;
    const height = 132;
    const pad = { left: 30, right: 6, top: 8, bottom: 20 };
    const values = points.flatMap((p) => [p.room, p.target]).filter((v) => v !== null);
    const low = Math.floor(Math.min(...values) - 0.25);
    const high = Math.ceil(Math.max(...values) + 0.25);
    const x = (time) => pad.left + ((time - start) / (end - start)) * (width - pad.left - pad.right);
    const y = (value) => pad.top + ((high - value) / (high - low || 1)) * (height - pad.top - pad.bottom);
    const until = (i) => (i + 1 < points.length ? points[i + 1].time : end);

    let bands = "";
    let lineRoom = "";
    let lineTarget = "";
    points.forEach((p, i) => {
      const x1 = Math.max(x(p.time), pad.left);
      const x2 = x(until(i));
      if (p.running) bands += `<rect class="band" x="${x1.toFixed(1)}" y="${pad.top}" width="${Math.max(0.5, x2 - x1).toFixed(1)}" height="${height - pad.top - pad.bottom}"/>`;
      if (p.target !== null) lineTarget += `M${x1.toFixed(1)} ${y(p.target).toFixed(1)}H${x2.toFixed(1)}`;
    });
    rooms.forEach((p, i) => {
      lineRoom += `${i ? "L" : "M"}${Math.max(x(p.time), pad.left).toFixed(1)} ${y(p.room).toFixed(1)}`;
    });
    lineRoom += `L${x(end).toFixed(1)} ${y(rooms.at(-1).room).toFixed(1)}`;

    let grid = "";
    const ticks = 3;
    for (let i = 0; i < ticks; i++) {
      const value = low + ((high - low) * i) / (ticks - 1);
      grid += `<line class="grid" x1="${pad.left}" x2="${width - pad.right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis" x="${pad.left - 5}" y="${y(value) + 3.5}" text-anchor="end">${number(hass, value, value % 1 ? 1 : 0)}°</text>`;
    }
    for (let hours = HISTORY_HOURS - 6; hours > 0; hours -= 6) {
      const time = end - hours * 3600e3;
      grid += `<text class="axis" x="${x(time)}" y="${height - 5}" text-anchor="middle">${clock(hass, time)}</text>`;
    }

    this.$.chart.innerHTML = `
      <div class="legend">
        <span><i class="room"></i>${text(hass, "room")}</span><span><i class="target"></i>${text(hass, "target")}</span><span><i class="band"></i>${text(hass, "heatingBand")}</span>
      </div>
      <div class="plot">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${text(hass, "history")}: ${text(hass, "room")} ${degrees(hass, rooms.at(-1).room)}">
          ${bands}${grid}
          <path class="target" d="${lineTarget}"/><path class="room" d="${lineRoom}"/>
          <line class="cross" y1="${pad.top}" y2="${height - pad.bottom}" visibility="hidden"/>
          <circle class="dot" r="4" visibility="hidden"/>
        </svg>
        <div class="tip" hidden></div>
      </div>`;

    const plot = this.$.chart.querySelector(".plot");
    const cross = plot.querySelector(".cross");
    const dot = plot.querySelector(".dot");
    const tip = plot.querySelector(".tip");
    const hide = () => {
      cross.setAttribute("visibility", "hidden");
      dot.setAttribute("visibility", "hidden");
      tip.hidden = true;
    };
    plot.addEventListener("pointermove", (event) => {
      const box = plot.getBoundingClientRect();
      const scale = box.width / width;
      const time = start + (((event.clientX - box.left) / scale - pad.left) / (width - pad.left - pad.right)) * (end - start);
      if (time < start || time > end) return hide();
      const at = points.findLast((p) => p.time <= time) || points[0];
      const room = rooms.findLast((p) => p.time <= time) || rooms[0];
      const px = x(time);
      cross.setAttribute("x1", px);
      cross.setAttribute("x2", px);
      cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", px);
      dot.setAttribute("cy", y(room.room));
      dot.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.innerHTML = `<b>${clock(hass, time)}</b><div><i class="room"></i>${text(hass, "room")} ${degrees(hass, room.room)}</div>${at.target !== null ? `<div><i class="target"></i>${text(hass, "target")} ${degrees(hass, at.target)}</div>` : ""}`;
      const tipWidth = tip.offsetWidth;
      const left = px * scale;
      tip.style.left = `${left + 12 + tipWidth > box.width ? left - 12 - tipWidth : left + 12}px`;
    });
    plot.addEventListener("pointerleave", hide);
  }
}

const POPUP_CSS = `
  :host { position: fixed; inset: 0; z-index: 100; display: flex; align-items: center; justify-content: center; font-family: var(--ha-font-family-body, Roboto, Noto, sans-serif); color: var(--primary-text-color); }
  #backdrop { position: absolute; inset: 0; background: var(--mdc-dialog-scrim-color, rgba(0, 0, 0, .5)); -webkit-backdrop-filter: var(--ha-dialog-scrim-backdrop-filter, none); backdrop-filter: var(--ha-dialog-scrim-backdrop-filter, none); animation: fade .16s ease-out; }
  #sheet { --room: ${COOL}; --target: ${WARM}; --solid: var(--primary-background-color, #fff); --surface: var(--ha-dialog-surface-background, var(--mdc-theme-surface, var(--card-background-color, #fff))); position: relative; width: min(460px, 100vw); max-height: min(92vh, 900px); max-height: min(92dvh, 900px); overflow-y: auto; overscroll-behavior: contain; padding: 16px 18px calc(14px + env(safe-area-inset-bottom)); background: var(--surface); -webkit-backdrop-filter: var(--ha-dialog-surface-backdrop-filter, none); backdrop-filter: var(--ha-dialog-surface-backdrop-filter, none); border: var(--ha-card-border, none); border-radius: 24px; box-shadow: var(--dialog-box-shadow, 0 12px 40px rgba(0, 0, 0, .35)); animation: rise .2s cubic-bezier(.2, .8, .3, 1); }
  #sheet.dark { --room: #3987e5; }
  header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  h2 { margin: 0 0 6px; font-size: 20px; font-weight: 500; line-height: 1.2; }
  h3 { margin: 0 0 8px; font-size: 12px; font-weight: 500; letter-spacing: .04em; color: var(--secondary-text-color); }
  section { margin-top: 14px; }
  .tabs { display: flex; gap: 4px; margin-top: 12px; padding: 3px; border-radius: 12px; background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); }
  .tabs button { flex: 1; min-height: 34px; font-size: 13px; border-radius: 9px; color: var(--secondary-text-color); }
  .tabs button[aria-selected="true"] { font-weight: 500; color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-text-color) 12%, transparent); }
  .round { width: 40px; height: 40px; flex: none; display: grid; place-items: center; border-radius: 50%; background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); }
  .pill { display: inline-flex; align-items: center; gap: 5px; font-size: 13px; font-weight: 500; }
  .pill ha-icon { --mdc-icon-size: 16px; color: var(--tone); }
  #notice p { margin: 10px 0 0; padding: 9px 12px; font-size: 13px; line-height: 1.35; border-radius: 12px; background: color-mix(in srgb, var(--tone) 10%, transparent); }
  #dial { position: relative; width: min(250px, 100%); margin: 10px auto -12px; aspect-ratio: 1; outline-offset: -8px; border-radius: 50%; }
  #dial svg { width: 100%; height: 100%; display: block; touch-action: none; cursor: grab; user-select: none; }
  #dial.readonly svg { cursor: default; }
  #dial.readonly #handle { display: none; }
  .seg { fill: none; stroke-width: 15; transition: opacity .15s linear; }
  #handle { stroke: var(--solid); stroke-width: 4; filter: drop-shadow(0 1px 3px rgba(0, 0, 0, .4)); }
  #now { fill: var(--primary-text-color); stroke: var(--solid); stroke-width: 2; }
  #center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; padding-bottom: 10px; }
  #label { font-size: 12px; letter-spacing: .04em; color: var(--secondary-text-color); }
  #big { font-size: 50px; font-weight: 300; line-height: 1.1; font-variant-numeric: tabular-nums; }
  #small { min-height: 18px; font-size: 14px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .step[hidden] { display: none; }
  .step { position: absolute; bottom: 8px; width: 44px; height: 44px; }
  #down { left: 26%; } #up { right: 26%; }
  .choices { display: flex; gap: 8px; }
  .choice { flex: 1 1 0; min-width: 0; min-height: 54px; padding: 8px 2px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; font-size: 12px; line-height: 1.2; border-radius: 14px; background: color-mix(in srgb, var(--primary-text-color) 6%, transparent); transition: background .12s; }
  .choice small { font-size: 11px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .choice span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .choice.active { font-weight: 500; background: color-mix(in srgb, var(--tone) 16%, transparent); box-shadow: inset 0 0 0 1.5px var(--tone); }
  .choice.active ha-icon { color: var(--tone); }
  .choice.active small { color: inherit; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 11px 6px 8px; font-size: 13px; border-radius: 16px; color: var(--secondary-text-color); background: color-mix(in srgb, var(--primary-text-color) 6%, transparent); }
  .chip ha-icon { --mdc-icon-size: 16px; }
  button.chip { min-height: 32px; }
  .chip.disabled { opacity: .55; text-decoration: line-through; background: none; box-shadow: inset 0 0 0 1px var(--divider-color, rgba(127, 127, 127, .3)); }
  .chip.on { color: var(--primary-text-color); font-weight: 500; background: color-mix(in srgb, var(--primary-color, ${COOL}) 18%, transparent); }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(72px, 1fr)); gap: 8px; }
  .stats div { padding: 9px 4px; display: flex; flex-direction: column; align-items: center; gap: 1px; border-radius: 12px; background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); }
  .stats b { font-size: 15px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .stats span { font-size: 11px; color: var(--secondary-text-color); }
  .devices { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }
  .devices li { min-width: 0; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; border-radius: 12px; background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); }
  .device-name { display: flex; align-items: center; gap: 6px; min-width: 0; font-size: 12px; color: var(--secondary-text-color); }
  .device-name span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .device-name ha-icon { --mdc-icon-size: 16px; flex: none; }
  .devices b { font-size: 20px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .devices small { font-size: 11px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .devices .down b, .devices .down ha-icon { font-size: 14px; color: var(--error-color, #d33); }
  #chart { min-height: 150px; }
  .empty { margin: 0; padding: 20px 0; text-align: center; font-size: 13px; color: var(--secondary-text-color); }
  .legend { display: flex; gap: 14px; margin-bottom: 4px; font-size: 12px; color: var(--secondary-text-color); }
  .legend span, .tip div { display: inline-flex; align-items: center; gap: 5px; }
  .legend i, .tip i { width: 12px; height: 2px; border-radius: 1px; }
  i.room { background: var(--room); } i.target { background: var(--target); }
  .legend i.band { height: 10px; background: color-mix(in srgb, var(--primary-text-color) 12%, transparent); }
  .plot { position: relative; touch-action: pan-y; }
  .plot svg { display: block; width: 100%; height: auto; }
  rect.band { fill: var(--primary-text-color); fill-opacity: .08; }
  .grid { stroke: var(--divider-color, rgba(127, 127, 127, .25)); stroke-width: 1; }
  .axis { font-size: 10px; fill: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  path.room, path.target { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  path.room { stroke: var(--room); } path.target { stroke: var(--target); }
  .cross { stroke: var(--secondary-text-color); stroke-width: 1; }
  .dot { fill: var(--room); stroke: var(--solid); stroke-width: 2; }
  .tip { position: absolute; top: 4px; padding: 6px 9px; font-size: 12px; line-height: 1.45; white-space: nowrap; pointer-events: none; border-radius: 8px; background: var(--solid); box-shadow: 0 2px 10px rgba(0, 0, 0, .28); font-variant-numeric: tabular-nums; }
  .tip b { font-weight: 500; }
  .tip div { display: flex; }
  #footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
  .link { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 10px; font-size: 13px; border-radius: 10px; color: var(--secondary-text-color); }
  .link ha-icon { --mdc-icon-size: 18px; }
  @keyframes fade { from { opacity: 0; } }
  @keyframes rise { from { opacity: 0; transform: translateY(16px); } }
  @media (max-width: 520px) {
    :host { align-items: flex-end; }
    #sheet { width: 100vw; border-radius: 22px 22px 0 0; }
  }
  @media (min-width: 700px) and (orientation: landscape) {
    #sheet { width: min(860px, 94vw); }
    #page-control:not([hidden]) { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); gap: 0 28px; align-items: center; }
    #notice { grid-column: 1 / -1; }
    #dial { width: min(280px, 56vh); margin: 10px auto 0; }
    #sections > section:first-child { margin-top: 0; }
    #page-details:not([hidden]) { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0 28px; }
    #details { display: contents; }
    .s-routines, .s-climate { grid-column: 1; }
    .s-chart { grid-column: 2; grid-row: 1 / span 2; }
    #footer { grid-column: 1 / -1; }
    .s-devices { grid-column: 1 / -1; }
    .devices { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
  }
  @media (prefers-reduced-motion: reduce) {
    #backdrop, #sheet { animation: none; }
    .seg, .choice { transition: none; }
  }
`;

if (!customElements.get("thermgenie-card")) {
  customElements.define("thermgenie-card", ThermGenieCard);
  customElements.define("thermgenie-popup", ThermGeniePopup);

  // Whatever opens the dialog of a ThermGenie thermostat, a tile or a list, it gets the popup.
  // If this ever stops matching, Home Assistant simply shows its standard dialog again.
  window.addEventListener(
    "hass-more-info",
    (event) => {
      const entityId = event.detail?.entityId;
      if (entityId && liveHass()?.entities?.[entityId]?.platform === "thermgenie" && entityId.startsWith("climate.")) {
        event.stopPropagation();
        ThermGeniePopup.open(entityId);
      }
    },
    true,
  );

  window.customCards = window.customCards || [];
  window.customCards.push({ type: "thermgenie-card", name: "ThermGenie", description: TEXT.de.description, preview: true });
}
