import { describe, it, expect, beforeEach } from "vitest";
import {
  PLAYBACK_LOOP_STORAGE_KEY,
  loadPlaybackLoop,
  savePlaybackLoop,
} from "../playbackLoop";

describe("playbackLoop", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns false when storage is empty", () => {
    expect(loadPlaybackLoop()).toBe(false);
  });

  it("persists loop enabled to localStorage", () => {
    expect(savePlaybackLoop(true)).toBe(true);
    expect(localStorage.getItem(PLAYBACK_LOOP_STORAGE_KEY)).toBe("1");
    expect(loadPlaybackLoop()).toBe(true);
  });

  it("persists loop disabled to localStorage", () => {
    savePlaybackLoop(true);
    expect(savePlaybackLoop(false)).toBe(false);
    expect(localStorage.getItem(PLAYBACK_LOOP_STORAGE_KEY)).toBe("0");
    expect(loadPlaybackLoop()).toBe(false);
  });
});
