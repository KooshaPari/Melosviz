import { t, tf } from "../i18n";
import type { RenderSpec } from "../renderSpec";

export interface SceneJumpPanelProps {
  spec: RenderSpec;
  onJumpToKeyframe: (t: number) => void;
  /** Optional className for placement. */
  className?: string;
}

/**
 * Compact scene-jump panel — surfaces a button per keyframe so the user can
 * seek directly to a named scene. Built from the typed RenderSpec.
 */
export function SceneJumpPanel({
  spec,
  onJumpToKeyframe,
  className,
}: SceneJumpPanelProps) {
  const scenes = (spec.keyframes ?? []).map((kf, i) => ({
    t: kf.t,
    name: kf.scene ?? kf.scene_template ?? tf("scene.beat_fallback", { n: i + 1 }),
    i,
  }));

  if (scenes.length === 0) {
    return null;
  }

  return (
    <nav
      aria-label={t("scene.panel_aria")}
      className={`flex flex-col gap-2 rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-xs text-white/80 ${className ?? ""}`}
    >
      <div className="uppercase tracking-wider text-white/50 text-[10px]">
        {t("scene.panel_label")}
      </div>
      <div className="flex flex-col gap-1">
        {scenes.map((s) => (
          <button
            key={s.i}
            type="button"
            onClick={() => onJumpToKeyframe(s.t)}
            aria-label={tf("scene.jump_aria", { name: s.name })}
            className="rounded border border-white/10 bg-white/5 px-2 py-1 text-left hover:bg-white/10 hover:border-white/20 transition-colors"
          >
            {s.name}
          </button>
        ))}
      </div>
    </nav>
  );
}
