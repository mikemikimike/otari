import { test as base, expect, type Locator, type Page } from "@playwright/test"

// Shared machinery for the visual-regression suite. The specs themselves stay a
// list of routes; everything that makes a screenshot reproducible lives here.

/** Same key `index.html`'s pre-paint script and `useTheme` both read. */
const THEME_STORAGE_KEY = "otari.dashboard.theme"

/**
 * The theme a project captures, taken from its name rather than a typed
 * Playwright option: the matrix in playwright.config.ts already spells it
 * (`screenshots-mobile-dark`), and reading it back here keeps the config plain
 * instead of making it generic over a custom option type.
 */
function themeFor(projectName: string): "light" | "dark" {
  return projectName.endsWith("-dark") ? "dark" : "light"
}

export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const theme = themeFor(testInfo.project.name)
    // Seeded before the first navigation, so the pre-paint script in index.html
    // applies the theme on the first frame. Setting it afterwards would capture
    // whatever the OS preference resolved to until React mounted.
    await page.addInitScript(
      ([key, value]) => {
        window.localStorage.setItem(key, value)
      },
      [THEME_STORAGE_KEY, theme] as const,
    )
    await use(page)
  },
})

/**
 * Regions whose pixels are not the thing under test.
 *
 * Recharts animates its series in on mount and exposes no way to turn that off
 * from a test, so a chart is a coin flip at capture time; `animations:
 * "disabled"` only reaches CSS animations. Relative timestamps ("2 minutes
 * ago") move with the wall clock. Both are masked rather than waited out: a
 * screenshot suite that is 95% reliable trains everyone to re-run it.
 */
function volatileRegions(page: Page): Locator[] {
  return [
    page.locator(".recharts-responsive-container"),
    page.getByText(/\bago\b/),
  ]
}

/**
 * Capture one page state under the project's viewport and theme.
 *
 * `fullPage` because a dashboard page's interesting parts are usually below the
 * fold on the mobile viewport, and a clipped capture would silently stop
 * covering them.
 */
export async function captureScreenshot(
  page: Page,
  name: string,
): Promise<void> {
  // Fonts are self-hosted and swap in late enough to change metrics mid-capture.
  await page.evaluate(() => document.fonts.ready)
  await expect(page).toHaveScreenshot(`${name}.png`, {
    fullPage: true,
    animations: "disabled",
    caret: "hide",
    mask: volatileRegions(page),
  })
}
