import { useCallback, useState } from "react";
import type { RenderSpec } from "../renderSpec";
import { t, tf } from "../i18n";
import { Toast } from "./Toast";

interface SpecViewerProps {
  spec: RenderSpec;
}

export function renderSpecJson(spec: RenderSpec): string {
  return JSON.stringify(spec, null, 2);
}

export function downloadRenderSpec(spec: RenderSpec, filename?: string): void {
  const blob = new Blob([renderSpecJson(spec)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename ?? `melosviz-renderspec-${Date.now()}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function copyRenderSpecToClipboard(
  spec: RenderSpec,
): Promise<void> {
  await navigator.clipboard.writeText(renderSpecJson(spec));
}

export function SpecViewer({ spec }: SpecViewerProps) {
  const [copied, setCopied] = useState(false);
  const summaryLine = tf("spec.summary", {
    seconds: spec.durationSecs,
    bpm: spec.bpm ?? "—",
    keyframes: spec.keyframes.length,
  });

  const handleDownload = useCallback(() => {
    downloadRenderSpec(spec);
  }, [spec]);

  const handleCopy = useCallback(async () => {
    await copyRenderSpecToClipboard(spec);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }, [spec]);

  return (
    <div className="mt-3 rounded-lg bg-white/5 border border-white/10 p-3">
      <Toast message={t("spec.copied_toast")} visible={copied} />
      <div className="flex items-center justify-between gap-2 mb-2">
        <p className="text-xs text-white/50 font-medium uppercase tracking-wider">
          {t("spec.title")}
        </p>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              void handleCopy();
            }}
            className="text-[10px] font-medium text-cyan-300/90 hover:text-cyan-200 border border-cyan-500/30 hover:border-cyan-500/50 rounded px-2 py-0.5 transition-colors"
            aria-label={t("spec.copy_aria")}
          >
            {t("action.copy_spec")}
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="text-[10px] font-medium text-cyan-300/90 hover:text-cyan-200 border border-cyan-500/30 hover:border-cyan-500/50 rounded px-2 py-0.5 transition-colors"
            aria-label={t("spec.download_aria")}
          >
            {t("action.download_spec")}
          </button>
        </div>
      </div>
      <p
        className="text-xs text-cyan-300 font-mono leading-relaxed"
        data-testid="spec-summary"
      >
        {summaryLine}
      </p>
    </div>
  );
}
