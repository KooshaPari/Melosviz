import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AudioDropzone } from "../AudioDropzone";
import { RECENT_AUDIO_STORAGE_KEY } from "../../lib/recentAudioFiles";
import { setLocale } from "../../i18n";

describe("AudioDropzone", () => {
  beforeEach(() => {
    localStorage.clear();
    setLocale("en");
    vi.restoreAllMocks();
  });

  it("renders drop zone and path input", () => {
    const onChange = vi.fn();
    render(<AudioDropzone value="" onChange={onChange} />);
    expect(screen.getByLabelText(/audio file path/i)).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: /drop an audio file/i }),
    ).toBeInTheDocument();
  });

  it("records path on blur", () => {
    const onChange = vi.fn();
    render(<AudioDropzone value="/music/track.mp3" onChange={onChange} />);
    fireEvent.blur(screen.getByLabelText(/audio file path/i));
    const stored = JSON.parse(
      localStorage.getItem(RECENT_AUDIO_STORAGE_KEY) ?? "[]",
    ) as Array<{
      name: string;
      kind: string;
    }>;
    expect(stored[0]?.name).toBe("track.mp3");
    expect(stored[0]?.kind).toBe("path");
  });

  it("shows recent path entries", () => {
    localStorage.setItem(
      RECENT_AUDIO_STORAGE_KEY,
      JSON.stringify([
        {
          name: "demo.wav",
          size: 1024,
          lastUsed: Date.now(),
          kind: "path",
          path: "/tmp/demo.wav",
        },
      ]),
    );
    const onChange = vi.fn();
    render(<AudioDropzone value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "demo.wav" }));
    expect(onChange).toHaveBeenCalledWith("/tmp/demo.wav");
  });

  it("labels file-only recent entries for re-pick", () => {
    localStorage.setItem(
      RECENT_AUDIO_STORAGE_KEY,
      JSON.stringify([
        { name: "session.mp3", size: 5000, lastUsed: Date.now(), kind: "file" },
      ]),
    );
    render(<AudioDropzone value="" onChange={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: /session\.mp3 \(re-pick file\)/i }),
    ).toBeInTheDocument();
  });

  it("clears recent list from storage", () => {
    localStorage.setItem(
      RECENT_AUDIO_STORAGE_KEY,
      JSON.stringify([
        {
          name: "demo.wav",
          size: 1024,
          lastUsed: Date.now(),
          kind: "path",
          path: "/tmp/demo.wav",
        },
      ]),
    );
    render(<AudioDropzone value="" onChange={vi.fn()} />);
    fireEvent.click(
      screen.getByRole("button", { name: /clear recent audio files list/i }),
    );
    expect(localStorage.getItem(RECENT_AUDIO_STORAGE_KEY)).toBeNull();
    expect(
      screen.queryByRole("button", { name: "demo.wav" }),
    ).not.toBeInTheDocument();
  });
});
