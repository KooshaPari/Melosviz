import { useState, useCallback, useRef, useEffect } from "react";
import type { RenderSpec } from "../renderSpec";

export interface PlaylistItem {
  id: string;
  file: File;
  status: "pending" | "analyzing" | "done" | "error";
  spec?: RenderSpec;
  errorMsg?: string;
  /** Duration in seconds if known from the spec */
  durationSecs?: number;
}

interface PlaylistState {
  queue: PlaylistItem[];
  currentIndex: number;
  isProcessing: boolean;
}

let _nextId = 1;
function nextId(): string {
  return `pl-${_nextId++}`;
}

export interface UsePlaylistReturn {
  queue: PlaylistItem[];
  currentIndex: number;
  isProcessing: boolean;
  addFiles: (files: File[]) => void;
  removeItem: (id: string) => void;
  reorder: (fromIdx: number, toIdx: number) => void;
  clearQueue: () => void;
  setCurrentIndex: (index: number) => void;
  /** Active item (currently selected for viewing) */
  activeItem: PlaylistItem | null;
}

/**
 * Manages a queue of audio files for sequential analysis.
 * Automatically advances to the next pending item when the current one finishes.
 */
export function usePlaylist(
  /** Async function that analyzes a file path/URL and returns a RenderSpec */
  analyzeFile: (audioPath: string) => Promise<RenderSpec>,
): UsePlaylistReturn {
  const [state, setState] = useState<PlaylistState>({
    queue: [],
    currentIndex: -1,
    isProcessing: false,
  });

  // Keep a ref so the effect closure always sees fresh state
  const stateRef = useRef(state);
  stateRef.current = state;

  const addFiles = useCallback((files: File[]) => {
    if (files.length === 0) return;
    setState((prev) => {
      const newItems: PlaylistItem[] = files.map((f) => ({
        id: nextId(),
        file: f,
        status: "pending" as const,
      }));
      const wasEmpty = prev.queue.length === 0;
      return {
        ...prev,
        queue: [...prev.queue, ...newItems],
        currentIndex: wasEmpty ? 0 : prev.currentIndex,
      };
    });
  }, []);

  const removeItem = useCallback((id: string) => {
    setState((prev) => {
      const idx = prev.queue.findIndex((i) => i.id === id);
      if (idx === -1) return prev;
      const newQueue = prev.queue.filter((i) => i.id !== id);
      let newCurrent = prev.currentIndex;
      if (newQueue.length === 0) {
        newCurrent = -1;
      } else if (idx < prev.currentIndex) {
        newCurrent = prev.currentIndex - 1;
      } else if (idx === prev.currentIndex) {
        newCurrent = Math.min(prev.currentIndex, newQueue.length - 1);
      }
      return { ...prev, queue: newQueue, currentIndex: newCurrent };
    });
  }, []);

  const reorder = useCallback((fromIdx: number, toIdx: number) => {
    setState((prev) => {
      if (
        fromIdx < 0 ||
        toIdx < 0 ||
        fromIdx >= prev.queue.length ||
        toIdx >= prev.queue.length ||
        fromIdx === toIdx
      ) {
        return prev;
      }
      const newQueue = [...prev.queue];
      const [moved] = newQueue.splice(fromIdx, 1);
      newQueue.splice(toIdx, 0, moved!);
      // Track current index through the reorder
      let newCurrent = prev.currentIndex;
      if (prev.currentIndex === fromIdx) {
        newCurrent = toIdx;
      } else if (fromIdx < prev.currentIndex && toIdx >= prev.currentIndex) {
        newCurrent = prev.currentIndex - 1;
      } else if (fromIdx > prev.currentIndex && toIdx <= prev.currentIndex) {
        newCurrent = prev.currentIndex + 1;
      }
      return { ...prev, queue: newQueue, currentIndex: newCurrent };
    });
  }, []);

  const clearQueue = useCallback(() => {
    setState({ queue: [], currentIndex: -1, isProcessing: false });
  }, []);

  const setCurrentIndex = useCallback((index: number) => {
    setState((prev) => {
      if (index < -1 || index >= prev.queue.length) return prev;
      return { ...prev, currentIndex: index };
    });
  }, []);

  // Auto-process: when a pending item is at currentIndex, analyze it.
  // When done, advance to next pending item.
  useEffect(() => {
    const { queue, currentIndex, isProcessing } = stateRef.current;
    if (isProcessing) return;
    if (currentIndex < 0 || currentIndex >= queue.length) return;

    const item = queue[currentIndex];
    if (!item || item.status !== "pending") return;

    // Mark as analyzing
    setState((prev) => {
      const newQueue = prev.queue.map((qi) =>
        qi.id === item.id ? { ...qi, status: "analyzing" as const } : qi,
      );
      return { ...prev, queue: newQueue, isProcessing: true };
    });

    // Use object URL as the audio path for the analyzer
    const objectUrl = URL.createObjectURL(item.file);

    analyzeFile(objectUrl)
      .then((spec) => {
        URL.revokeObjectURL(objectUrl);
        setState((prev) => {
          const newQueue = prev.queue.map((qi) =>
            qi.id === item.id
              ? {
                  ...qi,
                  status: "done" as const,
                  spec,
                  durationSecs: spec.durationSecs,
                }
              : qi,
          );
          // Advance to next pending item
          const nextPendingIdx = newQueue.findIndex(
            (qi, i) => i > prev.currentIndex && qi.status === "pending",
          );
          return {
            ...prev,
            queue: newQueue,
            isProcessing: false,
            currentIndex:
              nextPendingIdx !== -1 ? nextPendingIdx : prev.currentIndex,
          };
        });
      })
      .catch((err: unknown) => {
        URL.revokeObjectURL(objectUrl);
        const errorMsg = err instanceof Error ? err.message : "Unknown error";
        setState((prev) => {
          const newQueue = prev.queue.map((qi) =>
            qi.id === item.id
              ? { ...qi, status: "error" as const, errorMsg }
              : qi,
          );
          const nextPendingIdx = newQueue.findIndex(
            (qi, i) => i > prev.currentIndex && qi.status === "pending",
          );
          return {
            ...prev,
            queue: newQueue,
            isProcessing: false,
            currentIndex:
              nextPendingIdx !== -1 ? nextPendingIdx : prev.currentIndex,
          };
        });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.currentIndex, state.isProcessing, state.queue]);

  const activeItem =
    state.currentIndex >= 0 && state.currentIndex < state.queue.length
      ? (state.queue[state.currentIndex] ?? null)
      : null;

  return {
    queue: state.queue,
    currentIndex: state.currentIndex,
    isProcessing: state.isProcessing,
    addFiles,
    removeItem,
    reorder,
    clearQueue,
    setCurrentIndex,
    activeItem,
  };
}
