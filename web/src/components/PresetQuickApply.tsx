import {
  BUILTIN_PRESETS,
  presetDisplayName,
  type NamedPreset,
} from "./PresetEditor";
import { t } from "../i18n";

export interface PresetQuickApplyProps {
  /** Called immediately when a built-in preset is chosen (no editor dialog). */
  onApply: (preset: NamedPreset) => void;
}

/** Compact built-in preset picker — reuses PresetEditor builtins + i18n names. */
export function PresetQuickApply({ onApply }: PresetQuickApplyProps) {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    if (!id) return;
    const preset = BUILTIN_PRESETS.find((p) => p.id === id);
    if (preset) onApply(preset);
    e.target.value = "";
  };

  return (
    <select
      aria-label={t("preset.quick_apply_aria")}
      title={t("preset.quick_apply_title")}
      defaultValue=""
      onChange={handleChange}
      className="max-w-[7.5rem] truncate px-2 py-1.5 rounded bg-fuchsia-500/15 hover:bg-fuchsia-500/25 text-fuchsia-300 text-xs font-medium transition-colors border border-fuchsia-500/30 focus:outline-none focus:border-fuchsia-400/60 appearance-none cursor-pointer"
    >
      <option value="">{t("preset.quick_apply")}</option>
      {BUILTIN_PRESETS.map((p) => (
        <option key={p.id} value={p.id}>
          {presetDisplayName(p.id, p.name)}
        </option>
      ))}
    </select>
  );
}
