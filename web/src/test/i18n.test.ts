import { describe, expect, it, beforeEach } from "vitest";
import en from "../i18n/locales/en.json";
import es from "../i18n/locales/es.json";
import { LOCALE_STORAGE_KEY, getLocale, setLocale, t, tf } from "../i18n";

/** Studio-polish prefixes (W-358–376) — parity guard beyond full-catalog diff. */
const STUDIO_POLISH_PREFIXES = [
  "playback.",
  "fullscreen.",
  "scene.",
  "keyboard.section.",
  "keyboard.label.",
  "preset.quick_apply",
  "audio.start",
  "audio.stop",
] as const;

function keysWithPrefix(
  catalog: Record<string, string>,
  prefix: string,
): string[] {
  return Object.keys(catalog)
    .filter((k) => k.startsWith(prefix))
    .sort();
}

describe("web i18n catalogs", () => {
  beforeEach(() => {
    localStorage.clear();
    setLocale("en");
  });

  it("en and es expose the same keys", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(es).sort());
  });

  it("studio polish prefixes have matching en/es keys", () => {
    for (const prefix of STUDIO_POLISH_PREFIXES) {
      const enKeys = keysWithPrefix(en, prefix);
      const esKeys = keysWithPrefix(es, prefix);
      expect(esKeys, `es missing keys for prefix ${prefix}`).toEqual(enKeys);
      expect(enKeys.length, `no keys under prefix ${prefix}`).toBeGreaterThan(
        0,
      );
    }
  });

  it("translates analyze action in Spanish", () => {
    setLocale("es");
    expect(t("action.analyze")).toBe("Analizar");
  });

  it("interpolates analysis server errors", () => {
    setLocale("en");
    expect(
      tf("error.analysis_server", {
        status: 500,
        statusText: "Internal Server Error",
      }),
    ).toBe("Server error: 500 Internal Server Error");
  });

  it("translates keyboard help title in Spanish", () => {
    setLocale("es");
    expect(t("keyboard.title")).toBe("Atajos de teclado");
  });

  it("translates preset editor chrome in Spanish", () => {
    setLocale("es");
    expect(t("preset.editor_title")).toBe("Editor de presets");
    expect(t("preset.builtin.energetic")).toBe("Enérgico");
  });

  it("interpolates preset duration label", () => {
    setLocale("en");
    expect(tf("preset.duration_bpm", { seconds: 180, bpm: 128 })).toBe(
      "180s · 128 BPM",
    );
  });

  it("interpolates spec summary and playback time readout", () => {
    setLocale("en");
    expect(tf("spec.summary", { seconds: 180, bpm: 128, keyframes: 3 })).toBe(
      "180s · 128 BPM · 3 keyframes",
    );
    expect(tf("playback.time", { elapsed: "1:00", total: "3:00" })).toBe(
      "1:00 / 3:00",
    );
    expect(tf("a11y.analysis_progress_pct", { pct: 42 })).toContain("42");
  });

  it("translates bridge unreachable hint in Spanish", () => {
    setLocale("es");
    expect(t("error.bridge_unreachable")).toContain("puente");
    expect(t("onboarding.welcome_title")).toContain("Carga audio");
  });

  it("interpolates memory-cap hard error", () => {
    setLocale("en");
    expect(tf("error.memory_cap_hard", { rssMb: 200, capMb: 100 })).toContain(
      "200",
    );
    expect(tf("error.memory_cap_hard", { rssMb: 200, capMb: 100 })).toContain(
      "100",
    );
  });

  it("translates download spec action in Spanish", () => {
    setLocale("es");
    expect(t("action.download_spec")).toBe("Descargar JSON");
  });

  it("falls back to English for unknown keys", () => {
    setLocale("es");
    expect(t("nonexistent.key", "fallback")).toBe("fallback");
  });

  it("persists locale to localStorage on setLocale", () => {
    setLocale("es");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("es");
    expect(getLocale()).toBe("es");
  });

  it("translates locale switcher strings in Spanish", () => {
    setLocale("es");
    expect(t("locale.label")).toBe("Idioma");
    expect(tf("locale.switch_aria", { lang: t("locale.es") })).toContain(
      "Español",
    );
  });

  it("translates analysis progress a11y hint in Spanish", () => {
    setLocale("es");
    expect(t("a11y.analysis_progress")).toContain("Escape");
  });

  it("translates skip link in Spanish", () => {
    setLocale("es");
    expect(t("a11y.skip_link")).toBe("Saltar al contenido principal");
  });

  it("translates theme high-contrast strings in Spanish", () => {
    setLocale("es");
    expect(t("theme.high_contrast")).toBe("Alto contraste");
    expect(t("theme.high_contrast_enable_aria")).toContain("alto contraste");
  });

  it("translates live-audio adapter button in Spanish", () => {
    setLocale("es");
    expect(t("audio.start")).toBe("Iniciar audio");
    expect(t("audio.stop")).toBe("Detener audio");
  });
});
