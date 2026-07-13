/**
 * Thin i18n helper for desktop webview shell chrome.
 * Mirrors desktop/src/i18n.ts; catalogs live under desktop/locales/.
 */
import en from "../../locales/en.json";
import es from "../../locales/es.json";

export type Locale = "en" | "es";

const catalogs: Record<Locale, Record<string, string>> = { en, es };

function detectLocale(): Locale {
  // Bun/Electrobun may expose process.env; navigator is a fallback in the webview.
  const env =
    typeof process !== "undefined" ? process.env?.MELOSVIZ_LOCALE : undefined;
  const raw = env?.trim().toLowerCase();
  if (raw?.startsWith("es")) return "es";
  if (typeof navigator !== "undefined" && navigator.language?.startsWith("es")) {
    return "es";
  }
  return "en";
}

let current: Locale = detectLocale();

export function setLocale(locale: Locale): void {
  current = locale;
}

export function getLocale(): Locale {
  return current;
}

export function t(key: string, fallback?: string): string {
  return catalogs[current][key] ?? catalogs.en[key] ?? fallback ?? key;
}

/** Apply a couple of shell chrome strings from the active catalog. */
export function applyShellChrome(): void {
  const name = document.getElementById("titlebar-name");
  if (name) name.textContent = t("app.name");
  const tag = document.getElementById("titlebar-tag");
  if (tag) tag.textContent = t("shell.tagline");
  const skip = document.querySelector<HTMLAnchorElement>("a.skip-link");
  if (skip) skip.textContent = t("shell.skip_link");
  document.title = t("app.name");
  document.documentElement.lang = current;
}
