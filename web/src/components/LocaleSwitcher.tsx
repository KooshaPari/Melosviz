import { t, tf, supportedLocales, type Locale } from "../i18n";
import { useLocale } from "../i18n/LocaleProvider";

const LOCALE_LABELS: Record<Locale, string> = {
  en: "locale.en",
  es: "locale.es",
};

export function LocaleSwitcher() {
  const { locale, setLocale } = useLocale();

  return (
    <div
      className="flex items-center rounded-full border border-white/20 bg-white/5 p-0.5"
      role="group"
      aria-label={t("locale.label")}
    >
      {supportedLocales.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLocale(code)}
          aria-pressed={locale === code}
          aria-label={tf("locale.switch_aria", {
            lang: t(LOCALE_LABELS[code]),
          })}
          className={`min-w-[1.75rem] rounded-full px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide transition-colors ${
            locale === code
              ? "bg-white/15 text-white/90"
              : "text-white/40 hover:text-white/70"
          }`}
        >
          {code}
        </button>
      ))}
    </div>
  );
}
