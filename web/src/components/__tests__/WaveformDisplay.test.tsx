/**
 * Tests for WaveformDisplay.
 *
 * WaveSurfer is fully mocked so these tests run without a real DOM canvas /
 * AudioContext. They verify the component contract only.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// ------ Mock wavesurfer.js ------------------------------------------------
const mockSeekTo = vi.fn();
const mockLoad = vi.fn().mockResolvedValue(undefined);
const mockDestroy = vi.fn();

vi.mock("wavesurfer.js", () => ({
  default: {
    create: vi.fn(() => ({
      load: mockLoad,
      seekTo: mockSeekTo,
      destroy: mockDestroy,
    })),
  },
}));
// -------------------------------------------------------------------------

import { WaveformDisplay } from "../WaveformDisplay";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("WaveformDisplay", () => {
  it("renders without crashing when audioSrc and playbackT are provided", () => {
    render(<WaveformDisplay audioSrc="/audio/track.mp3" playbackT={0} />);
    expect(screen.getByTestId("waveform-display")).toBeInTheDocument();
  });

  it("shows the playback percentage derived from playbackT", () => {
    render(<WaveformDisplay audioSrc="/audio/track.mp3" playbackT={0.42} />);
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("calls seekTo with clamped playbackT when the prop changes", async () => {
    const { rerender } = render(
      <WaveformDisplay audioSrc="/audio/track.mp3" playbackT={0} />,
    );
    await act(async () => {
      rerender(
        <WaveformDisplay audioSrc="/audio/track.mp3" playbackT={0.75} />,
      );
    });
    expect(mockSeekTo).toHaveBeenCalledWith(0.75);
  });

  it("handles null / missing audio gracefully (empty src still mounts)", () => {
    // An empty string src should still render the container without throwing.
    expect(() =>
      render(<WaveformDisplay audioSrc="" playbackT={0} />),
    ).not.toThrow();
    expect(screen.getByTestId("waveform-display")).toBeInTheDocument();
  });

  it("clamps playbackT values outside [0, 1] before calling seekTo", async () => {
    const { rerender } = render(
      <WaveformDisplay audioSrc="/audio/track.mp3" playbackT={0} />,
    );
    await act(async () => {
      rerender(<WaveformDisplay audioSrc="/audio/track.mp3" playbackT={1.5} />);
    });
    expect(mockSeekTo).toHaveBeenCalledWith(1);
  });
});
