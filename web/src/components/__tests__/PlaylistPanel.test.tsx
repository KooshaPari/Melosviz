import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PlaylistPanel } from "../PlaylistPanel";
import type { PlaylistItem, UsePlaylistReturn } from "../../hooks/usePlaylist";
import { setLocale } from "../../i18n";

function makeItem(name: string, id: string): PlaylistItem {
  return {
    id,
    file: new File(["audio"], name, { type: "audio/mpeg" }),
    status: "pending",
  };
}

function makePlaylist(
  overrides: Partial<UsePlaylistReturn> = {},
): UsePlaylistReturn {
  const queue = [
    makeItem("a.mp3", "pl-1"),
    makeItem("b.mp3", "pl-2"),
    makeItem("c.mp3", "pl-3"),
  ];
  return {
    queue,
    currentIndex: 1,
    isProcessing: false,
    addFiles: vi.fn(),
    removeItem: vi.fn(),
    reorder: vi.fn(),
    clearQueue: vi.fn(),
    setCurrentIndex: vi.fn(),
    activeItem: queue[1] ?? null,
    ...overrides,
  };
}

describe("PlaylistPanel", () => {
  it("move-down button calls reorder for the selected row", () => {
    setLocale("en");
    const reorder = vi.fn();
    const playlist = makePlaylist({ reorder });

    render(<PlaylistPanel playlist={playlist} onSelectItem={vi.fn()} />);

    fireEvent.click(
      screen.getByRole("button", { name: /move b\.mp3 down in queue/i }),
    );
    expect(reorder).toHaveBeenCalledWith(1, 2);
  });

  it("Alt+ArrowUp on a row calls reorder", () => {
    setLocale("en");
    const reorder = vi.fn();
    const playlist = makePlaylist({ reorder });

    render(<PlaylistPanel playlist={playlist} onSelectItem={vi.fn()} />);

    const rows = screen.getAllByRole("listitem");
    fireEvent.keyDown(rows[2]!, { key: "ArrowUp", altKey: true });

    expect(reorder).toHaveBeenCalledWith(2, 1);
  });
});
