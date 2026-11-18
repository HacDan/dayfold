/* Dashboard i18n. Portuguese is the source language: the key IS the Portuguese text and
   `en` maps it to English. Missing keys fall back to Portuguese. Variables use {name}. */
import { en } from "./i18n.en";

export type Lang = "pt" | "en";
const KEY = "dayfold.lang";

function initial(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "pt" || saved === "en") return saved;
  } catch { /* storage unavailable */ }
  return "en";
}

let current: Lang = initial();
document.documentElement.lang = current === "pt" ? "pt-BR" : "en";

export const getLang = () => current;
export const locale = () => (current === "pt" ? "pt-BR" : "en-US");

/** Did the operator ever pick a language? Without a choice the dashboard follows the server. */
export function hasSavedLang(): boolean {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "pt" || saved === "en";
  } catch { return false; }
}

/** ``persist: false`` applies a language without remembering it, so a later change to the
    server's language still shows up for someone who never picked one. */
export function setLang(lang: Lang, persist = true) {
  current = lang;
  document.documentElement.lang = lang === "pt" ? "pt-BR" : "en";
  if (!persist) return;
  try { localStorage.setItem(KEY, lang); } catch { /* ignore */ }
}

export function t(text: string, vars?: Record<string, string | number>): string {
  let out = current === "en" ? en[text] ?? text : text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

/** Named labels for the generation triggers: the daily schedule and the startup catch-up. A manual
    run, or a trigger new enough not to have a label, keeps its own name. */
const TRIGGER_LABEL: Record<string, string> = { schedule: "agendada", "catch-up": "recuperação" };

export const triggerLabel = (trigger: string) => t(TRIGGER_LABEL[trigger] ?? trigger);
