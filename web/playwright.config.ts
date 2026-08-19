import { defineConfig, devices } from "@playwright/test"

// End-to-end tests for the dashboard, run against a real gateway serving the
// built bundle (booted by `webServer` below). Component behavior is covered by
// Vitest; this exercises the multi-page flows a browser actually walks.

// The visual-regression matrix: every screenshot spec is captured at three
// viewports in both themes. Widths are the ones otari-ai/frontend shoots, so a
// page that moves between the two repos is compared at the same sizes.
const SCREENSHOT_VIEWPORTS = [
  { name: "desktop-large", viewport: { width: 1920, height: 1080 } },
  { name: "desktop-small", viewport: { width: 1280, height: 800 } },
  { name: "mobile", viewport: { width: 390, height: 844 } },
] as const

const SCREENSHOT_THEMES = ["light", "dark"] as const

// One project per cell. The theme reaches the app through localStorage (see
// e2e/screenshots/fixtures.ts, which reads it back off the project name);
// `colorScheme` here is the OS-level preference underneath it, set to match so
// the two never disagree and native controls are painted the same way.
const screenshotProjects = SCREENSHOT_VIEWPORTS.flatMap(({ name, viewport }) =>
  SCREENSHOT_THEMES.map((theme) => ({
    name: `screenshots-${name}-${theme}`,
    testDir: "./e2e/screenshots",
    // Captured against the state the parity specs leave behind, so the
    // dependency is on that project rather than on the seed alone: what a page
    // renders depends on the rows in the database, and "whichever project
    // happened to run first" is not a fixture.
    dependencies: ["parity"],
    use: {
      ...devices["Desktop Chrome"],
      viewport,
      colorScheme: theme,
    },
  })),
)

export default defineConfig({
  testDir: "./e2e",
  // Baselines are per project and platform-independent by name: CI captures on
  // Linux and that is the only set committed, so a macOS run comparing against
  // them reports font-rendering diffs. That is expected; see
  // .github/skills/frontend-standards/testing.md before regenerating anything.
  snapshotPathTemplate:
    "e2e/screenshots/__snapshots__/{projectName}/{arg}{ext}",
  // The flows mutate one shared gateway DB, so they run in order, not parallel.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  // No retries: the serial flows share one gateway DB that serve.sh resets only
  // at server start, and Playwright does not restart the webServer between
  // retries. A retry would re-run the block against state left by the first
  // attempt (the provider/alias already exist) and fail deterministically.
  retries: 0,
  // "list" everywhere, not "line" locally: the gateway's own request log is piped
  // into this stream (see `webServer.stdout`), and the line reporter rewrites its
  // single status line with carriage returns, so interleaving the two shreds the
  // failure detail exactly when it is needed.
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8000",
    // Not "on-first-retry": retries are off by design (see above), so that mode
    // never fires and a CI failure arrives with no trace to open. Retaining on
    // failure keeps the artifact for the run that needs it and discards it for
    // every run that passes.
    trace: "retain-on-failure",
  },
  // Three ordered projects over one gateway, rather than one project relying on
  // the alphabetical order of filenames. `onboarding` needs the empty database
  // serve.sh leaves behind (it asserts the first-run screens), so anything that
  // writes usage has to come after it; the parity specs in turn all read one
  // seeded fixture, so they hang off the seed rather than each re-creating it.
  projects: [
    {
      name: "onboarding",
      testMatch: /dashboard\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "seed",
      testMatch: /parity\.setup\.ts/,
      dependencies: ["onboarding"],
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "parity",
      // Everything that is not the onboarding spec, rather than a `parity.*`
      // pattern: a project's testMatch is the only thing that collects a file, so
      // a spec named outside every pattern here runs in no project at all and is
      // dropped from the run silently, with no warning and a green exit.
      // The screenshot suite is excluded because it has its own six projects
      // below; without this it would also run here, once, unthemed.
      testIgnore: [/dashboard\.spec\.ts/, /screenshots\//],
      dependencies: ["seed"],
      use: { ...devices["Desktop Chrome"] },
    },
    ...screenshotProjects,
  ],
  webServer: {
    command: "bash e2e/serve.sh",
    url: "http://127.0.0.1:8000/health",
    // Opt-in only: by default always start a fresh gateway (serve.sh resets the
    // DB), so a stray server already on :8000 can't silently skip the reset and
    // leave the serial flows running against dirty state. Set
    // PLAYWRIGHT_REUSE_SERVER=1 for fast local iteration against a running one.
    reuseExistingServer: !!process.env.PLAYWRIGHT_REUSE_SERVER,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
})
