/**
 * Where you were on each rail, so crossing between them does not lose your place.
 *
 * The design's `Interaction · A ⇄ B` note is explicit about this: pressing
 * "Organization" should open the organization page you were last on, and "Back
 * to {Workspace}" should return you to the workspace page you left, rather than
 * both journeys resetting to a fixed landing. The shell used to send you to
 * `/organization/members` and `/` every time, which treats a rail as a place you
 * arrive at rather than one you were already working in.
 *
 * Three things keep a stored value honest. It is **written only for a registered
 * destination**, and read back through the same check, so a stale entry left by
 * an older build, a hand-edited localStorage, or a route that has since been
 * removed is dropped rather than navigated to. It is **written and read only for
 * a destination this deployment still shows**, which is a separate question: a
 * gated-off route is still registered and still reachable by URL, so without
 * that check the resume link lands on the shell's "not available here" panel,
 * and the visit that saw the panel is recorded as somewhere worth returning to.
 * And because the first check resolves against the registry, what comes back is
 * a `NavPath`: the caller gets something a `Link` will accept, not a string it
 * has to cast.
 *
 * It lives here rather than in `shared/helpers` — where `otari-ai` keeps its
 * counterpart — because deciding which rail a path belongs to is
 * `navContextForPath`'s job, and `src/shared` may not import `src/app`. Over
 * there the same decision is a pair of path-prefix regexes, which this
 * dashboard's URLs do not support: `/workspaces` and `/settings` are
 * organization destinations that look like anything else.
 */

import { NAV_ITEMS, type NavContext, navContextForPath } from "./registry"
import type { NavChild, NavItem, NavPath } from "./types"

const STORAGE_KEYS: Record<NavContext, string> = {
  workspace: "otari.dashboard.lastWorkspaceLocation",
  organization: "otari.dashboard.lastOrganizationLocation",
}

/**
 * A place to return to.
 *
 * The destination only, not its filters. The design asks for the page you were
 * last on, and this dashboard keeps every filter in the URL: restoring those too
 * would drop you back into a twelve-month usage window or a model filter you set
 * days ago, which reads as the app having lost your place rather than kept it.
 */
export interface RememberedLocation {
  to: NavPath
}

/** A registered destination, with the entries that declare its gating. */
interface Destination {
  to: NavPath
  item: NavItem
  child?: NavChild
}

/**
 * The registered destination at this pathname, if it is one.
 *
 * Exact matches only, leaves and nested children alike. A deeper path
 * (`/organization/members/abc`) resolves to no destination and is therefore not
 * remembered, which is the right trade: the design asks for the page you were
 * on, and a detail view's id may not exist by the time you come back.
 *
 * The entries come back with the path because the gates are declared on them,
 * and a nested destination may carry a surface of its own (Guardrails is grouped
 * under Routing and served by the tools surface), so `isReachable` needs both.
 */
function destinationAt(pathname: string): Destination | undefined {
  for (const item of NAV_ITEMS) {
    if (item.to === pathname) return { to: item.to, item }
    for (const child of item.children ?? []) {
      if (child.to === pathname) return { to: child.to, item, child }
    }
  }
  return undefined
}

/**
 * Whether this deployment still shows the destination.
 *
 * The same composition the sidebar draws with: the entry's own three gates, and
 * for a nested destination the parent's gates with the child's surface
 * substituted, which is what the shell's own group does. Registered is not the
 * same as visible, and the two resume links are where that difference would land
 * on a panel instead of a page.
 */
function isReachable(
  found: Destination,
  isVisible: (item: NavItem) => boolean,
): boolean {
  if (!isVisible(found.item)) return false
  const surface = found.child?.surface
  return surface === undefined || isVisible({ ...found.item, surface })
}

/**
 * Record the current location under the rail it belongs to.
 *
 * Called on every navigation, and a no-op for anything that is not a registered
 * destination, so the guide and the 404 splat never become somewhere to return
 * to. Also a no-op for a destination this deployment gates off, which a URL can
 * still reach and which answers with the "not available here" panel: the page
 * someone was just told they cannot have is not the page to send them back to.
 * Both rails are recorded the same way, which is what makes the memory right
 * however you left: a link on a page and a bookmark update it as surely as the
 * control that crosses the rail does.
 */
export function rememberLocation(
  pathname: string,
  isVisible: (item: NavItem) => boolean,
): void {
  const found = destinationAt(pathname)
  if (!found || !isReachable(found, isVisible)) return
  try {
    window.localStorage.setItem(
      STORAGE_KEYS[navContextForPath(pathname)],
      found.to,
    )
  } catch {
    // Storage can throw when it is disabled (blocked cookies, private mode).
    // Losing the memory costs a landing page, so it is not worth an error path.
  }
}

/** Where you last were on this rail, if it is still somewhere you can go. */
export function lastLocation(
  context: NavContext,
  isVisible: (item: NavItem) => boolean,
): RememberedLocation | undefined {
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(STORAGE_KEYS[context])
  } catch {
    return undefined
  }
  if (!raw) return undefined
  // Re-validated on the way out, not just on the way in: a destination that has
  // been removed, moved to the other rail, or gated off since it was stored
  // would otherwise send someone to the shell's "not available here" panel, or
  // to the wrong rail. The gate is the half a write-time check cannot cover on
  // its own, because a gateway restarted against a config that reports fewer
  // surfaces changes the answer under an entry already written.
  const found = destinationAt(raw)
  if (!found || navContextForPath(found.to) !== context) return undefined
  if (!isReachable(found, isVisible)) return undefined
  return { to: found.to }
}
