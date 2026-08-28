import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import * as SpecViewerModule from "../SpecViewer";
import type { RenderSpec } from "../../renderSpec";

const { SpecViewer, downloadRenderSpec, copyRenderSpecToClipboard } =
  SpecViewerModule;

const MOCK_SPEC: RenderSpec = {
  durationSecs: 180,
  bpm: 128,
  keyframes: [
    {
      t: 0,
      scene: "Intro",
      camera: { distance: 8, azimuth: 0, elevation: 0 },
      color: { primary: "#7c6af7", secondary: "#22d3ee", brightness: 0.7 },
    },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
});

it("renders summary and download button", () => {
  render(<SpecViewer spec={MOCK_SPEC} />);
  expect(screen.getByText(/RenderSpec/i)).toBeInTheDocument();
  expect(screen.getByTestId("spec-summary")).toHaveTextContent(
    "180s · 128 BPM · 1 keyframes",
  );
  expect(
    screen.getByRole("button", { name: /copy renderspec json to clipboard/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /download renderspec as json/i }),
  ).toBeInTheDocument();
});

it("downloadRenderSpec triggers a JSON blob download", () => {
  const click = vi.fn();
  const createObjectURL = vi.fn(() => "blob:renderspec");
  const revokeObjectURL = vi.fn();
  const createElement = vi
    .spyOn(document, "createElement")
    .mockImplementation((tag) => {
      if (tag === "a") {
        return {
          click,
          download: "",
          href: "",
        } as unknown as HTMLAnchorElement;
      }
      return document.createElement(tag);
    });

  vi.stubGlobal("URL", {
    createObjectURL,
    revokeObjectURL,
  });

  downloadRenderSpec(MOCK_SPEC, "test-spec.json");

  expect(createObjectURL).toHaveBeenCalled();
  expect(click).toHaveBeenCalled();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:renderspec");
  createElement.mockRestore();
});

it("download button invokes download helper", () => {
  const downloadSpy = vi
    .spyOn(SpecViewerModule, "downloadRenderSpec")
    .mockImplementation(() => {});

  render(<SpecViewer spec={MOCK_SPEC} />);
  fireEvent.click(
    screen.getByRole("button", { name: /download renderspec as json/i }),
  );
  expect(downloadSpy).toHaveBeenCalledWith(MOCK_SPEC);
});

it("copyRenderSpecToClipboard writes JSON text", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });

  await copyRenderSpecToClipboard(MOCK_SPEC);

  expect(writeText).toHaveBeenCalledWith(JSON.stringify(MOCK_SPEC, null, 2));
});

it("copy button invokes clipboard helper and shows toast feedback", async () => {
  const copySpy = vi
    .spyOn(SpecViewerModule, "copyRenderSpecToClipboard")
    .mockResolvedValue(undefined);

  render(<SpecViewer spec={MOCK_SPEC} />);
  fireEvent.click(
    screen.getByRole("button", { name: /copy renderspec json to clipboard/i }),
  );

  expect(copySpy).toHaveBeenCalledWith(MOCK_SPEC);
  const toast = await screen.findByTestId("toast");
  expect(toast).toHaveAttribute("aria-live", "polite");
  expect(toast).toHaveTextContent(/renderspec json copied to clipboard/i);
});
