/**
 * Thin i18n helper for desktop webview shell chrome.
 * Mirrors desktop/src/i18n.ts; catalogs live under desktop/locales/.
 */
import en from "../../locales/en.json";
import es from "../../locales/es.json";

export type Locale = "en" | "es";

const catalogs: Record<Locale, Record<string, string>> = { en, es };

function detectLocale(): Locale {
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

export function tf(key: string, vars: Record<string, string | number>, fallback?: string): string {
  let text = t(key, fallback);
  for (const [name, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

function setText(sel: string, key: string): void {
  const el = document.querySelector(sel);
  if (el) el.textContent = t(key);
}

function setPipelineBtn(btnId: string, labelKey: string, subKey: string): void {
  const label = document.querySelector(`#${btnId} .pipeline-btn-label`);
  const sub = document.querySelector(`#${btnId} .pipeline-btn-sub`);
  if (label) label.textContent = t(labelKey);
  if (sub) sub.textContent = t(subKey);
}

/** Apply shell chrome strings from the active catalog. */
export function applyShellChrome(): void {
  setText("#titlebar-name", "app.name");
  setText("#titlebar-tag", "shell.tagline");
  const skip = document.querySelector<HTMLAnchorElement>("a.skip-link");
  if (skip) skip.textContent = t("shell.skip_link");
  document.title = t("app.name");
  document.documentElement.lang = current;

  // Sidebar cards
  const cardTitles = document.querySelectorAll<HTMLElement>(".card-header .card-title");
  const cardKeys = [
    "shell.card.source",
    "shell.card.output",
    "shell.card.pipeline",
    "shell.card.progress",
    "shell.card.error",
  ];
  cardTitles.forEach((el, i) => {
    if (cardKeys[i]) el.textContent = t(cardKeys[i]);
  });

  const dzP = document.querySelector("#dropzone p");
  if (dzP) dzP.textContent = t("shell.dropzone");

  const outPath = document.querySelector("#out-path");
  if (outPath?.textContent?.includes("MelosViz-output")) {
    outPath.textContent = t("shell.output.default");
  }

  setText("#btn-change-wav", "shell.btn.change_file");
  setText("#btn-pick-out", "shell.btn.choose_folder");
  setPipelineBtn("btn-analyze", "shell.btn.analyze", "shell.btn.analyze.sub");
  setPipelineBtn("btn-build", "shell.btn.build", "shell.btn.build.sub");
  setPipelineBtn("btn-render", "shell.btn.render", "shell.btn.render.sub");
  setText("#btn-dismiss-error", "shell.btn.dismiss");

  const copyBtns = ["btn-copy-spec", "btn-copy-plan"];
  for (const id of copyBtns) {
    const btn = document.getElementById(id);
    if (btn) btn.textContent = t("shell.btn.copy_json");
  }

  // Welcome empty state
  const welcomeTitle = document.querySelector(".empty-state-title");
  if (welcomeTitle) welcomeTitle.textContent = t("shell.empty.welcome_title");
  const welcomeDesc = document.querySelector(".empty-state-desc");
  if (welcomeDesc) welcomeDesc.textContent = t("shell.empty.welcome_desc");
  const stepLabels = document.querySelectorAll<HTMLElement>(".empty-step-label");
  const stepKeys = [
    "shell.empty.step.load",
    "shell.empty.step.analyze",
    "shell.empty.step.plan",
    "shell.empty.step.render",
  ];
  stepLabels.forEach((el, i) => {
    if (stepKeys[i]) el.textContent = t(stepKeys[i]);
  });

  // Tabs
  const tabKeys: Record<string, string> = {
    spec: "shell.tab.spec",
    timeline: "shell.tab.timeline",
    plan: "shell.tab.plan",
    video: "shell.tab.video",
  };
  document.querySelectorAll<HTMLButtonElement>(".tab-btn").forEach((btn) => {
    const tab = btn.dataset.tab;
    if (!tab || !tabKeys[tab]) return;
    const pip = btn.querySelector(".tab-pip");
    btn.textContent = "";
    if (pip) btn.appendChild(pip);
    btn.append(document.createTextNode(t(tabKeys[tab])));
  });
}
