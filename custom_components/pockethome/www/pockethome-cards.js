/* PocketHome dashboard cards (original code, not part of the heating-schedule-card fork).
   - pockethome-modes-card : summer / absence / holiday of the central unit, entities found automatically.
   - pockethome-rooms-card : per thermostat: temperature, heating on/off and a drop-down to change its program.
   Entities are found through the Home Assistant entity registry (platform "pockethome"), so
   no entity id has to be written in the dashboard. */

const TEXTS = {
  en: { central: "Central unit", thermostats: "Thermostats", today: "today", total: "Heating total", modes: "PocketHome: central unit modes", modesD: "Summer, absence and holiday", rooms: "PocketHome: thermostats", roomsD: "Temperature, heating on/off, program, energy of the day" },
  fr: { central: "Centrale", thermostats: "Thermostats", today: "aujourd'hui", total: "Chauffage total", modes: "PocketHome : modes de la centrale", modesD: "Été, absence et vacances", rooms: "PocketHome : thermostats", roomsD: "Température, chauffage en cours, programme, énergie du jour" },
  de: { central: "Zentrale", thermostats: "Thermostate", today: "heute", total: "Heizung gesamt", modes: "PocketHome: Modi der Zentrale", modesD: "Sommer, Abwesenheit und Urlaub", rooms: "PocketHome: Thermostate", roomsD: "Temperatur, Heizbetrieb, Programm, Tagesenergie" },
  cs: { central: "Centrála", thermostats: "Termostaty", today: "dnes", total: "Topení celkem", modes: "PocketHome: režimy centrály", modesD: "Léto, nepřítomnost a dovolená", rooms: "PocketHome: termostaty", roomsD: "Teplota, topení, program, energie za den" },
};
const text = (hass, key) => {
  const lang = String(hass?.locale?.language || navigator.language || "en").slice(0, 2).toLowerCase();
  return (TEXTS[lang] || TEXTS.en)[key];
};

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* Entities of the integration: [{entity_id, device_id, domain, state}] */
function pocketHomeEntities(hass) {
  return Object.values(hass.entities || {})
    .filter((e) => e.platform === "pockethome" && hass.states[e.entity_id])
    .map((e) => ({ id: e.entity_id, device: e.device_id, domain: e.entity_id.split(".")[0], st: hass.states[e.entity_id] }));
}

class PocketHomeModesCard extends HTMLElement {
  setConfig(config) { this._config = config || {}; }
  getCardSize() { return 6; }
  static getStubConfig() { return {}; }

  set hass(hass) {
    this._hass = hass;
    const byRole = {};
    // An unavailable entity has no attributes: the role seen earlier is remembered in the browser.
    let known = {};
    try { known = JSON.parse(localStorage.getItem("pockethome-roles") || "{}"); } catch (err) { /* no storage */ }
    for (const e of pocketHomeEntities(hass)) {
      const role = e.st.attributes.role || known[e.id];
      if (!role) continue;
      byRole[role] = e.id;
      if (known[e.id] !== role) {
        known[e.id] = role;
        try { localStorage.setItem("pockethome-roles", JSON.stringify(known)); } catch (err) { /* no storage */ }
      }
    }
    const rows = [];
    const group = (ids) => { const l = ids.filter((r) => byRole[r]).map((r) => ({ entity: byRole[r] })); if (l.length) { if (rows.length) rows.push({ type: "divider" }); rows.push(...l); } };
    group(["summer"]);
    group(["absence", "absence_temp"]);
    group(["holiday", "holiday_temp", "holiday_start", "holiday_end"]);
    const key = JSON.stringify(rows);
    if (key !== this._key) {
      this._key = key;
      this._build(rows);
    }
    if (this._inner) this._inner.hass = hass;
  }

  async _build(rows) {
    const helpers = await window.loadCardHelpers();
    this._inner = await helpers.createCardElement({ type: "entities", title: this._config.title || text(this._hass, "central"), show_header_toggle: false, entities: rows });
    this._inner.hass = this._hass;
    this.replaceChildren(this._inner);
  }
}

class PocketHomeRoomsCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
  }
  getCardSize() { return 8; }
  static getStubConfig() { return {}; }

  set hass(hass) {
    this._hass = hass;
    // A re-render would close an open drop-down: wait until it is closed.
    if (this.querySelector("select:focus")) return;
    this._render();
  }

  _rooms() {
    const all = pocketHomeEntities(this._hass);
    return all.filter((e) => e.domain === "climate").map((c) => {
      const select = all.find((e) => e.domain === "select" && e.device === c.device);
      const sibling = (cls) => all.find((e) => e.domain === "sensor" && e.device === c.device && e.st.attributes.device_class === cls);
      return { climate: c.st, select: select?.st, selectId: select?.id, energy: sibling("energy") };
    });
  }

  /* kWh since midnight per energy sensor, from the recorder's 5-minute statistics (compiled every 5 min,
     so reloaded at most that often). */
  _loadToday(ids) {
    const now = Date.now();
    if (!ids.length || this._todayBusy || now - (this._todayAt || 0) < 300000) return;
    this._todayBusy = true;
    const start = new Date(); start.setHours(0, 0, 0, 0);
    this._hass.callWS({ type: "recorder/statistics_during_period", start_time: start.toISOString(), statistic_ids: ids, period: "5minute", types: ["change"] })
      .then((res) => {
        this._today = {};
        for (const id of ids) {
          // Statistics are in the sensor's own unit: converted to kWh.
          const unit = this._hass.states[id]?.attributes.unit_of_measurement;
          const factor = unit === "Wh" ? 0.001 : unit === "MWh" ? 1000 : 1;
          this._today[id] = (res[id] || []).reduce((sum, r) => sum + (r.change || 0), 0) * factor;
        }
        this._todayAt = Date.now();
      })
      .catch(() => { this._todayAt = Date.now(); })   // no recorder statistics: only the live power is shown
      .finally(() => { this._todayBusy = false; this._render(); });
  }

  _render() {
    if (!this._hass) return;
    if (!this._root) {
      this._root = document.createElement("ha-card");
      this._root.innerHTML = `<style>
        .room { padding:12px 16px; border-top:1px solid var(--divider-color); }
        .room:first-of-type { border-top:none; }
        .head { display:flex; align-items:center; gap:10px; }
        .head .name { flex:1; font-weight:500; }
        .heat { --mdc-icon-size:22px; color:var(--secondary-text-color); }
        .heat.on { color:var(--state-climate-heat-color, #ff8100); }
        .temps { color:var(--secondary-text-color); }
        select { font:inherit; height:34px; margin-top:8px; width:100%; box-sizing:border-box; padding:0 8px;
          border:1px solid var(--divider-color); border-radius:8px; background:var(--card-background-color); color:var(--primary-text-color); }
        .usage { margin-top:8px; color:var(--secondary-text-color); cursor:pointer; }
        .usage:hover { color:var(--primary-text-color); }
        .total { font-weight:500; background:var(--secondary-background-color); }
        h1 { font-size:var(--ha-card-header-font-size, 24px); font-weight:400; margin:0; padding:16px 16px 4px; }
      </style><h1></h1><div class="rooms"></div>`;
      this.appendChild(this._root);
    }
    this._root.querySelector("h1").textContent = this._config.title || text(this._hass, "thermostats");
    const rooms = this._rooms();
    const extra = [].concat(this._config.extra_energy || []);   // e.g. a Shelly energy sensor outside the central unit
    this._loadToday([...rooms.filter((r) => r.energy).map((r) => r.energy.id), ...extra]);
    const kwh = (v) => `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })} kWh`;
    let totalKwh = 0, anyKwh = false;
    for (const id of extra) if (this._today?.[id] !== undefined) { totalKwh += this._today[id]; anyKwh = true; }
    const html = rooms.map((r, i) => {
      const a = r.climate.attributes;
      const unavailable = r.climate.state === "unavailable";
      const heating = a.hvac_action === "heating";
      const options = r.select ? (r.select.attributes.options || []).map((o) => `<option value="${esc(o)}"${o === r.select.state ? " selected" : ""}>${esc(o)}</option>`).join("") : "";
      const t = a.current_temperature, sp = a.temperature;
      const today = r.energy ? this._today?.[r.energy.id] : undefined;
      if (today !== undefined) { totalKwh += today; anyKwh = true; }
      const usage = today !== undefined
        ? `<div class="usage" data-more="${esc(r.energy.id)}" role="button" tabindex="0">⚡ ${kwh(today)} ${text(this._hass, "today")}</div>` : "";
      return `<div class="room">
        <div class="head"><ha-icon class="heat${heating ? " on" : ""}" icon="${heating ? "mdi:fire" : "mdi:radiator-disabled"}"></ha-icon>
          <span class="name">${esc(a.friendly_name || r.climate.entity_id)}</span>
          <span class="temps">${unavailable ? "—" : `${t ?? "?"}° → ${sp ?? "—"}°`}</span></div>
        ${r.select ? `<select data-e="${esc(r.selectId)}"${unavailable ? " disabled" : ""}>${options}</select>` : ""}
        ${usage}
      </div>`;
    }).join("") + `<div class="room total"><div class="head"><span class="name">${esc(this._config.total_label || text(this._hass, "total"))}</span>
      <span class="temps">${anyKwh ? `${kwh(totalKwh)} ${text(this._hass, "today")}` : "—"}</span></div></div>`;
    const container = this._root.querySelector(".rooms");
    if (container.innerHTML !== html) {
      container.innerHTML = html;
      container.querySelectorAll("[data-more]").forEach((el) => {
        const open = () => el.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: el.dataset.more }, bubbles: true, composed: true }));
        el.addEventListener("click", open);
        el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") open(); });
      });
      container.querySelectorAll("select").forEach((s) => s.addEventListener("change", () =>
        this._hass.callService("select", "select_option", { entity_id: s.dataset.e, option: s.value })));
    }
  }
}

customElements.define("pockethome-modes-card", PocketHomeModesCard);
customElements.define("pockethome-rooms-card", PocketHomeRoomsCard);
window.customCards = window.customCards || [];
const picker = (key, descKey) => ({ get name() { return text(null, key); }, get description() { return text(null, descKey); } });
window.customCards.push(
  { type: "pockethome-modes-card", ...picker("modes", "modesD") },
  { type: "pockethome-rooms-card", ...picker("rooms", "roomsD") },
);
