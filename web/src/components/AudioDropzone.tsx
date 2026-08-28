import { useCallback, useRef, useState, type DragEvent } from "react";
import { t, tf } from "../i18n";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import {
  clearRecentAudioFiles,
  formatRecentSize,
  loadRecentAudioFiles,
  pushRecentAudioFile,
  type RecentAudioEntry,
} from "../lib/recentAudioFiles";

interface AudioDropzoneProps {
  value: string;
  onChange: (path: string) => void;
  disabled?: boolean;
}

function basename(path: string): string {
  const parts = path.split(/[/\\]/);
  return parts[parts.length - 1] || path;
}

export function AudioDropzone({
  value,
  onChange,
  disabled = false,
}: AudioDropzoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingRecentRef = useRef<RecentAudioEntry | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [recent, setRecent] = useState<RecentAudioEntry[]>(() =>
    loadRecentAudioFiles(),
  );
  const reducedMotion = usePrefersReducedMotion();

  const remember = useCallback((entry: Omit<RecentAudioEntry, "lastUsed">) => {
    setRecent(pushRecentAudioFile(entry));
  }, []);

  const loadFile = useCallback(
    (file: File) => {
      const url = URL.createObjectURL(file);
      onChange(url);
      remember({ name: file.name, size: file.size, kind: "file" });
    },
    [onChange, remember],
  );

  const loadPath = useCallback(
    (path: string) => {
      const trimmed = path.trim();
      if (!trimmed) return;
      onChange(trimmed);
      remember({
        name: basename(trimmed),
        size: 0,
        kind: "path",
        path: trimmed,
      });
    },
    [onChange, remember],
  );

  const handleRecentClick = (entry: RecentAudioEntry) => {
    if (entry.kind === "path" && entry.path) {
      onChange(entry.path);
      remember(entry);
      return;
    }
    pendingRecentRef.current = entry;
    fileInputRef.current?.click();
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    pendingRecentRef.current = null;
    if (file) loadFile(file);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const file = e.dataTransfer.files?.[0];
    if (file) loadFile(file);
  };

  const dragHighlight = dragOver && !disabled;

  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs text-white/50 font-medium uppercase tracking-wider">
        {t("audio.label")}
      </label>

      <div
        role="group"
        aria-label={t("audio.dropzone_aria")}
        aria-disabled={disabled}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => {
          if (!disabled) fileInputRef.current?.click();
        }}
        className={`rounded-lg border border-dashed px-3 py-3 text-center cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50 ${
          dragHighlight
            ? "border-cyan-400/60 bg-cyan-500/10"
            : "border-white/15 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.05]"
        } ${disabled ? "opacity-50 pointer-events-none" : ""} ${
          reducedMotion ? "" : "transition-colors duration-200"
        }`}
      >
        <p className="text-xs text-white/60">{t("empty.drop_wav")}</p>
        <p className="mt-1 text-[10px] text-white/35">{t("empty.hint")}</p>
        <button
          type="button"
          tabIndex={-1}
          className="mt-2 text-[10px] font-medium text-cyan-300/80 hover:text-cyan-200 underline underline-offset-2"
          onClick={(e) => {
            e.stopPropagation();
            if (!disabled) fileInputRef.current?.click();
          }}
        >
          {t("audio.browse")}
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        className="hidden"
        disabled={disabled}
        onChange={handleFileInputChange}
      />

      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={(e) => loadPath(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") loadPath(value);
        }}
        disabled={disabled}
        placeholder={t("audio.path_placeholder")}
        aria-label={t("audio.path_aria")}
        className="px-2 py-1.5 rounded bg-white/5 border border-white/10 text-xs text-white/80 placeholder:text-white/30 focus:outline-none focus:border-cyan-500/50 disabled:opacity-50"
      />

      {recent.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-medium uppercase tracking-wider text-white/40">
              {t("audio.recent_title")}
            </span>
            <button
              type="button"
              disabled={disabled}
              onClick={() => setRecent(clearRecentAudioFiles())}
              aria-label={t("audio.recent_clear_aria")}
              className="text-[10px] font-medium text-white/35 hover:text-white/60 disabled:opacity-40"
            >
              {t("audio.recent_clear")}
            </button>
          </div>
          <ul
            className="flex flex-col gap-0.5 max-h-28 overflow-y-auto"
            aria-label={t("audio.recent_title")}
          >
            {recent.map((entry) => {
              const needsRepick = entry.kind === "file";
              const label = needsRepick
                ? tf("audio.recent_repick", { name: entry.name })
                : entry.name;
              return (
                <li
                  key={`${entry.kind}-${entry.name}-${entry.size}-${entry.lastUsed}`}
                >
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => handleRecentClick(entry)}
                    title={
                      needsRepick ? t("audio.recent_repick_hint") : entry.path
                    }
                    className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-[11px] text-white/60 hover:bg-white/10 hover:text-white/80 disabled:opacity-40"
                  >
                    <span className="truncate">{label}</span>
                    {entry.size > 0 && (
                      <span className="flex-shrink-0 text-white/30 tabular-nums">
                        {formatRecentSize(entry.size)}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
