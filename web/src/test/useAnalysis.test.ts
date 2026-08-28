import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import {
  useAnalysis,
  analyzeAudioPath,
  formatAnalysisError,
  resolveServerAudioPath,
  uploadAudioFile,
} from "../hooks/useAnalysis";

const MOCK_RAW = {
  duration_sec: 180,
  bpm: 128,
  keyframes: [{ t: 0, scene: "Intro" }],
};

function mockJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 413 ? "Payload Too Large" : "OK",
    json: async () => body,
  } as Response;
}

describe("formatAnalysisError", () => {
  it("maps 413 to a clear message", () => {
    expect(formatAnalysisError(null, 413)).toMatch(/too large/i);
  });

  it("maps failed fetch to connection reset hint", () => {
    expect(formatAnalysisError(new TypeError("Failed to fetch"))).toMatch(
      /bridge/,
    );
  });
});

describe("resolveServerAudioPath", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns filesystem paths unchanged", async () => {
    const path = "C:\\music\\track.wav";
    await expect(resolveServerAudioPath(path)).resolves.toBe(path);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uploads blob URLs and returns wav_path", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: async () => new Blob(["wav-bytes"], { type: "audio/wav" }),
    } as Response);

    class MockXHR {
      upload = { onprogress: null as ((ev: ProgressEvent) => void) | null };
      responseType = "";
      status = 200;
      statusText = "OK";
      response = { wav_path: "/data/uploads/abc.wav" };
      open = vi.fn();
      send = vi.fn(function (this: MockXHR) {
        this.onload?.();
      });
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
    }
    vi.stubGlobal(
      "XMLHttpRequest",
      MockXHR as unknown as typeof XMLHttpRequest,
    );

    await expect(resolveServerAudioPath("blob:mock-1")).resolves.toBe(
      "/data/uploads/abc.wav",
    );
  });
});

describe("analyzeAudioPath", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("analyzes pasted paths without uploading", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockJsonResponse(MOCK_RAW));

    const spec = await analyzeAudioPath("/srv/audio/track.wav");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wav_path: "/srv/audio/track.wav" }),
    });
    expect(spec.durationSecs).toBe(180);
    expect(spec.bpm).toBe(128);
  });

  it("uploads blob URLs then analyzes with returned wav_path", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: async () => new Blob(["x"], { type: "audio/wav" }),
      } as Response)
      .mockResolvedValueOnce(mockJsonResponse(MOCK_RAW));

    class MockXHR {
      upload = { onprogress: null as ((ev: ProgressEvent) => void) | null };
      responseType = "";
      status = 200;
      statusText = "OK";
      response = { wav_path: "/tmp/uploads/test.wav" };
      open = vi.fn();
      send = vi.fn(function (this: MockXHR) {
        this.onload?.();
      });
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
    }
    vi.stubGlobal(
      "XMLHttpRequest",
      MockXHR as unknown as typeof XMLHttpRequest,
    );

    const spec = await analyzeAudioPath("blob:playlist-item");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenLastCalledWith("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wav_path: "/tmp/uploads/test.wav" }),
    });
    expect(spec.durationSecs).toBe(180);
  });

  it("surfaces 413 from analyze", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      mockJsonResponse({ detail: "Body exceeds 1048576 bytes" }, 413),
    );

    await expect(analyzeAudioPath("/big.wav")).rejects.toMatchObject({
      message: expect.stringMatching(/413|Body exceeds/),
      status: 413,
    });
  });
});

describe("uploadAudioFile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reports connection reset on xhr error", async () => {
    class MockXHR {
      upload = { onprogress: null as ((ev: ProgressEvent) => void) | null };
      responseType = "";
      open = vi.fn();
      send = vi.fn(function (this: MockXHR) {
        this.onerror?.();
      });
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
    }
    vi.stubGlobal(
      "XMLHttpRequest",
      MockXHR as unknown as typeof XMLHttpRequest,
    );

    const file = new File(["a"], "a.wav", { type: "audio/wav" });
    await expect(uploadAudioFile(file)).rejects.toMatchObject({
      message: expect.stringMatching(/reset|bridge/i),
    });
  });
});

describe("useAnalysis", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sets error state on connection failure", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const { result } = renderHook(() => useAnalysis());
    await act(async () => {
      await result.current.analyze("/music/track.wav");
    });

    await waitFor(() => {
      expect(result.current.error).toMatch(/bridge/i);
      expect(result.current.loading).toBe(false);
    });
  });

  it("populates data after successful path analyze", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(mockJsonResponse(MOCK_RAW));

    const { result } = renderHook(() => useAnalysis());
    await act(async () => {
      await result.current.analyze("/music/track.wav");
    });

    await waitFor(() => {
      expect(result.current.data?.bpm).toBe(128);
      expect(result.current.error).toBeNull();
    });
  });
});
