# Testing the dashboard

Three suites, each with a different job:

| Suite | Command | Covers |
| --- | --- | --- |
| Vitest + Testing Library | `pnpm --dir web test` | Components, hooks, pure helpers. The bulk. |
| Playwright behavioral | `pnpm --dir web run e2e` | Multi-page flows against a real gateway. |
| Playwright screenshots | `pnpm --dir web run e2e:screenshots` | How every page renders, at three viewports in both themes. |

Backend testing is a different world (PostgreSQL, Testcontainers, the OSS smoke gate) and
lives in [AGENTS.md](../../../AGENTS.md) under "Test Notes".

## Vitest

`pnpm --dir web test` regenerates the API client first, then runs the suite. Tests are
colocated: `Foo.tsx` → `Foo.test.tsx`, `format.ts` → `format.test.ts`.

**Query the way an operator would.** `getByRole`, `getByLabelText`, `getByText`. Not
`getByTestId`, and never a class selector: `.bg-surface` is a token that will be renamed, and
a test that breaks on a restyle teaches everyone to stop trusting the suite.

**Mock the network boundary, nothing inside it.** The page tests spy on the transport and let
the real hooks, query keys, formatters, and derivations run:

```tsx
vi.spyOn(apiClient, "apiFetch").mockImplementation(async (input) => {
  const url = String(input)
  if (url.startsWith("/v1/models")) return CATALOG
  …
})
```

Mocking `useModels` or `formatCost` instead hides exactly the regressions worth catching: a
changed query key, a loading state nobody renders, a formatter that rounds wrong. There is no
`vi.mock("@/shared/api/hooks")` anywhere in this tree, and adding the first one needs a reason
in the diff.

**Render what the app renders.** A component that reads the URL needs a real router:
`withRouter` / `renderWithRouter` from `src/tests/router.tsx`. The router resolves its first
location asynchronously, so `await renderWithRouter(...)` or `flushRouter()` before asserting.
`src/tests/providers.tsx` re-exports the real provider tree for the tests that need it, and it
is the only module allowed to import `@/app`.

**Build fixtures from `src/tests/fixtures.ts`.** The builders fill a whole shape, which
matters because several code paths branch on `undefined` rather than zero
(`billedTokenTotal`, the share-card caveats): a hand-rolled partial fixture can pass a test
that the real response would fail.

**Drive with `userEvent`** and assert on what the operator sees, not on component internals.

**Wait on the event, not the clock.** `findBy*` and `waitFor` resolve the instant the DOM
changes; their timeout is a ceiling, not a sleep. Two habits that follow:

- Await the content, not its container. A wrapper can commit before its children do, so
  `await findByRole("tabpanel")` then a synchronous `getByText` inside it is a race. Await the
  text too.
- **A per-assertion `{ timeout: 5000 }` is a review blocker.** It hides which wait was slow.
  If the environment genuinely needs more headroom, raise it in one place
  (`configure({ asyncUtilTimeout })` in `src/tests/setup.ts`) and say why.

**Every test file is self-contained.** Vitest runs files in parallel across workers, so a
global one file leaves modified is a failure in another file that only reproduces at full
suite size:

- Restore any global you override (`window.location`, `matchMedia`, `localStorage`) in
  `afterEach`, and set `configurable: true` on every `Object.defineProperty` so the next test
  can redefine it.
- `vi.clearAllMocks()` and `localStorage.clear()` in `beforeEach`, not once at the top.
- `vi.useFakeTimers()` is always paired with `vi.useRealTimers()` in `afterEach`.
- Heavy polyfills go in the file that needs them. `src/tests/setup.ts` carries only what is
  universal (the jsdom gaps: `ResizeObserver`, `scrollTo`, object URLs).

**Keep test files small.** Vitest gives one file to one worker, so a 2,000-line file is the
suite's critical path while other workers idle, and `ActivityPage.test.tsx` is currently
exactly that. Split by concern (`Page.test.tsx`, `Page.deletion.test.tsx`,
`Page.filters.test.tsx`) when a file grows several independent `describe` blocks or needs
different mock setups per block.

## Playwright: behavioral

`pnpm --dir web run e2e` builds the bundle and boots a real gateway against a throwaway SQLite
database (`e2e/serve.sh`). Three ordered projects share that one database, so a spec scopes
itself to the rows it owns rather than to a global count, and an open react-aria combobox
popover `aria-hidden`s the rest of the page, so `dismissComboBox` runs before asserting
anything outside it. `playwright.config.ts` carries the rest.

## Playwright: screenshots

`e2e/screenshots/` is the visual-regression suite. Each spec is captured by six projects,
three viewports (1920×1080, 1280×800, 390×844) times both themes, so one entry covers a page
at every size and in both palettes. The theme is seeded into localStorage before the first
navigation (`e2e/screenshots/fixtures.ts`) so the pre-paint script in `index.html` applies it
on the first frame, and `colorScheme` is set to match underneath it.

**Adding a page means adding an entry.** A route in `WORKSPACE_ROUTES` in
`authenticated.spec.ts` is one line and buys six captures. A page with no entry is a page
whose mobile and dark rendering nobody checks.

What the harness already handles, so you do not work around it: `fullPage` captures,
`animations: "disabled"`, the caret hidden, fonts awaited, and masks over the two things that
are not reproducible (recharts, which animates on mount with no way to disable it from a test,
and any relative timestamp). If you find a third source of noise, mask it in `fixtures.ts`
with a comment, rather than loosening the pixel threshold for everything.

**Baselines are Linux PNGs produced by CI**, committed under
`e2e/screenshots/__snapshots__/<project>/`. A macOS capture renders fonts differently, so a
local run reports diffs that mean nothing: use it to check a page renders, not to judge a
diff, and do not commit what it writes. To obtain baselines for a new page, push the branch
and let the `screenshots` job run: it captures with `--update-snapshots=missing`, then fails
the "committed baselines are up to date" check with the new files attached as the
`screenshot-baselines` artifact. Download it, commit the PNGs, push again.

An intended visual change is the same loop with the changed files replaced rather than added.
Review the diff images in the artifact before committing: a baseline updated without looking
is a regression that has been made official.
