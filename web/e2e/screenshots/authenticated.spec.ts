import { expect, type Page } from "@playwright/test"

import { gotoRoute, login, openOrganization } from "../helpers"
import { captureScreenshot, test } from "./fixtures"

// One entry per destination the nav registry can reach. The matrix in
// playwright.config.ts multiplies each of these by three viewports and both
// themes, so adding a page here is the whole cost of covering it.
//
// Routes are opened directly rather than clicked to, because this suite is
// about how a page renders, not how it is reached: the parity specs own
// navigation. The router is on hash history, so `gotoRoute` builds "/#<route>".
const WORKSPACE_ROUTES: ReadonlyArray<{
  readonly route: string
  readonly name: string
  readonly heading: RegExp
}> = [
  { route: "/", name: "overview", heading: /overview/i },
  { route: "/models", name: "models", heading: /models/i },
  { route: "/routing", name: "routing", heading: /routing/i },
  { route: "/providers", name: "providers", heading: /provider/i },
  { route: "/keys", name: "keys", heading: /keys/i },
  { route: "/budgets", name: "budgets", heading: /budgets/i },
  { route: "/users", name: "users", heading: /users/i },
  { route: "/usage", name: "usage", heading: /usage/i },
  { route: "/activity", name: "activity", heading: /activity/i },
  { route: "/tools", name: "tools", heading: /tools/i },
  { route: "/settings", name: "settings", heading: /settings/i },
  { route: "/docs", name: "docs", heading: /./ },
]

async function open(page: Page, route: string, heading: RegExp): Promise<void> {
  await gotoRoute(page, route)
  await expect(
    page.getByRole("heading", { name: heading }).first(),
  ).toBeVisible()
}

test.describe("workspace rail", () => {
  // Serial because the whole suite runs single-worker against one gateway
  // database (see playwright.config.ts). Each test still signs in on its own
  // page: the fixtures give every test a fresh context, which is also what
  // makes the theme seeding apply before its first navigation.
  test.describe.configure({ mode: "serial" })

  for (const { route, name, heading } of WORKSPACE_ROUTES) {
    test(name, async ({ page }) => {
      await login(page)
      await open(page, route, heading)
      await captureScreenshot(page, name)
    })
  }
})

test.describe("organization rail", () => {
  test.describe.configure({ mode: "serial" })

  test("organization general", async ({ page }) => {
    await login(page)
    await openOrganization(page)
    await captureScreenshot(page, "organization-general")
  })

  test("organization members", async ({ page }) => {
    await login(page)
    await gotoRoute(page, "/organization/members")
    await expect(
      page.getByRole("heading", { name: /members/i }).first(),
    ).toBeVisible()
    await captureScreenshot(page, "organization-members")
  })

  test("workspaces", async ({ page }) => {
    await login(page)
    await gotoRoute(page, "/workspaces")
    await expect(
      page.getByRole("heading", { name: /workspaces/i }).first(),
    ).toBeVisible()
    await captureScreenshot(page, "workspaces")
  })
})
