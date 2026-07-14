/**
 * Thin i18n helper for desktop shell chrome (no heavy framework).
 * Default: en. Override with MELOSVIZ_LOCALE=es.
 */
import en from "../locales/en.json";
import es from "../locales/es.json";

export type Locale = "en" | "es";

const catalogs: Record<Locale, Record<string, string>> = { en, es };

function detectLocale(): Locale {
  const raw = (typeof process !== "undefined" ? process.env?.MELOSVIZ_LOCALE : undefined)
    ?.trim()
    .toLowerCase();
  if (raw?.startsWith("es")) return "es";
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

/** Interpolate `{name}` placeholders in a catalog string. */
export function tf(key: string, vars: Record<string, string | number>, fallback?: string): string {
  let text = t(key, fallback);
  for (const [name, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

export const supportedLocales: Locale[] = ["en", "es"];
