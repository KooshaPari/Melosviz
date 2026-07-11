/**
 * Minimal i18n helper (no runtime dependency).
 * Default locale: en. Override with `MELOSVIZ_LOCALE` or `setLocale()`.
 */
import en from "./locales/en.json";
import es from "./locales/es.json";

export type Locale = "en" | "es";

const catalogs: Record<Locale, Record<string, string>> = { en, es };

let current: Locale = detectLocale();

function detectLocale(): Locale {
  if (typeof process !== "undefined" && process.env?.MELOSVIZ_LOCALE === "es") {
    return "es";
  }
  if (typeof navigator !== "undefined" && navigator.language?.startsWith("es")) {
    return "es";
  }
  return "en";
}

export function setLocale(locale: Locale): void {
  current = locale;
}

export function getLocale(): Locale {
  return current;
}

export function t(key: string, fallback?: string): string {
  return catalogs[current][key] ?? catalogs.en[key] ?? fallback ?? key;
}

export const supportedLocales: Locale[] = ["en", "es"];
