/**
 * @vitest-environment happy-dom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from "@testing-library/react";
import { StudioConsole } from "../StudioConsole";

function renderStudio(initialWavPath = "/tmp/track.wav") {
  return render(<StudioConsole initialWavPath={initialWavPath} />);
}

describe("StudioConsole (Director\u2019s Console)", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("renders the four-stage ribbon", () => {
    renderStudio();
    expect(screen.getByTestId("studio-btn-storyboard")).toBeTruthy();
    expect(screen.getByTestId("studio-btn-generate")).toBeTruthy();
    expect(screen.getByTestId("studio-btn-master")).toBeTruthy();
    expect(screen.getByTestId("studio-btn-ship")).toBeTruthy();
  });

  it("seeds inputs from initialWavPath", () => {
    renderStudio("/tmp/underwater.wav");
    const wavInput = screen.getByTestId("studio-wav-input") as HTMLInputElement;
    expect(wavInput.value).toBe("/tmp/underwater.wav");
  });

  it("uses sensible defaults for BPM, palette, concept", () => {
    renderStudio();
    const bpmInput = screen.getByTestId("studio-bpm-input") as HTMLInputElement;
    const paletteInput = screen.getByTestId(
      "studio-palette-input",
    ) as HTMLInputElement;
    expect(Number(bpmInput.value)).toBeGreaterThanOrEqual(60);
    expect(Number(bpmInput.value)).toBeLessThanOrEqual(180);
    expect(paletteInput.value.length).toBeGreaterThan(8);
  });

  it("POSTs to /api/studio/storyboard with the configured concept + BPM + palette", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      text: () =>
        Promise.resolve(
          JSON.stringify({
            concept: "underwater city",
            bpm: 124,
            scenes: [
              {
                name: "Bioluminescent opening",
                start_sec: 0,
                end_sec: 30,
                scene_type: "comfyui_image",
                camera_motion: "slow dolly",
                prompt: "underwater city, bioluminescent",
                palette: ["#0d0d10", "#ff2bd6"],
                seed: 42,
              },
            ],
          }),
        ),
    } as Response);

    renderStudio();
    fireEvent.click(screen.getByTestId("studio-btn-storyboard"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toContain("/api/studio/storyboard");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.wav_path).toBe("/tmp/track.wav");
    expect(body.bpm).toBeGreaterThan(0);
    expect(body.palette).toMatch(/#/i);
    expect(body.concept.length).toBeGreaterThan(0);
  });

  it("renders per-scene rows with queued status after storyboard", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      text: () =>
        Promise.resolve(
          JSON.stringify({
            scenes: [
              {
                name: "Open",
                start_sec: 0,
                end_sec: 10,
                scene_type: "comfyui_image",
                camera_motion: "static",
                prompt: "a",
                palette: ["#000000"],
                seed: 1,
              },
              {
                name: "Build",
                start_sec: 10,
                end_sec: 20,
                scene_type: "comfyui_video",
                camera_motion: "orbit",
                prompt: "b",
                palette: ["#ffffff"],
                seed: 2,
              },
            ],
          }),
        ),
    } as Response);

    renderStudio();
    await act(async () => {
      fireEvent.click(screen.getByTestId("studio-btn-storyboard"));
    });

    await waitFor(() => {
      const items = document.querySelectorAll(".studio-queue-item");
      expect(items.length).toBe(2);
    });

    const items = document.querySelectorAll(".studio-queue-item");
    expect(items[0]?.getAttribute("data-state")).toBe("queued");
    expect(items[1]?.getAttribute("data-state")).toBe("queued");
  });

  it("blocks Generate until a storyboard exists", () => {
    renderStudio();
    const generateBtn = screen.getByTestId(
      "studio-btn-generate",
    ) as HTMLButtonElement;
    expect(generateBtn.disabled).toBe(true);
  });

  it("surfaces fetch errors as the error banner", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      text: () => Promise.resolve("memory cap exceeded"),
    } as Response);

    renderStudio();
    await act(async () => {
      fireEvent.click(screen.getByTestId("studio-btn-storyboard"));
    });

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/503|memory/i);
    });
  });

  it("toggles offline mode and LLM director via checkboxes", () => {
    renderStudio();
    const llm = screen.getByTestId("studio-llm-toggle") as HTMLInputElement;
    const offline = screen.getByTestId(
      "studio-offline-toggle",
    ) as HTMLInputElement;
    expect(llm.checked).toBe(true);
    expect(offline.checked).toBe(true);

    fireEvent.click(llm);
    fireEvent.click(offline);
    expect(llm.checked).toBe(false);
    expect(offline.checked).toBe(false);
  });

  it("exposes LUFS target select with sensible preset options", () => {
    renderStudio();
    const lufs = screen.getByTestId("studio-lufs-select") as HTMLSelectElement;
    expect(lufs).toBeTruthy();
    const options = Array.from(lufs.querySelectorAll("option")).map(
      (o) => o.value,
    );
    expect(options).toContain("youtube");
    expect(options).toContain("spotify");
    expect(options).toContain("broadcast");
    expect(options).toContain("club_pa");
  });

  it("exposes a stem-export checkbox defaulting on", () => {
    renderStudio();
    const stems = screen.getByTestId("studio-stems-toggle") as HTMLInputElement;
    expect(stems).toBeTruthy();
    expect(stems.checked).toBe(true);
  });

  it("POSTs /api/studio/storyboard with lyrics_path + mood_board_paths + aspect_ratio + continuity", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      text: () =>
        Promise.resolve(
          JSON.stringify({
            scenes: [
              {
                name: "S0",
                start_sec: 0,
                end_sec: 5,
                scene_type: "comfyui_image",
                prompt: "x",
                palette: ["#000"],
                seed: 1,
              },
            ],
          }),
        ),
    } as Response);

    renderStudio();
    const lyricsEl = screen.getByTestId(
      "studio-lyrics-input",
    ) as HTMLInputElement;
    const moodEl = screen.getByTestId(
      "studio-moodboard-input",
    ) as HTMLInputElement;
    fireEvent.change(lyricsEl, { target: { value: "/tmp/song.lrc" } });
    fireEvent.change(moodEl, { target: { value: "/tmp/moodboard.txt" } });

    await act(async () => {
      fireEvent.click(screen.getByTestId("studio-btn-storyboard"));
    });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());

    const [, init] = fetchSpy.mock.calls[0] ?? [];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.lyrics_path).toBe("/tmp/song.lrc");
    expect(body.mood_board_paths).toEqual(["/tmp/moodboard.txt"]);
    expect(body.aspect_ratio).toMatch(/16x9|9x16|4k|1080|1x1/i);
  });

  it("forwards lufs_target + export_stems + audio_path to /api/studio/master", async () => {
    // 1) storyboard OK
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      text: () =>
        Promise.resolve(
          JSON.stringify({
            scenes: [
              {
                name: "S0",
                start_sec: 0,
                end_sec: 5,
                scene_type: "comfyui_image",
                prompt: "x",
                palette: ["#000"],
                seed: 1,
              },
            ],
          }),
        ),
    } as Response);
    // 2) generate OK
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      text: () =>
        Promise.resolve(
          JSON.stringify({
            out_dir: "/tmp/g",
            scenes: [
              {
                index: 0,
                scene_type: "comfyui_image",
                workflow_json: "/tmp/g/workflow_0.json",
              },
            ],
          }),
        ),
    } as Response);
    // 3) master OK
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: "OK",
      text: () =>
        Promise.resolve(
          JSON.stringify({
            deliverables: [
              { name: "mp4_h264_1080p", path: "/tmp/master/mp4.mp4" },
            ],
            files: [
              {
                name: "master_plan.json",
                path: "/tmp/master/master_plan.json",
              },
            ],
            lufs_target: "youtube",
            stems_export: {
              method: "ffmpeg_3band",
              audio: "/tmp/master/stems",
            },
          }),
        ),
    } as Response);

    renderStudio();
    fireEvent.change(screen.getByTestId("studio-lufs-select"), {
      target: { value: "youtube" },
    });
    // stems default ON, audio default seeded from wav_path
    await act(async () => {
      fireEvent.click(screen.getByTestId("studio-btn-storyboard"));
    });
    await waitFor(() =>
      expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(1),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId("studio-btn-generate"));
    });
    await waitFor(() =>
      expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(2),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId("studio-btn-master"));
    });
    await waitFor(() =>
      expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(3),
    );

    const masterCall = fetchSpy.mock.calls.find((c) =>
      String(c[0]).includes("/api/studio/master"),
    );
    expect(masterCall).toBeTruthy();
    const body = JSON.parse((masterCall?.[1] as RequestInit).body as string);
    expect(body.lufs_target).toBe("youtube");
    expect(body.export_stems).toBe(true);
    expect(
      body.audio_wav_path || body.audio_path || body.audio || body.wav_path,
    ).toBeTruthy();
  });
});
