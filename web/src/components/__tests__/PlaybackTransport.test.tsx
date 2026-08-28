import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PlaybackTransport } from "../PlaybackTransport";
import { setLocale } from "../../i18n";

const baseProps = {
  playbackT: 0.5,
  autoPlay: false,
  durationSecs: 120,
  currentSceneLabel: "Performance",
  isListening: false,
  bpm: 128,
  onTogglePlay: vi.fn(),
  onSeek: vi.fn(),
  onReset: vi.fn(),
};

describe("PlaybackTransport", () => {
  it("exposes i18n aria-labels and visible time readout", () => {
    setLocale("en");
    render(<PlaybackTransport {...baseProps} />);

    expect(
      screen.getByRole("button", { name: /start playback/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("slider", { name: /seek playback position/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reset playback to start/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("1:00 / 2:00")).toBeInTheDocument();
    expect(screen.getByText("128 BPM · Three.js / R3F")).toBeInTheDocument();
  });

  it("shows pause aria-label when autoPlay is on", () => {
    setLocale("en");
    render(<PlaybackTransport {...baseProps} autoPlay />);
    expect(
      screen.getByRole("button", { name: /pause playback/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Playing")).toBeInTheDocument();
  });

  it("calls transport handlers", () => {
    const onTogglePlay = vi.fn();
    const onSeek = vi.fn();
    const onReset = vi.fn();
    render(
      <PlaybackTransport
        {...baseProps}
        onTogglePlay={onTogglePlay}
        onSeek={onSeek}
        onReset={onReset}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /start playback/i }));
    fireEvent.change(screen.getByRole("slider"), { target: { value: "25" } });
    fireEvent.click(
      screen.getByRole("button", { name: /reset playback to start/i }),
    );

    expect(onTogglePlay).toHaveBeenCalledTimes(1);
    expect(onSeek).toHaveBeenCalledWith(0.25);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("localizes controls in Spanish", () => {
    setLocale("es");
    render(<PlaybackTransport {...baseProps} />);
    expect(
      screen.getByRole("button", { name: /iniciar reproducción/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Inactivo")).toBeInTheDocument();
  });

  it("shows keyboard seek hint chips", () => {
    setLocale("en");
    render(<PlaybackTransport {...baseProps} />);
    expect(screen.getByText("−5 s")).toBeInTheDocument();
    expect(screen.getByText("+5 s")).toBeInTheDocument();
  });

  it("renders volume/mute controls when showVolume is set", () => {
    setLocale("en");
    const onVolumeChange = vi.fn();
    const onMutedToggle = vi.fn();
    render(
      <PlaybackTransport
        {...baseProps}
        showVolume
        volume={0.6}
        muted={false}
        onVolumeChange={onVolumeChange}
        onMutedToggle={onMutedToggle}
      />,
    );

    expect(
      screen.getByRole("button", { name: /mute track audio/i }),
    ).toBeInTheDocument();
    const volumeSlider = screen.getByRole("slider", { name: /track volume/i });
    expect(volumeSlider).toHaveAttribute("aria-valuenow", "60");

    fireEvent.click(screen.getByRole("button", { name: /mute track audio/i }));
    expect(onMutedToggle).toHaveBeenCalledTimes(1);

    fireEvent.change(volumeSlider, { target: { value: "40" } });
    expect(onVolumeChange).toHaveBeenCalledWith(0.4);
  });

  it("renders playback rate slider and calls onPlaybackRateChange", () => {
    setLocale("en");
    const onPlaybackRateChange = vi.fn();
    render(
      <PlaybackTransport
        {...baseProps}
        playbackRate={1}
        onPlaybackRateChange={onPlaybackRateChange}
      />,
    );

    const rateSlider = screen.getByRole("slider", { name: /playback speed/i });
    expect(rateSlider).toHaveAttribute("aria-valuenow", "100");

    fireEvent.change(rateSlider, { target: { value: "130" } });
    expect(onPlaybackRateChange).toHaveBeenCalledWith(1.3);
  });

  it("renders rate preset buttons and calls onPlaybackRateChange", () => {
    setLocale("en");
    const onPlaybackRateChange = vi.fn();
    render(
      <PlaybackTransport
        {...baseProps}
        playbackRate={1}
        onPlaybackRateChange={onPlaybackRateChange}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /set playback speed to 0\.5/i }),
    );
    expect(onPlaybackRateChange).toHaveBeenCalledWith(0.5);

    fireEvent.click(
      screen.getByRole("button", { name: /set playback speed to 1\.5/i }),
    );
    expect(onPlaybackRateChange).toHaveBeenCalledWith(1.5);
  });

  it("renders loop toggle and calls onLoopToggle", () => {
    setLocale("en");
    const onLoopToggle = vi.fn();
    render(
      <PlaybackTransport
        {...baseProps}
        loopEnabled={false}
        onLoopToggle={onLoopToggle}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /enable loop/i }));
    expect(onLoopToggle).toHaveBeenCalledTimes(1);
  });

  it("shows loop-off aria when loop is enabled", () => {
    setLocale("en");
    render(
      <PlaybackTransport {...baseProps} loopEnabled onLoopToggle={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: /disable loop/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});
