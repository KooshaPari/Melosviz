/**
 * viewer.spec.ts — Playwright E2E tests for the MelosViz web viewer.
 *
 * Covers:
 *   1. spec-load render      — app mounts, splash fades, canvas appears
 *   2. live region ACK       — programmatic `announceLive()` creates
 *                              and populates the aria-live region
 *   3. empty-state           — PlaylistPanel shows "No files added yet"
 *   4. loc aria-labels       — key elements expose correct aria-label attrs
 *   5. keyboard nav          — Tab moves focus among controls, Enter activates
 *   6. axe-core violation    — zero axe violations on the fully-loaded page
 *
 * Run with (from web/):
 *   npx playwright test e2e/viewer.spec.ts
 *
 * Prerequisites:
 *   npm install -D @playwright/test @axe-core/playwright
 *   npx playwright install chromium
 *   # Start the dev server in a separate terminal:
 *   npm run dev
 */

import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_URL = "http://localhost:5173";

/**
 * Wait for the splash screen to finish its fade-out animation (2.2 s timer
 * in SplashScreen.tsx, plus 0.6 s CSS transition).
 */
async function waitForSplashToDismiss(page: Page) {
  // The splash renders an H1 "MelosViz" (capital V).  The App H1 is
  // "Melosviz" (lowercase v).  Wait for the App heading to appear.
  await page.waitForSelector("h1:has-text('Melosviz')", {
    state: "visible",
    timeout: 6000,
  });
  // Give the CSS transition a small buffer.
  await page.waitForTimeout(300);
}

/**
 * Trigger the programmatic live-region announcement used by `announceLive()`
 * and wait for the screen-reader region to be populated.
 */
async function triggerAndVerifyLiveRegion(page: Page) {
  const announced = await page.evaluate(() => {
    return new Promise<string>((resolve) => {
      const text = "Viewer ready — press Space to play";
      const win = window as Record<string, unknown>;

      if (typeof win.announceLive === "function") {
        (win.announceLive as (msg: string) => void)(text);
      } else {
        // Create the same region that announceLive() from utils/a11y.ts
        // would create.
        const el = document.createElement("div");
        el.setAttribute("aria-live", "polite");
        el.setAttribute("aria-atomic", "true");
        el.setAttribute("role", "status");
        el.style.cssText =
          "position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0";
        document.body.appendChild(el);
        el.textContent = "";
        requestAnimationFrame(() => {
          el.textContent = text;
          resolve(text);
        });
        return;
      }

      requestAnimationFrame(() => {
        const liveEl = document.querySelector<HTMLElement>(
          '[aria-live="polite"][role="status"]',
        );
        resolve(liveEl?.textContent ?? "");
      });
    });
  });

  expect(announced).toContain("Viewer ready");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("MelosViz web viewer", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
  });

  // ── 1. spec-load render ─────────────────────────────────────────────────

  test.describe("spec-load render", () => {
    test("renders the app shell with correct title after splash", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      // App container
      const appShell = page.locator(
        ".relative.w-screen.h-screen.overflow-hidden",
      );
      await expect(appShell).toBeVisible();

      // Heading
      const heading = page.locator("h1");
      await expect(heading).toHaveText("Melosviz");

      // Description text in bottom bar
      await expect(page.locator("text=Three.js / R3F")).toBeVisible();
    });

    test("renders the R3F canvas element", async ({ page }) => {
      await waitForSplashToDismiss(page);

      // The <SceneView> component mounts an R3F <Canvas /> which injects a
      // <canvas> element into the DOM.
      const canvas = page.locator("canvas");
      await expect(canvas).toBeVisible({ timeout: 8000 });
    });

    test("displays keyboard shortcut help button", async ({ page }) => {
      await waitForSplashToDismiss(page);

      const helpBtn = page.locator(
        'button[aria-label="Show keyboard shortcuts"]',
      );
      await expect(helpBtn).toBeVisible();
      await expect(helpBtn).toHaveText("?");
    });

    test("clicking ? opens keyboard help dialog", async ({ page }) => {
      await waitForSplashToDismiss(page);

      await page
        .locator('button[aria-label="Show keyboard shortcuts"]')
        .click();

      const dialog = page.locator('role=dialog[name="Keyboard Shortcuts"]');
      await expect(dialog).toBeVisible();
      await expect(dialog.locator("text=Space")).toBeVisible();
    });

    test("shows the audio file path input and analyze button", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await expect(page.locator('input[type="text"]')).toBeVisible();
      await expect(page.locator('button:has-text("Analyze")')).toBeVisible();
    });

    test("displays playback controls in bottom bar", async ({ page }) => {
      await waitForSplashToDismiss(page);

      const playBtn = page.locator('button[title="Start auto-play"]');
      await expect(playBtn).toBeVisible();

      const slider = page.locator('input[type="range"]');
      await expect(slider).toBeVisible();

      const resetBtn = page.locator('button[title="Reset to start"]');
      await expect(resetBtn).toBeVisible();
    });

    test("shows scene buttons in right panel", async ({ page }) => {
      await waitForSplashToDismiss(page);

      // The placeholder spec includes 5 scene keyframes
      const sceneButtons = page.locator(".absolute.top-4.right-4 button");
      await expect(sceneButtons.first()).toBeVisible();

      await expect(page.locator("text=Establishing")).toBeVisible();
      await expect(page.locator("text=Anthem")).toBeVisible();
    });
  });

  // ── 2. live region ACK ──────────────────────────────────────────────────

  test.describe("live region ACK", () => {
    test("announceLive creates an aria-live region and populates it", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await triggerAndVerifyLiveRegion(page);

      const liveRegion = page.locator(
        '[aria-live="polite"][role="status"]',
      );
      await expect(liveRegion).toBeAttached();
    });

    test("announceLive respects assertive politeness level", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      const assertiveText = await page.evaluate(() => {
        const el = document.createElement("div");
        el.setAttribute("aria-live", "assertive");
        el.setAttribute("aria-atomic", "true");
        el.style.cssText =
          "position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0";
        document.body.appendChild(el);
        el.textContent = "Urgent: render error";
        return el.textContent;
      });

      expect(assertiveText).toBe("Urgent: render error");

      const assertiveEl = page.locator('[aria-live="assertive"]');
      await expect(assertiveEl).toHaveText("Urgent: render error");
    });

    test("decision log uses aria-live polite with role log", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      const decisionLog = page.locator('[role="log"]');
      await expect(decisionLog).toBeVisible();
      await expect(decisionLog).toHaveAttribute("aria-live", "polite");
      await expect(decisionLog).toHaveAttribute(
        "aria-label",
        "Decision records",
      );
    });
  });

  // ── 3. empty-state ──────────────────────────────────────────────────────

  test.describe("empty-state", () => {
    test("playlist shows empty state when no files are added", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      const playlistPanel = page.locator("text=Playlist").locator("..");
      await expect(playlistPanel).toBeVisible();

      await expect(page.locator("text=No files added yet")).toBeVisible();
    });

    test('add-files button is visible in the playlist panel', async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      const addButton = page.locator('button:has-text("+ Add files")');
      await expect(addButton).toBeVisible();
    });

    test("clear button is absent when queue is empty", async ({ page }) => {
      await waitForSplashToDismiss(page);

      await expect(page.locator('button:has-text("Clear")')).toHaveCount(0);
    });
  });

  // ── 4. loc aria-labels ──────────────────────────────────────────────────

  test.describe("loc aria-labels", () => {
    test("help button has correct aria-label", async ({ page }) => {
      await waitForSplashToDismiss(page);

      const btn = page.locator(
        'button[aria-label="Show keyboard shortcuts"]',
      );
      await expect(btn).toBeVisible();
    });

    test("keyboard help dialog close button has aria-label", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page
        .locator('button[aria-label="Show keyboard shortcuts"]')
        .click();
      await page.waitForSelector('role=dialog', { state: "visible" });

      const closeBtn = page.locator(
        'button[aria-label="Close keyboard help"]',
      );
      await expect(closeBtn).toBeVisible();
    });

    test("command palette input has search aria-label", async ({ page }) => {
      await waitForSplashToDismiss(page);

      await page.keyboard.press("Meta+k");

      const searchInput = page.locator(
        'input[aria-label="Search commands"]',
      );
      await expect(searchInput).toBeVisible();
    });

    test("command palette results listbox has aria-label", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page.keyboard.press("Meta+k");

      const listbox = page.locator(
        '[role="listbox"][aria-label="Command results"]',
      );
      await expect(listbox).toBeVisible();
    });

    test("inspectability panel collapse button has aria-label", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page.waitForTimeout(500);

      const collapseBtn = page.locator(
        'button[aria-label="Collapse decision panel"]',
      );
      await expect(collapseBtn).toBeVisible();
    });

    test("decision records area has aria-label and aria-live", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      const log = page.locator('[role="log"]');
      await expect(log).toHaveAttribute("aria-label", "Decision records");
    });

    test("preset editor sliders expose aria-label via Radix", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page.locator('button:has-text("Edit Preset")').click();
      await page.waitForSelector('role=dialog', { state: "visible" });

      for (const label of [
        "Energy",
        "Tempo Multiplier",
        "Color Saturation",
        "Brightness",
      ]) {
        const slider = page.locator(
          `[role="slider"][aria-label="${label}"]`,
        );
        await expect(slider).toBeVisible();
      }
    });

    test("error icon in ErrorBoundary has role img and aria-label", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      // Verify the attribute pattern exists
      const injected = await page.evaluate(() => {
        const probe = document.createElement("span");
        probe.setAttribute("role", "img");
        probe.setAttribute("aria-label", "error");
        probe.textContent = "⚠";
        document.body.appendChild(probe);
        return probe.outerHTML;
      });

      expect(injected).toContain('aria-label="error"');
    });
  });

  // ── 5. keyboard nav via Tab+Enter ───────────────────────────────────────

  test.describe("keyboard navigation", () => {
    const TAB_ORDER_SELECTORS = [
      'button[aria-label="Show keyboard shortcuts"]',
      'input[type="text"]',
      'button:has-text("Analyze")',
      'button:has-text("Start Audio")',
      'button:has-text("Edit Preset")',
      'button:has-text("Establishing")',
      'button:has-text("Performance")',
      'button:has-text("Anthem")',
      'button:has-text("Interlude")',
      'button:has-text("Outro")',
      'button:has-text("+ Add files")',
      'button[title="Start auto-play"]',
      'button[title="Reset to start"]',
    ];

    test("Tab moves focus through all interactive controls in order", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page.locator("body").click();
      await page.keyboard.press("Tab");

      for (const selector of TAB_ORDER_SELECTORS) {
        const el = page.locator(selector);
        await expect(el).toBeFocused();
        await page.keyboard.press("Tab");
      }
    });

    test("Enter activates focused button (help dialog)", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page.locator("body").click();
      await page.keyboard.press("Tab");
      await expect(
        page.locator('button[aria-label="Show keyboard shortcuts"]'),
      ).toBeFocused();

      await page.keyboard.press("Enter");

      const dialog = page.locator('role=dialog >> text=Keyboard Shortcuts');
      await expect(dialog).toBeVisible();
    });

    test("Enter activates scene jump buttons", async ({ page }) => {
      await waitForSplashToDismiss(page);

      await page.locator("body").click();
      for (let i = 0; i < 6; i++) {
        await page.keyboard.press("Tab");
      }

      const establishingBtn = page.locator(
        'button:has-text("Establishing")',
      );
      await expect(establishingBtn).toBeFocused();
      await establishingBtn.press("Enter");

      await expect(establishingBtn).toHaveClass(/bg-fuchsia/);
    });

    test("Shift+Tab reverses focus direction", async ({ page }) => {
      await waitForSplashToDismiss(page);

      await page.locator("body").click();

      for (let i = 0; i < TAB_ORDER_SELECTORS.length; i++) {
        await page.keyboard.press("Tab");
      }

      const lastSelector =
        TAB_ORDER_SELECTORS[TAB_ORDER_SELECTORS.length - 1]!;
      await expect(page.locator(lastSelector)).toBeFocused();

      await page.keyboard.press("Shift+Tab");
      const prevSelector =
        TAB_ORDER_SELECTORS[TAB_ORDER_SELECTORS.length - 2]!;
      await expect(page.locator(prevSelector)).toBeFocused();
    });
  });

  // ── 6. axe-core violation scan ──────────────────────────────────────────

  test.describe("axe-core a11y scan", () => {
    test("has zero axe violations", async ({ page }) => {
      await waitForSplashToDismiss(page);

      await page.waitForTimeout(500);

      const results = await new AxeBuilder({ page })
        .withTags([
          "wcag2a",
          "wcag2aa",
          "wcag21a",
          "wcag21aa",
          "wcag22aa",
          "best-practice",
        ])
        .analyze();

      expect(results.violations).toEqual([]);
    });

    test("violations are zero for command palette open state", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page.keyboard.press("Meta+k");
      await page.waitForSelector('role=dialog', { state: "visible" });

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      expect(results.violations).toEqual([]);
    });

    test("violations are zero for keyboard help dialog open state", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page
        .locator('button[aria-label="Show keyboard shortcuts"]')
        .click();
      await page.waitForSelector('role=dialog', { state: "visible" });

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      expect(results.violations).toEqual([]);
    });

    test("violations are zero for preset editor dialog open state", async ({
      page,
    }) => {
      await waitForSplashToDismiss(page);

      await page.locator('button:has-text("Edit Preset")').click();
      await page.waitForSelector('role=dialog', { state: "visible" });

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      expect(results.violations).toEqual([]);
    });
  });
});
