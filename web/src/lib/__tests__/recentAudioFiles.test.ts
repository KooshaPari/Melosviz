import { describe, it, expect, beforeEach } from "vitest";
import {
  RECENT_AUDIO_STORAGE_KEY,
  loadRecentAudioFiles,
  pushRecentAudioFile,
  clearRecentAudioFiles,
  formatRecentSize,
} from "../recentAudioFiles";

describe("recentAudioFiles", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns empty list when storage is empty", () => {
    expect(loadRecentAudioFiles()).toEqual([]);
  });

  it("persists path entries with name and lastUsed", () => {
    const list = pushRecentAudioFile({
      name: "track.mp3",
      size: 0,
      kind: "path",
      path: "/music/track.mp3",
    });
    expect(list).toHaveLength(1);
    expect(list[0]?.name).toBe("track.mp3");
    expect(list[0]?.kind).toBe("path");
    expect(list[0]?.path).toBe("/music/track.mp3");
    expect(
      JSON.parse(localStorage.getItem(RECENT_AUDIO_STORAGE_KEY) ?? "[]"),
    ).toHaveLength(1);
  });

  it("does not persist blob URLs for file entries", () => {
    pushRecentAudioFile({
      name: "clip.wav",
      size: 4096,
      kind: "file",
      path: "blob:http://localhost/abc",
    });
    const raw = JSON.parse(
      localStorage.getItem(RECENT_AUDIO_STORAGE_KEY) ?? "[]",
    ) as Array<{
      path?: string;
    }>;
    expect(raw[0]?.path).toBeUndefined();
  });

  it("bumps existing entry to top on re-use", () => {
    pushRecentAudioFile({ name: "a.mp3", size: 100, kind: "file" });
    pushRecentAudioFile({ name: "b.mp3", size: 200, kind: "file" });
    const list = pushRecentAudioFile({
      name: "a.mp3",
      size: 100,
      kind: "file",
    });
    expect(list[0]?.name).toBe("a.mp3");
    expect(list[1]?.name).toBe("b.mp3");
  });

  it("formats byte sizes for display", () => {
    expect(formatRecentSize(0)).toBe("");
    expect(formatRecentSize(512)).toBe("512 B");
    expect(formatRecentSize(2048)).toBe("2.0 KB");
  });

  it("clears persisted recent entries", () => {
    pushRecentAudioFile({ name: "a.mp3", size: 100, kind: "file" });
    expect(clearRecentAudioFiles()).toEqual([]);
    expect(localStorage.getItem(RECENT_AUDIO_STORAGE_KEY)).toBeNull();
    expect(loadRecentAudioFiles()).toEqual([]);
  });
});
