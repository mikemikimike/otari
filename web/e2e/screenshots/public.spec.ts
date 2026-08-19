import { expect } from "@playwright/test"

import { captureScreenshot, test } from "./fixtures"

// Everything a browser can reach without a session. Kept apart from the
// authenticated matrix because these are the screens an operator meets first
// and the ones most likely to be linked to from outside the app, so a
// regression here is the most expensive one to ship.

test("sign-in screen", async ({ page }) => {
  await page.goto("/")
  await expect(page.locator('input[type="password"]')).toBeVisible()
  await captureScreenshot(page, "sign-in")
})

test("sign-in screen with a rejected key", async ({ page }) => {
  await page.goto("/")
  const key = page.locator('input[type="password"]')
  await key.fill("not-the-master-key")
  await key.press("Enter")
  // The error state is a layout of its own: it adds a banner above the form,
  // which is exactly the kind of shift a screenshot catches and a unit test
  // does not.
  await expect(page.getByText(/invalid|unauthor/i).first()).toBeVisible()
  await captureScreenshot(page, "sign-in-rejected")
})

test("welcome page", async ({ page }) => {
  // Served by the gateway itself, not the SPA (src/gateway/dashboard.py), and
  // what "/" degrades to when no bundle was built.
  await page.goto("/welcome")
  await expect(page.getByRole("heading").first()).toBeVisible()
  await captureScreenshot(page, "welcome")
})
