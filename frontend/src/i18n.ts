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

export function setLang(lang: Lang) {
  current = lang;
  document.documentElement.lang = lang === "pt" ? "pt-BR" : "en";
  try { localStorage.setItem(KEY, lang); } catch { /* ignore */ }
}

export function t(text: string, vars?: Record<string, string | number>): string {
  let out = current === "en" ? en[text] ?? text : text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}
