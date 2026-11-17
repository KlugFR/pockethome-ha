/* pockethome-program-card - edit a program of the PocketHome (Elektrobock PH-CJ39) central unit.

   THIS FILE IS A FORK of heating-schedule-card
   (https://github.com/Pandetthe/heating-schedule-card), Copyright (c) 2026 Jakub Jurczyk,
   MIT license (see LICENSE-heating-schedule-card). The layout, the interactions and most of
   the code come from that project. Changes made for PocketHome are listed in NOTICE.md:
   - data comes from the `pockethome.get_program` service and is saved with
     `pockethome.set_program` (no `schedule` helper, no schedule/list or schedule/update);
   - a program day is at most 6 slots (start, temperature); a slot lasts until the next one,
     so the end of a block is computed, not edited, and the first block starts at 00:00;
   - 10 minute time grid, 5-30 °C in 0.5 steps, editable program name, French translation.

   Usage: type: custom:pockethome-program-card, with `program: 10` for a fixed program or
   without `program` for a drop-down of all programs. */

import { TRANSLATIONS, pickLanguage, format } from "./i18n.js";
import { hhmm, toMinutes, uses12h, numberFormatter, pad2 } from "./format.js";
import { haButton, haIconButton } from "./ha-elements.js";
import { timeField } from "./time-field.js";
import { expand, collapse } from "./motion.js";
import { clipboard, cards, setClipboard } from "./clipboard.js";
import { styles } from "./styles.js";

const VERSION = "0.1.0";
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const MAX_BLOCKS = 6;      // limit of the central unit
const GRID = 10;           // minutes
const fmtMin = (m) => `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}`;
/* Error messages can carry text from the central unit or from Home Assistant: escaped before innerHTML. */
const LAST_KEY = "pockethome-program-card:last";
let namesPromise = null;   // program names (get_programs reads all 22: once per page, shared by cards)
const names = {};
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class PocketHomeProgramCard extends HTMLElement {
  connectedCallback() {
    cards.add(this);
    if (this._card) this._render();
  }

  disconnectedCallback() {
    cards.delete(this);
  }

  setConfig(config) {
    const fixed = config?.program != null;
    const program = fixed ? Number(config.program) : null;
    if (fixed && (!Number.isInteger(program) || program < 1 || program > 22)) {
      throw new Error(TRANSLATIONS[pickLanguage(config?.language || navigator.language)].program_required);
    }
    this._config = { unit: "°C", group_days: true, ...config };
    this._fixed = fixed;     // no `program`: the card shows a drop-down
    this._program = program;
    this._data = null;       // { name, days: {day: [blocks]} }
    this._dirty = false;
    this._error = null;
    this._saving = false;
    // Which days are expanded. Only today by default.
    this._expanded = new Set([DAYS[(new Date().getDay() + 6) % 7]]);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Re-rendering on every hass change would interrupt a slider drag, so the card
    // loads once and renders after loading and after user actions.
    if (!first) return;
    if (!this._fixed && !this._program) {
      try { this._program = Number(localStorage.getItem(LAST_KEY)) || null; } catch (e) { /* no storage */ }
    }
    if (!this._fixed) this._loadNames();
    if (this._program) this._load(); else this._render();
  }

  /* Program names for the drop-down: the list is usable at once (numbers), names fill in
     when the central unit has answered. */
  async _loadNames() {
    if (!namesPromise) {
      namesPromise = this._hass.callWS({ type: "call_service", domain: "pockethome", service: "get_programs", return_response: true })
        .then((r) => r.response.programs.forEach((p) => { names[p.number] = p.name; }))
        .catch(() => { namesPromise = null; });
    }
    await namesPromise;
    const select = this._body?.querySelector(".prog-select");
    if (select) [...select.options].forEach((o) => { if (o.value) o.textContent = this._optionLabel(+o.value); });
  }

  _optionLabel(n) {
    return names[n] ? `${n} · ${names[n]}` : String(n);
  }

  /* Title: `title` from the config; else "Programs" with the drop-down, "N · name" for a fixed program. */
  _title() {
    if (this._config.title) return this._config.title;
    return this._fixed ? `${this._program} · ${this._data?.name || ""}` : this._t("programs_title");
  }

  _selectorHtml() {
    if (this._fixed) return "";
    const locked = this._dirty || this._saving;
    const opts = Array.from({ length: 22 }, (_, i) => i + 1)
      .map((n) => `<option value="${n}"${n === this._program ? " selected" : ""}>${esc(this._optionLabel(n))}</option>`).join("");
    return `<select class="prog-select" aria-label="${this._t("program_label")}"${locked ? ` disabled title="${this._t("select_locked")}"` : ""}>${
      this._program ? "" : `<option value="" selected disabled>${this._t("choose_program")}</option>`}${opts}</select>`;
  }

  _bindSelector() {
    const select = this._body.querySelector(".prog-select");
    if (!select) return;
    select.addEventListener("change", () => {
      this._program = Number(select.value);
      try { localStorage.setItem(LAST_KEY, String(this._program)); } catch (e) { /* no storage */ }
      this._data = null;
      this._error = null;
      this._dirty = false;
      this._saved = false;
      this._expanded = new Set([DAYS[(new Date().getDay() + 6) % 7]]);
      this._render();
      this._load();
    });
  }

  getCardSize() {
    return this._data ? 3 + DAYS.length * 2 : 4;
  }

  static getStubConfig() {
    return { program: 1 };
  }

  _language() {
    return pickLanguage(this._config?.language || this._hass?.locale?.language
      || this._hass?.language || navigator.language);
  }

  /* Translated text; keys missing in a language fall back to English. */
  _t(key, params) {
    const text = TRANSLATIONS[this._language()][key] ?? TRANSLATIONS.en[key];
    return typeof text === "string" ? format(text, params) : text;
  }

  _blockCount(n) {
    const forms = this._t("blocks");
    if (n === 0) return forms.zero;
    const form = forms[new Intl.PluralRules(this._language()).select(n)] ?? forms.other;
    return format(form, { n });
  }

  _fit(v) {
    const { min, max, step } = this._limits();
    return Math.min(max, Math.max(min, Math.round(Number(v) / step) * step));
  }

  /* Limits of the central unit's thermostats (the config can override them). */
  _limits() {
    return {
      min: Number(this._config.min ?? 5),
      max: Number(this._config.max ?? 30),
      step: Number(this._config.step ?? 0.5),
    };
  }

  async _load() {
    try {
      const res = await this._hass.callWS({
        type: "call_service",
        domain: "pockethome",
        service: "get_program",
        service_data: { program: this._program },
        return_response: true,
      });
      const p = res.response;
      const days = {};
      // Temperature in force at midnight: the last slot of the closest previous day that
      // has slots (the week wraps around).
      const carryFor = (d) => {
        for (let i = 1; i <= 7; i++) {
          const prev = p.days[(d + 7 - i) % 7];
          if (prev.length) return Number(prev[prev.length - 1].temperature);
        }
        return this._limits().min;
      };
      DAYS.forEach((key, d) => {
        const blocks = p.days[d].map((s) => ({ from: hhmm(s.start), value: Number(s.temperature) }));
        // A day that does not start at 00:00 continues the previous day's last slot:
        // shown (and saved) as an explicit 00:00 block with that temperature.
        if (!blocks.length || blocks[0].from !== "00:00") blocks.unshift({ from: "00:00", value: carryFor(d) });
        days[key] = blocks;
      });
      this._data = { name: p.name, days };
      DAYS.forEach((k) => this._recompute(k));
      this._layout = this._initialLayout();
      this._original = this._signature();
      this._error = null;
    } catch (e) {
      this._error = this._t("load_failed", { error: e.message || JSON.stringify(e) });
    }
    this._render();
  }

  /* Sorts a day's blocks and sets each block's end to the next block's start
     (24:00 for the last one). */
  _recompute(key) {
    const b = this._data.days[key].sort((x, y) => toMinutes(x.from) - toMinutes(y.from));
    b.forEach((blk, i) => { blk.to = i + 1 < b.length ? b[i + 1].from : "24:00"; });
  }

  /* Group layout computed on load: with group_days:true every day with identical
     blocks goes into one group (also non-adjacent ones). After that the layout is
     editing state; days move between groups with chips (_toggleDay). */
  _initialLayout() {
    if (!this._config.group_days) return DAYS.map((k) => [k]);
    const sig = (d) => JSON.stringify(this._data.days[d].map((b) => [b.from, b.value]));
    const bySig = new Map();
    for (const k of DAYS) {
      const s = sig(k);
      if (!bySig.has(s)) bySig.set(s, []);
      bySig.get(s).push(k);
    }
    return [...bySig.values()];
  }

  /* Name and blocks of every day in comparable form - to check whether anything
     really changed. */
  _signature() {
    return JSON.stringify([this._data.name, DAYS.map((k) => [...this._data.days[k]]
      .sort((a, b) => toMinutes(a.from) - toMinutes(b.from))
      .map((b) => [b.from, Number(b.value)]))]);
  }

  _groups() {
    const index = (k) => DAYS.indexOf(k);
    return this._layout
      .map((days) => [...days].sort((a, b) => index(a) - index(b)))
      .sort((a, b) => index(a[0]) - index(b[0]))
      .map((days) => ({
        days,
        full: this._config.group_days ? null : this._t("days_full")[index(days[0])],
      }));
  }

  /* A run of days as "a–b", commas only between scattered pieces; the whole week = "Every day". */
  _label(g) {
    if (g.full) return g.full;
    if (g.days.length === 7) return this._t("every_day");
    const short = this._t("days_short");
    const idx = g.days.map((k) => DAYS.indexOf(k));
    const parts = [];
    for (let i = 0; i < idx.length; ) {
      let j = i;
      while (j + 1 < idx.length && idx[j + 1] === idx[j] + 1) j++;
      const len = j - i + 1;
      parts.push(len >= 2 ? `${short[idx[i]]}–${short[idx[j]]}` : short[idx[i]]);
      i = j + 1;
    }
    return parts.join(", ");
  }

  /* Day chip in an expanded group: a day from the group splits into its own group
     (same blocks, ready to change); a day outside the group joins it and copies
     the group's blocks to it. */
  _toggleDay(group, day) {
    const source = this._layout.find((u) => u.includes(day));
    if (group.days.includes(day)) {
      if (group.days.length === 1) return;
      source.splice(source.indexOf(day), 1);
      this._layout.push([day]);
      this._newGroup = day;
    } else {
      source.splice(source.indexOf(day), 1);
      if (!source.length) this._layout.splice(this._layout.indexOf(source), 1);
      this._layout.find((u) => u.includes(group.days[0])).push(day);
      this._data.days[day] = this._data.days[group.days[0]].map((b) => ({ ...b }));
      this._dirty = true;
    }
    this._expanded.add(day);
    for (const k of source) this._expanded.add(k);
    for (const k of group.days) this._expanded.add(k);
    this._render();
  }

  _validationErrors() {
    const errors = [];
    DAYS.forEach((key, d) => {
      const day = this._t("days_short")[d];
      const blocks = this._data.days[key];
      if (blocks.length > MAX_BLOCKS) errors.push(this._t("max_blocks", { day }));
      for (let i = 1; i < blocks.length; i++) {
        if (toMinutes(blocks[i].from) <= toMinutes(blocks[i - 1].from)) {
          errors.push(this._t("not_increasing", { day, at: blocks[i].from }));
        }
      }
    });
    return errors;
  }

  _change(group, idx, field, value) {
    for (const d of group.days) {
      const block = this._data.days[d][idx];
      if (!block) continue;
      block[field] = value;
    }
    if (field === "from") {
      // A start can move a block past its neighbours: re-sort and redraw.
      for (const d of group.days) this._recompute(d);
      this._render();
      return;
    }
    // A temperature change does not change the layout - no DOM rebuild: only day
    // summaries, errors and the save bar. Nothing jumps and focus stays in the fields.
    this._refreshState();
  }

  /* Validation errors and the save bar - separate from the rest of the card, so
     a value change refreshes only this part. */
  _renderFooter() {
    const errorsSlot = this._body.querySelector(".errors-slot");
    const barSlot = this._body.querySelector(".save-bar-slot");
    if (!errorsSlot || !barSlot) return;
    const errors = this._validationErrors();
    this._dirty = this._signature() !== this._original;
    const select = this._body.querySelector(".prog-select");
    if (select) select.disabled = this._dirty || this._saving;

    let errorsHtml = "";
    if (errors.length) errorsHtml += `<div class="error">${errors.map((x) => `• ${esc(x)}`).join("<br>")}</div>`;
    if (this._error) errorsHtml += `<div class="error">${esc(this._error)}</div>`;
    if (errorsHtml !== this._errorsHtml) {
      const had = !!this._errorsHtml;
      this._errorsHtml = errorsHtml;
      if (!errorsHtml && had && errorsSlot.firstElementChild) {
        collapse(errorsSlot, () => { errorsSlot.innerHTML = this._errorsHtml; errorsSlot.getAnimations().forEach((a) => a.cancel()); errorsSlot.style.cssText = ""; });
      } else {
        errorsSlot.getAnimations().forEach((a) => a.cancel());
        errorsSlot.style.cssText = "";
        errorsSlot.innerHTML = errorsHtml;
        if (!had) expand(errorsSlot);
      }
    }

    // Save bar only when there is something to save (or a save is running/done).
    const canSave = this._dirty && !errors.length && !this._saving;
    const visible = this._dirty || this._saving || this._saved;
    const show = visible && !barSlot.firstElementChild;
    const hide = !visible && barSlot.firstElementChild;
    this._footerVisible = visible;
    if (hide) {
      collapse(barSlot, () => {
        if (this._dirty || this._saving || this._saved) return;
        barSlot.innerHTML = "";
        barSlot.getAnimations().forEach((a) => a.cancel());
        barSlot.style.cssText = "";
      });
      return;
    }
    if (!visible) return;
    barSlot.getAnimations().forEach((a) => a.cancel());
    barSlot.style.cssText = "";
    barSlot.innerHTML = `<div class="save-bar${canSave ? " changed" : ""}">
        <span class="status">${
          this._saving ? this._t("saving")
          : errors.length ? this._t("fix_errors")
          : this._dirty ? this._t("unsaved")
          : this._t("saved")
        }</span>
        <span class="actions">${this._dirty && !this._saving ? `<span class="slot-discard"></span>` : ""}${this._dirty || this._saving ? `<span class="slot-save"></span>` : ""}</span>
      </div>`;
    const saveSlot = barSlot.querySelector(".slot-save");
    if (saveSlot) {
      const el = haButton(this._t("save"), { primary: true });
      const disabled = !this._dirty || errors.length > 0 || this._saving;
      el.disabled = disabled;
      if (disabled) el.setAttribute("disabled", "");
      el.addEventListener("click", () => this._save());
      saveSlot.replaceWith(el);
    }
    const discardSlot = barSlot.querySelector(".slot-discard");
    if (discardSlot) {
      const el = haButton(this._t("discard"));
      el.addEventListener("click", () => this._discard());
      discardSlot.replaceWith(el);
    }
    if (show) expand(barSlot);
  }

  /* On a full re-render a save bar that was already visible does not slide in again. */
  _renderFooterAfterDraw() {
    const wasVisible = this._footerVisible;
    this._renderFooter();
    const barSlot = this._body.querySelector(".save-bar-slot");
    if (wasVisible && barSlot) barSlot.getAnimations().forEach((a) => a.finish());
  }

  /* "3 blocks · 17.0–21.0 °C" in the group header. */
  _summary(g) {
    const fmt = numberFormatter(this._hass);
    const { unit } = this._config;
    const blocks = this._data.days[g.days[0]];
    const t = blocks.map((b) => Number(b.value));
    const n = blocks.length;
    const count = this._blockCount(n);
    if (!n) return count;
    const lo = Math.min(...t), hi = Math.max(...t);
    return `${count} · ${lo === hi ? fmt(lo) : `${fmt(lo)}–${fmt(hi)}`} ${unit}`;
  }

  _refreshState() {
    this._groups().forEach((g, gi) => {
      const el = this._body.querySelector(`.group[data-g="${gi}"] .summary`);
      if (el) el.textContent = this._summary(g);
    });
    this._renderFooter();
  }

  /* A day always keeps at least one block, and always starts at 00:00: removing the
     first block moves 00:00 to the next one. */
  _remove(group, idx) {
    for (const d of group.days) {
      const blocks = this._data.days[d];
      if (blocks.length <= 1) continue;
      blocks.splice(idx, 1);
      if (idx === 0) blocks[0].from = "00:00";
      this._recompute(d);
    }
    this._dirty = true;
    this._render();
  }

  /* Splits the longest block of the day in two (on the 10 min grid); the new block
     starts with the same temperature. */
  _add(group) {
    const blocks = this._data.days[group.days[0]];
    const day = this._t("days_short")[DAYS.indexOf(group.days[0])];
    if (blocks.length >= MAX_BLOCKS) {
      this._error = this._t("max_blocks", { day });
      this._render();
      return;
    }
    let best = 0, bestLen = -1;
    blocks.forEach((b, i) => {
      const len = toMinutes(b.to) - toMinutes(b.from);
      if (len > bestLen) { best = i; bestLen = len; }
    });
    if (bestLen < 2 * GRID) {
      this._error = this._t("no_free_gap");
      this._render();
      return;
    }
    const start = toMinutes(blocks[best].from) + Math.floor(bestLen / (2 * GRID)) * GRID;
    for (const d of group.days) {
      const b = this._data.days[d];
      b.push({ from: fmtMin(start), value: b[best].value });
      this._recompute(d);
    }
    this._newBlock = { day: group.days[0], from: fmtMin(start) };
    this._error = null;
    this._dirty = true;
    this._render();
  }

  _copy(group) {
    setClipboard({
      schedule: this._program,
      name: this._data.name,
      label: this._label(group),
      days: [...group.days],
      blocks: this._data.days[group.days[0]].map((b) => ({ ...b })),
    });
  }

  _isClipboardSource(group) {
    return !!clipboard && clipboard.schedule === this._program
      && clipboard.days.length === group.days.length && group.days.every((d) => clipboard.days.includes(d));
  }

  /* Pastes the clipboard blocks into every day of the group (replacing its blocks).
     Values are fitted to the range and step of this card's slider. */
  _paste(group) {
    if (!clipboard) return;
    for (const d of group.days) {
      this._data.days[d] = clipboard.blocks.map((b) => ({ ...b, value: this._fit(b.value) }));
      this._recompute(d);
    }
    for (const d of group.days) this._expanded.add(d);
    this._render();
  }

  async _save() {
    if (this._validationErrors().length) return;
    this._saving = true;
    this._render();
    try {
      await this._hass.callService("pockethome", "set_program", {
        program: this._program,
        name: this._data.name,
        days: DAYS.map((key) => this._data.days[key].map((b) => ({ start: b.from, temperature: Number(b.value) }))),
      });
      this._dirty = false;
      this._error = null;
      // Cleared before _load(), because _load() renders the card after saving.
      this._saving = false;
      this._saved = true;
      await this._load();   // read back from the central unit: what is shown is what it holds
      clearTimeout(this._savedTimer);
      this._savedTimer = setTimeout(() => {
        this._saved = false;
        // No re-render while a field is being edited - it would lose focus.
        if (!this._body.matches(":focus-within")) this._render();
      }, 2000);
      return;
    } catch (e) {
      this._error = this._t("save_failed", { error: e.message || JSON.stringify(e) });
    }
    this._saving = false;
    this._render();
  }

  _discard() {
    this._dirty = false;
    this._error = null;
    this._load();
  }

  _render() {
    this._draw();
  }

  _draw() {
    if (!this._card) {
      this._card = document.createElement("ha-card");
      this._style = document.createElement("style");
      this._style.textContent = styles;
      this._card.appendChild(this._style);
      this._body = document.createElement("div");
      this._card.appendChild(this._body);
      this.appendChild(this._card);
    }

    if (!this._data) {
      this._card.header = this._title();
      const msg = this._error ? `<div class="error">${esc(this._error)}</div>`
        : this._program ? `<div class="status">${this._t("loading")}</div>` : "";
      this._body.innerHTML = `<div class="content"><div class="name-row">${this._selectorHtml()}</div>${msg}</div>`;
      this._bindSelector();
      return;
    }
    // "Unsaved changes" only when the data differs from what the central unit holds.
    this._dirty = this._signature() !== this._original;

    const { unit } = this._config;
    const fmt = numberFormatter(this._hass);
    const { min, max, step } = this._limits();

    const groups = this._groups();
    this._card.header = this._title();
    let html = `<div class="content">
      <div class="name-row">${this._selectorHtml()}<input class="prog-name" type="text" maxlength="16"
        aria-label="${this._t("name_label")}" placeholder="${this._t("name_label")}"></div>`;

    groups.forEach((g, gi) => {
      const blocks = this._data.days[g.days[0]];
      const open = g.days.some((d) => this._expanded.has(d));

      const isNew = this._newGroup && g.days.length === 1 && g.days[0] === this._newGroup;
      html += `<div class="group${open ? " open" : ""}${isNew ? " new" : ""}" data-g="${gi}">
        <div class="group-header">
          <button class="day-toggle" data-g="${gi}" aria-expanded="${open}">
            <ha-icon class="chev" icon="mdi:chevron-right"></ha-icon>
            <span class="name">${this._label(g)}</span>
            <span class="summary">${this._summary(g)}</span>
          </button>
          ${clipboard ? `<span class="slot-paste" data-g="${gi}"></span>` : ""}
          <span class="slot-copy" data-g="${gi}"></span>
        </div>
        <div class="group-body"><div class="group-inner">`;
      if (this._config.group_days) {
        const [short, full] = [this._t("days_short"), this._t("days_full")];
        html += `<div class="chips" role="group" aria-label="${this._t("days_with_blocks")}">${DAYS.map((k, d) => {
          const on = g.days.includes(k);
          const only = on && g.days.length === 1;
          return `<button class="chip${on ? " on" : ""}" data-g="${gi}" data-d="${k}" aria-pressed="${on}"
            aria-label="${full[d]}"${only ? " disabled" : ""}>${short[d]}</button>`;
        }).join("")}</div>`;
      }

      blocks.forEach((b, bi) => {
        const isNewRow = this._newBlock && this._newBlock.day === g.days[0] && this._newBlock.from === b.from;
        html += `<div class="row${isNewRow ? " new" : ""}">
          <span class="slot-from" data-g="${gi}" data-b="${bi}"></span>
          <span class="to-text">${this._t("until")} ${b.to}</span>
          <span class="slot-slider" data-g="${gi}" data-b="${bi}"></span>
          <span class="val">${fmt(b.value)} ${unit}</span>
          <span class="slot-remove" data-g="${gi}" data-b="${bi}"></span>
        </div>`;
      });
      html += `<span class="slot-add" data-g="${gi}"></span></div></div></div>`;
    });

    html += `<div class="footer"><div class="errors-slot"></div><div class="save-bar-slot"></div></div>`;
    html += `</div>`;

    this._body.innerHTML = html;
    this._errorsHtml = undefined;

    this._bindSelector();
    const nameInput = this._body.querySelector(".prog-name");
    nameInput.value = this._data.name || "";
    nameInput.addEventListener("input", () => {
      this._data.name = nameInput.value;
      this._card.header = this._title();
      this._refreshState();
    });

    // Slider: HA's own element (ha-slider), so it looks and behaves exactly like
    // input_number rows. Falls back to a native range input if not registered yet.
    const native = !!customElements.get("ha-slider");
    this._body.querySelectorAll(".slot-slider").forEach((slot) => {
      const gi = +slot.dataset.g, bi = +slot.dataset.b;
      const block = this._data.days[groups[gi].days[0]][bi];
      let el;
      if (native) {
        el = document.createElement("ha-slider");
        el.setAttribute("labeled", "");
      } else {
        el = document.createElement("input");
        el.type = "range";
      }
      el.min = min; el.max = max; el.step = step; el.value = block.value;
      const read = (ev) => Number(ev.target.value ?? el.value);
      el.addEventListener("input", (ev) => {
        const v = el.closest(".row")?.querySelector(".val");
        if (v) v.textContent = `${fmt(read(ev))} ${unit}`;
      });
      el.addEventListener("change", (ev) =>
        this._change(groups[gi], bi, "value", read(ev))
      );
      slot.replaceWith(el);
    });
    const h12 = uses12h(this._hass);
    const labels = { hour: this._t("hour"), minutes: this._t("minutes") };
    this._body.querySelectorAll(".slot-from").forEach((slot) => {
      const gi = +slot.dataset.g, bi = +slot.dataset.b;
      const block = this._data.days[groups[gi].days[0]][bi];
      if (bi === 0) {
        // The first block of a day always starts at 00:00 (fixed).
        const locked = document.createElement("span");
        locked.className = "time locked";
        locked.textContent = "00:00";
        slot.replaceWith(locked);
        return;
      }
      slot.replaceWith(timeField(block.from, h12, labels, (v) => this._change(groups[gi], bi, "from", v)));
    });

    this._body.querySelectorAll(".slot-remove").forEach((slot) => {
      const gi = +slot.dataset.g, bi = +slot.dataset.b;
      if (this._data.days[groups[gi].days[0]].length <= 1) { slot.remove(); return; }
      const el = haIconButton("mdi:close", this._t("remove"));
      el.classList.add("remove");
      el.addEventListener("click", () => {
        const row = el.closest(".row");
        // Remove only after collapsing - and only if the card was not re-rendered
        // in the meantime, because the index would then refer to different data.
        collapse(row, () => { if (row.isConnected) this._remove(groups[gi], bi); });
      });
      slot.replaceWith(el);
    });

    this._body.querySelectorAll(".chip").forEach((el) => {
      el.addEventListener("click", () => this._toggleDay(groups[+el.dataset.g], el.dataset.d));
    });

    this._body.querySelectorAll(".day-toggle").forEach((el) => {
      el.addEventListener("click", () => {
        const gi = +el.dataset.g;
        const g = groups[gi];
        const open = g.days.some((d) => this._expanded.has(d));
        for (const d of g.days) {
          if (open) this._expanded.delete(d);
          else this._expanded.add(d);
        }
        // No full _render(): toggle the class on the existing DOM, so the CSS
        // transition has a start and end state to animate.
        const groupEl = this._body.querySelector(`.group[data-g="${gi}"]`);
        if (groupEl) groupEl.classList.toggle("open", !open);
        el.setAttribute("aria-expanded", String(!open));
      });
    });

    this._body.querySelectorAll(".slot-copy").forEach((slot) => {
      const gi = +slot.dataset.g;
      const isSource = this._isClipboardSource(groups[gi]);
      const el = haIconButton("mdi:content-copy", this._t("copy"));
      if (isSource) el.classList.add("active");
      el.addEventListener("click", () => this._copy(groups[gi]));
      slot.replaceWith(el);
    });
    this._body.querySelectorAll(".slot-paste").forEach((slot) => {
      const gi = +slot.dataset.g;
      const el = haIconButton("mdi:content-paste", this._t("paste"));
      el.addEventListener("click", () => this._paste(groups[gi]));
      slot.replaceWith(el);
    });

    this._body.querySelectorAll(".slot-add").forEach((slot) => {
      const gi = +slot.dataset.g;
      const el = haButton(this._t("add_block"), { icon: "mdi:plus" });
      el.addEventListener("click", () => this._add(groups[gi]));
      slot.replaceWith(el);
    });

    this._renderFooterAfterDraw();
    expand(this._body.querySelector(".row.new"));
    expand(this._body.querySelector(".group.new"));
    this._newBlock = null;
    this._newGroup = null;
  }
}

customElements.define("pockethome-program-card", PocketHomeProgramCard);
window.customCards = window.customCards || [];
const pickerTexts = TRANSLATIONS[pickLanguage(navigator.language)];
window.customCards.push({
  type: "pockethome-program-card",
  name: pickerTexts.card_name,
  description: pickerTexts.card_description,
});
console.info(`%c pockethome-program-card %c ${VERSION} (fork of heating-schedule-card) `, "background:#0C6675;color:#fff", "background:#444;color:#fff");
