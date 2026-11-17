/* FORK of heating-schedule-card (c) 2026 Jakub Jurczyk, MIT (LICENSE-heating-schedule-card). Modified for PocketHome, see NOTICE.md. */
import en from "./translations/en.js";
import fr from "./translations/fr.js";
import de from "./translations/de.js";
import cs from "./translations/cs.js";

/* UI texts, one JS module per language. {name} placeholders are filled by
   format(); a key missing in a language falls back to English. */
export const TRANSLATIONS = { en, fr, de, cs };

/* "fr-FR" -> "fr"; languages without translations -> "en". */
export function pickLanguage(language) {
  const base = String(language || "").toLowerCase().split("-")[0];
  return TRANSLATIONS[base] ? base : "en";
}
export const format = (text, params = {}) => text.replace(/\{(\w+)\}/g, (m, k) => params[k] ?? m);
