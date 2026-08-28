/**
 * Minimal i18n helper (no runtime dependency).
 * Default locale: en. Override with stored preference, `MELOSVIZ_LOCALE`, or `setLocale()`.
 */
import en from "./locales/en.json";
import es from "./locales/es.json";

export type Locale = "en" | "es";

export const LOCALE_STORAGE_KEY = "melosviz-locale";

const catalogs: Record<Locale, Record<string, string>> = { en, es };

let current: Locale = detectLocale();

function detectLocale(): Locale {
  if (typeof window !== "undefined") {
    try {
      const stored = window.localStorage?.getItem(LOCALE_STORAGE_KEY);
      if (stored === "en" || stored === "es") return stored;
    } catch {
      /* localStorage may throw under sandboxed test runners — fall through */
    }
  }
  if (typeof process !== "undefined" && process.env?.MELOSVIZ_LOCALE === "es") {
    return "es";
  }
  if (
    typeof navigator !== "undefined" &&
    navigator.language?.startsWith("es")
  ) {
    return "es";
  }
  return "en";
}

export function setLocale(locale: Locale): void {
  current = locale;
  if (typeof window !== "undefined") {
    try {
      window.localStorage?.setItem(LOCALE_STORAGE_KEY, locale);
    } catch {
      /* sandboxed environments: ignore */
    }
  }
}

export function getLocale(): Locale {
  return current;
}

export function t(key: string, fallback?: string): string {
  return catalogs[current][key] ?? catalogs.en[key] ?? fallback ?? key;
}

/** Interpolate `{name}` placeholders in a catalog string. */
export function tf(
  key: string,
  vars: Record<string, string | number>,
  fallback?: string,
): string {
  let text = t(key, fallback);
  for (const [name, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

export const supportedLocales: Locale[] = ["en", "es"];
