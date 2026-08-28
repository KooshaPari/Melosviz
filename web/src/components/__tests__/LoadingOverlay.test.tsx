import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LoadingOverlay } from "../LoadingOverlay";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LoadingOverlay", () => {
  it("does not render dialog when visible=false", () => {
    const { container } = render(
      <LoadingOverlay visible={false} onCancel={vi.fn()} />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(container.firstChild).toBeNull();
  });

  it("renders accessible dialog with live region when visible", () => {
    render(<LoadingOverlay visible={true} onCancel={vi.fn()} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const live = document.querySelector('[aria-live="polite"]');
    expect(live).toBeTruthy();
    expect(live?.textContent).toMatch(/Analyzing/i);
  });

  it("calls onCancel when cancel button is clicked", () => {
    const onCancel = vi.fn();
    render(<LoadingOverlay visible={true} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel on Escape", async () => {
    const onCancel = vi.fn();
    render(<LoadingOverlay visible={true} onCancel={onCancel} />);
    await waitFor(() => {
      expect(document.getElementById("loading-overlay-cancel")).toBe(
        document.activeElement,
      );
    });
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("focuses cancel control when opened", async () => {
    render(<LoadingOverlay visible={true} onCancel={vi.fn()} />);
    await waitFor(() => {
      expect(document.getElementById("loading-overlay-cancel")).toBe(
        document.activeElement,
      );
    });
  });

  it("uses static freq bars when prefers-reduced-motion is set", () => {
    vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const { container } = render(
      <LoadingOverlay visible={true} onCancel={vi.fn()} />,
    );
    expect(container.querySelector(".mv-freq-bar")).toBeNull();
    expect(container.querySelector("style")).toBeNull();
  });

  it("announces percentage in live region when progressPct is provided", () => {
    render(
      <LoadingOverlay visible={true} onCancel={vi.fn()} progressPct={42} />,
    );
    const live = document.querySelector('[aria-live="polite"]');
    expect(live?.textContent).toMatch(/42/);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "42",
    );
    expect(screen.getByText(/Analyzing audio… 42%/i)).toBeInTheDocument();
  });
});
