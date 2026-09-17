import { it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SpecViewer } from "../SpecViewer";
import type { RenderSpec } from "../../renderSpec";

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

it("download button triggers a JSON blob download via anchor click", () => {
  const click = vi.fn();
  const createObjectURL = vi.fn(() => "blob:renderspec");
  const revokeObjectURL = vi.fn();
  const originalCreate = document.createElement.bind(document);
  vi.spyOn(document, "createElement").mockImplementation((tag) => {
    if (tag === "a") {
      return { click, download: "", href: "" } as unknown as HTMLAnchorElement;
    }
    return originalCreate(tag);
  });
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

  render(<SpecViewer spec={MOCK_SPEC} />);
  fireEvent.click(
    screen.getByRole("button", { name: /download renderspec as json/i }),
  );

  expect(createObjectURL).toHaveBeenCalled();
  expect(click).toHaveBeenCalled();
  expect(revokeObjectURL).toHaveBeenCalled();
});

it("copy button writes JSON to clipboard and shows toast", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });

  render(<SpecViewer spec={MOCK_SPEC} />);
  fireEvent.click(
    screen.getByRole("button", { name: /copy renderspec json to clipboard/i }),
  );

  expect(writeText).toHaveBeenCalledWith(
    JSON.stringify(MOCK_SPEC, null, 2),
  );
  const toast = await screen.findByTestId("toast");
  expect(toast).toHaveAttribute("aria-live", "polite");
  expect(toast).toHaveTextContent(/renderspec json copied to clipboard/i);
});
