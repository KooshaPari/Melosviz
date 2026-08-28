// Screen-reader text mirror for the R3F canvas (W-329).
//
// Siblings the WebGL canvas: the parent role=img wrapper keeps a short label;
// this component exposes a richer deterministic description + polite live updates.

import { useEffect, useRef } from "react";
import type { SceneSummary } from "../utils/sceneSummary";

export interface SceneSummaryAnnouncerProps {
  summary: SceneSummary;
  /** id referenced by the canvas wrapper aria-describedby. */
  detailId: string;
  /** When true, push liveAnnouncement into the polite live region. */
  announce?: boolean;
}

export function SceneSummaryAnnouncer({
  summary,
  detailId,
  announce = true,
}: SceneSummaryAnnouncerProps) {
  const liveRef = useRef<HTMLSpanElement>(null);
  const prevLiveKey = useRef<string | null>(null);

  useEffect(() => {
    if (!announce || !liveRef.current) return;
    if (prevLiveKey.current === summary.liveKey) return;
    prevLiveKey.current = summary.liveKey;
    liveRef.current.textContent = summary.liveAnnouncement;
  }, [announce, summary.liveAnnouncement, summary.liveKey]);

  return (
    <>
      <p id={detailId} className="sr-only" data-testid="scene-summary-detail">
        {summary.detailText}
      </p>
      <span
        ref={liveRef}
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
        data-testid="scene-summary-live"
      />
    </>
  );
}
