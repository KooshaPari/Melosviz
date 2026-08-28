import { useEffect, useRef, useCallback } from "react";
import WaveSurfer from "wavesurfer.js";

interface WaveformDisplayProps {
  /** Absolute or relative path / URL to the audio file. */
  audioSrc: string;
  /** Normalised playback position [0, 1]. */
  playbackT: number;
  className?: string;
}

/**
 * Renders a waveform for `audioSrc` using WaveSurfer.js and keeps the
 * playback cursor in sync with the `playbackT` prop (0-1 normalised).
 *
 * Visual styling uses brand CSS vars from styles/brand.css.
 */
export function WaveformDisplay({
  audioSrc,
  playbackT,
  className = "",
}: WaveformDisplayProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const seekingRef = useRef(false);

  // Create / destroy WaveSurfer instance when audioSrc changes.
  useEffect(() => {
    if (!containerRef.current) return;

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: "var(--mv-primary)",
      progressColor: "var(--mv-secondary)",
      cursorColor: "var(--mv-secondary)",
      cursorWidth: 2,
      height: 64,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      interact: false, // cursor is driven externally via playbackT
      backend: "WebAudio",
    });

    wavesurferRef.current = ws;

    ws.load(audioSrc).catch(() => {
      // Audio may not be fetchable in all environments (e.g. tests); ignore.
    });

    return () => {
      seekingRef.current = false;
      ws.destroy();
      wavesurferRef.current = null;
    };
  }, [audioSrc]);

  // Sync cursor when playbackT changes.
  const syncCursor = useCallback((t: number) => {
    const ws = wavesurferRef.current;
    if (!ws) return;
    // seekTo expects a value in [0, 1]; guard against edge values.
    const clamped = Math.max(0, Math.min(1, t));
    try {
      ws.seekTo(clamped);
    } catch {
      // WaveSurfer throws if not ready; silently ignore.
    }
  }, []);

  useEffect(() => {
    syncCursor(playbackT);
  }, [playbackT, syncCursor]);

  return (
    <div
      className={`rounded-lg overflow-hidden border border-white/10 bg-[var(--mv-surface)] px-2 pt-2 pb-1 ${className}`}
      data-testid="waveform-display"
    >
      <div ref={containerRef} style={{ minHeight: 64 }} />
      <div className="flex justify-between px-0.5 mt-0.5">
        <span className="text-[10px] text-white/30 font-mono">0:00</span>
        <span className="text-[10px] text-white/50 font-mono">
          {Math.round(playbackT * 100)}%
        </span>
      </div>
    </div>
  );
}
