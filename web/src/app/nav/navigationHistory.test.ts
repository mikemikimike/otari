import { afterEach, describe, expect, it } from "vitest"

import { lastLocation, rememberLocation } from "./navigationHistory"

const WORKSPACE_KEY = "otari.dashboard.lastWorkspaceLocation"
const ORGANIZATION_KEY = "otari.dashboard.lastOrganizationLocation"

describe("rail location memory", () => {
  afterEach(() => {
    window.localStorage.clear()
  })

  it("files a destination under the rail that declares it", () => {
    rememberLocation("/usage")
    rememberLocation("/budgets")

    // Two rails, two memories: recording an organization page must not overwrite
    // where you were on the workspace one, which is the whole point.
    expect(lastLocation("workspace")).toEqual({ to: "/usage" })
    expect(lastLocation("organization")).toEqual({ to: "/budgets" })
  })

  it("remembers a nested destination, not just a top-level one", () => {
    // "Including its subpage" is the part the shell used to lose: it sent you to
    // the rail's landing page however deep you had been.
    rememberLocation("/tools/web-search")

    expect(lastLocation("workspace")).toEqual({ to: "/tools/web-search" })
  })

  it("ignores a path the registry does not declare", () => {
    rememberLocation("/usage")
    rememberLocation("/docs")

    // The guide and the 404 splat are not places to return to, so the last real
    // destination stands rather than being replaced by one.
    expect(lastLocation("workspace")).toEqual({ to: "/usage" })
  })

  it("drops a stored value that is no longer a destination", () => {
    // A stale entry from an older build, or a hand-edited one. Returning it would
    // send someone to the shell's "not available here" panel.
    window.localStorage.setItem(WORKSPACE_KEY, "/retired-page")

    expect(lastLocation("workspace")).toBeUndefined()
  })

  it("drops a stored value that belongs to the other rail", () => {
    // Both keys are read through the same registry check, so a destination that
    // has since moved rails cannot land you on the wrong one.
    window.localStorage.setItem(ORGANIZATION_KEY, "/usage")

    expect(lastLocation("organization")).toBeUndefined()
  })

  it("answers with nothing before anything has been recorded", () => {
    expect(lastLocation("workspace")).toBeUndefined()
    expect(lastLocation("organization")).toBeUndefined()
  })
})
