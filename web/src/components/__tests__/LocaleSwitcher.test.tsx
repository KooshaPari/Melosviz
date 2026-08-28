import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LocaleSwitcher } from "../LocaleSwitcher";
import { LocaleProvider } from "../../i18n/LocaleProvider";
import { LOCALE_STORAGE_KEY, getLocale, setLocale } from "../../i18n";

function renderSwitcher() {
  return render(
    <LocaleProvider>
      <LocaleSwitcher />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  setLocale("en");
});

describe("LocaleSwitcher", () => {
  it("renders en and es toggles", () => {
    renderSwitcher();
    expect(
      screen.getByRole("button", { name: /english/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /spanish/i }),
    ).toBeInTheDocument();
  });

  it("persists locale choice to localStorage", () => {
    renderSwitcher();
    fireEvent.click(screen.getByRole("button", { name: /spanish/i }));
    expect(getLocale()).toBe("es");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("es");
  });

  it("marks active locale with aria-pressed", () => {
    renderSwitcher();
    const enBtn = screen.getByRole("button", { name: /english/i });
    const esBtn = screen.getByRole("button", { name: /spanish/i });
    expect(enBtn).toHaveAttribute("aria-pressed", "true");
    expect(esBtn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(esBtn);
    expect(esBtn).toHaveAttribute("aria-pressed", "true");
    expect(enBtn).toHaveAttribute("aria-pressed", "false");
  });
});
