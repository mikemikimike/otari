import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

import playwrightConfig from "../playwright.config"

/**
 * Every Playwright project has to be named by one of the e2e scripts.
 *
 * A project's `testMatch`/`testDir` is the only thing that collects its files,
 * and this version of Playwright supports neither wildcards nor negation in
 * `--project`, so both scripts in package.json list their projects by hand. A
 * project nobody lists runs in no script at all: `pnpm run e2e` and
 * `pnpm run e2e:screenshots` both pass, having silently skipped it. That is the
 * same failure the config's own comment warns about one level down, and it is
 * invisible in a green run, so it is asserted here instead.
 */
describe("the Playwright project list", () => {
  const scripts = JSON.parse(
    readFileSync(join(__dirname, "..", "package.json"), "utf8"),
  ).scripts as Record<string, string>

  const declared = (playwrightConfig.projects ?? []).map(
    (project) => project.name,
  )

  it("declares projects", () => {
    // Guards the assertion below against a config that stopped exporting any.
    expect(declared.length).toBeGreaterThan(0)
  })

  it.each(declared)("runs %s in an e2e script", (name) => {
    const runners = [scripts.e2e, scripts["e2e:screenshots"]].join(" ")
    expect(runners, `no e2e script runs the "${name}" project`).toContain(
      `--project=${name}`,
    )
  })
})
