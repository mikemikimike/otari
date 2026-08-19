import {
  FiActivity,
  FiBarChart2,
  FiBox,
  FiCode,
  FiCreditCard,
  FiDollarSign,
  FiGlobe,
  FiGrid,
  FiHome,
  FiKey,
  FiLayers,
  FiRepeat,
  FiServer,
  FiShield,
  FiSliders,
  FiTag,
  FiTool,
  FiUsers,
} from "react-icons/fi"
import {
  OVERLAY_NAV_SECTIONS,
  OVERLAY_ORG_NAV_SECTIONS,
} from "./overlaySections"
import type { NavItem, NavSection } from "./types"

/**
 * The sidebar the base build ships, and the only place a destination is
 * declared.
 *
 * Sections render in this order. The index leads, alone and unlabeled, because
 * it is the rail's destination rather than a member of a category: it is where
 * the sidebar puts you back, not one of the places you go from it. The three
 * below it are the design's: "Observe" is where you look (the request log and
 * the usage rollups over it), "Gateway" is what the gateway serves (models, the
 * policies that route over them, and the tools it can call), and "Access" is who
 * may call it (keys, the upstream credentials those keys spend, and the
 * workspace's roster).
 *
 * Each entry declares its own gating, and the three axes are independent:
 * `surface` (does this deployment host it), `capability` (is it entitled), and
 * `flag` (is its rollout on). The sidebar composes them as AND. Hiding a link
 * is a convenience and never an authorization; the server still authorizes
 * every request the page behind it makes.
 */
const BASE_NAV_SECTIONS = [
  {
    // Headingless on purpose, and the one section in this rail that is. A label
    // over a single row would read as a category with one member, and the index
    // is not a category: it is the row every other row is a departure from. The
    // gap the shell already puts between sections is what separates it.
    id: "index",
    items: [
      // Ungated on every axis: the index is the deployment's own front page and
      // reads whatever it is allowed to.
      { to: "/", label: "Overview", icon: FiHome },
    ],
  },
  {
    id: "observe",
    label: "Observe",
    items: [
      // Both read /v1/usage, which is why they name the surface rather than
      // themselves: a deployment that does not host usage loses both.
      {
        to: "/activity",
        label: "Activity",
        surface: "usage",
        icon: FiActivity,
      },
      { to: "/usage", label: "Usage", surface: "usage", icon: FiBarChart2 },
    ],
  },
  {
    id: "gateway",
    label: "Gateway",
    items: [
      { to: "/models", label: "Models", surface: "models", icon: FiLayers },
      // Deliberately not tagged `capability: "routing"`, though otari.ai's
      // registry tags its own Routing item that way. ARCHITECTURE.md's
      // capability lines mark the routing split (how much is core base, how
      // much an overlay adapter) **provisional**, and say it is a decision for
      // the maintainers rather than something a contributor assumes. Tagging
      // this entry would assume it, and would withhold nothing today either
      // way, since the base grants what it ships. Add the tag when the split is
      // decided, together with its name in `BASE_CAPABILITIES`.
      {
        to: "/routing",
        label: "Routing",
        surface: "routing",
        icon: FiRepeat,
        // Policies and Guardrails as the navigation prototype groups them. The
        // prototype's third entry, Aliases, is deliberately absent: this
        // dashboard lists an alias as the one-target policy it is, in the same
        // table (see `RoutingPage`), so `/aliases` is a compatibility redirect
        // onto `/routing` rather than a destination. Linking it would give the
        // group two entries for one page, and the second could never highlight.
        // It comes back if and when Routing grows a separate alias view.
        children: [
          { to: "/routing", label: "Policies", icon: FiRepeat },
          {
            to: "/tools/guardrails",
            label: "Guardrails",
            icon: FiShield,
            // Grouped with Routing, served by the tools surface.
            surface: "tools",
          },
        ],
      },
      {
        to: "/tools",
        label: "Tools",
        surface: "tools",
        icon: FiTool,
        // Two of the three services the page configures; Guardrails is grouped
        // under Routing, where the prototype puts it. The prototype lists MCP
        // servers here too, and the gateway has no MCP server registry to
        // manage (only per-request config a caller passes in, plus two safety
        // toggles on Settings), so it is left out rather than linked to an
        // empty page.
        children: [
          { to: "/tools/web-search", label: "Web search", icon: FiGlobe },
          {
            to: "/tools/code-execution",
            label: "Code execution",
            icon: FiCode,
          },
        ],
      },
    ],
  },
  {
    id: "access",
    label: "Access",
    items: [
      { to: "/keys", label: "API keys", surface: "keys", icon: FiKey },
      // "Providers", not "Provider credentials": the page manages the
      // credential *and* the instance it belongs to, the rail has one line for
      // it, and a two-word label is what the rest of this group reads like.
      {
        to: "/providers",
        label: "Providers",
        surface: "providers",
        icon: FiBox,
      },
      // The selected workspace's roster, not the organization's. The
      // organization roster is "Members & roles" in the other context, and the
      // two pages cross-link, which is the distinction the prototype draws.
      {
        to: "/members",
        label: "Members",
        surface: "workspaces",
        icon: FiUsers,
      },
    ],
  },
] as const satisfies readonly NavSection[]

/**
 * The organization context: what belongs to the tenant rather than to one
 * workspace inside it.
 *
 * Reached from the sidebar footer and left by the "Back to" link at its top,
 * so the two contexts never render together. Gated on the caller managing the
 * organization, which in a standalone deployment is always true: there is one
 * session, the local operator, and it owns the organization the gateway
 * provisioned for itself. The gate is written anyway because it is the thing
 * that becomes load-bearing the moment per-user sign-in lands (otari-ai#1716).
 *
 * Four of the design's rows are destinations this gateway does not serve:
 * Billing, Gateways, the organization's own provider credentials, and the
 * organization guardrail ceiling. Each is **declared and gated on a surface the
 * standalone bootstrap does not report** (`STANDALONE_SURFACES` in
 * `src/gateway/api/routes/bootstrap.py` is that list), so the row is absent here
 * and present on a deployment that serves it, and a group whose every row is
 * gated drops entirely, heading included.
 *
 * The surface axis rather than the capability one, and that is a constraint
 * rather than a preference: `registry.test.ts` requires every capability a base
 * entry names to be in `BASE_CAPABILITIES`, that is, to be granted, so a
 * capability gate cannot express "declared but not served" without relaxing that
 * invariant. A surface gate says exactly this and needs no test change.
 *
 * Two of the four have a page on the *workspace* rail that looks like them and
 * is not: `/providers` is this process's credentials, and `/tools/guardrails` is
 * what this process refuses. The organization copies would be a tenant-wide
 * credential set and a ceiling over every workspace, which are different tables
 * behind different endpoints. Pointing the organization rows at the workspace
 * pages would put one destination on both rails, which `navContextForPath`
 * cannot express and `registry.test.ts` forbids.
 */
const ORGANIZATION_NAV_SECTIONS = [
  {
    id: "org-people",
    label: "People & access",
    items: [
      {
        to: "/organization/members",
        label: "Members & roles",
        surface: "organizations",
        icon: FiUsers,
      },
      // Absent from the design, which folds per-user spend into "Spend &
      // budgets". Kept because a budget names a `users` row, so this is the only
      // place a budget is attached to anything. It sits beside the members
      // rather than beside the budgets it feeds, because what the page edits is
      // an identity: the two identity tables have not merged yet (M4), and this
      // row stops being a destination when they do.
      { to: "/users", label: "Users", surface: "users", icon: FiUsers },
      // The organization's own upstream credentials, which is a different table
      // from the workspace rail's `/providers`: over there a credential belongs
      // to the process, here it would belong to the tenant. This gateway has only
      // the first, so the row is declared and gated off. See the note below.
      {
        to: "/organization/provider-keys",
        label: "Providers",
        surface: "organization_providers",
        icon: FiBox,
      },
      // Absent from the design, which switches workspace from the scope menu and
      // has no list page. Kept because this is the only place a workspace is
      // renamed, deleted, or has its roster read, and the scope menu offers none
      // of that.
      {
        to: "/workspaces",
        label: "Workspaces",
        surface: "workspaces",
        icon: FiGrid,
      },
    ],
  },
  {
    id: "org-money",
    label: "Cost & billing",
    items: [
      {
        to: "/budgets",
        label: "Spend & budgets",
        surface: "budgets",
        icon: FiDollarSign,
      },
      {
        to: "/organization/billing",
        label: "Billing",
        surface: "billing",
        icon: FiCreditCard,
      },
      // Tenant-scoped in fact as well as in the design: a rate applies to every
      // workspace and every key in the deployment. The catalog had no home
      // before — its refresh flow sat in the gateway's runtime Settings next to
      // the master key — so this is where it lives, while one model's rate stays
      // on Models, beside the model it prices.
      {
        to: "/organization/pricing",
        label: "Model pricing",
        surface: "settings",
        icon: FiTag,
      },
    ],
  },
  {
    id: "org-gateway",
    label: "Gateway",
    items: [
      // The organization's guardrail ceiling, which is not the workspace rail's
      // `/tools/guardrails`: that page configures what this process refuses, and
      // this one would cap what any workspace under the tenant may allow.
      {
        to: "/organization/guardrails",
        label: "Guardrails",
        surface: "organization_guardrails",
        icon: FiShield,
      },
      {
        to: "/organization/gateways",
        label: "Gateways",
        surface: "gateways",
        icon: FiServer,
      },
    ],
  },
  {
    id: "org-general",
    label: "General",
    items: [
      {
        to: "/organization",
        label: "Org settings",
        surface: "organizations",
        icon: FiSliders,
      },
      // No slot in the design, which has no gateway of its own to configure: this
      // is the process's runtime settings (the master key, the safety toggles,
      // the defaults), and it is the tenant's in the only sense that matters here,
      // because the tenant is the deployment.
      {
        to: "/settings",
        label: "Settings",
        surface: "settings",
        icon: FiSliders,
      },
    ],
  },
] as const satisfies readonly NavSection[]

/**
 * Compose the base sections with an overlay build's contributions.
 *
 * Base first, then overlay, so an overlay appends its own sections without
 * reordering the base sidebar.
 */
export function composeNavSections(
  base: readonly NavSection[],
  overlay: readonly NavSection[],
): readonly NavSection[] {
  return [...base, ...overlay]
}

/**
 * The composed workspace sidebar.
 *
 * This build appends nothing, so it is the base sections alone.
 */
export const NAV_SECTIONS: readonly NavSection[] = composeNavSections(
  BASE_NAV_SECTIONS,
  OVERLAY_NAV_SECTIONS,
)

/**
 * The composed organization sidebar.
 *
 * Composed the same way the workspace rail is, and for the same reason: Billing
 * is the canonical overlay-only capability (ARCHITECTURE.md's capability table)
 * and it belongs on this rail, so an overlay that could only contribute to the
 * workspace one would have to edit this file to register it, which is what
 * cardinal rule 6 rules out. This build appends nothing.
 */
export const ORG_NAV_SECTIONS: readonly NavSection[] = composeNavSections(
  ORGANIZATION_NAV_SECTIONS,
  OVERLAY_ORG_NAV_SECTIONS,
)

/**
 * Every registered entry, across both contexts.
 *
 * Flattened over both because this is what answers "which entry is this
 * pathname", and a route is gated the same way whichever sidebar links to it.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  ...NAV_SECTIONS,
  ...ORG_NAV_SECTIONS,
].flatMap((section) => section.items)

/**
 * Every nested destination, paired with the entry it is gated by.
 *
 * A child has no gating of its own, so `navItemForPath` has to answer with the
 * parent: that is what the shell reads to decide whether the route is served
 * and what to call it when it is not.
 */
const NAV_CHILD_PARENTS: ReadonlyMap<string, NavItem> = new Map(
  NAV_ITEMS.flatMap((item) =>
    (item.children ?? []).map(
      (child) =>
        [
          child.to,
          // The parent, so the sidebar still highlights the group this belongs
          // to, but carrying the child's own surface when it declares one.
          child.surface ? { ...item, surface: child.surface } : item,
        ] as const,
    ),
  ),
)

/** Where a destination lives: the workspace sidebar, or the organization one. */
export type NavContext = "workspace" | "organization"

const ORG_PATHS: readonly string[] = ORG_NAV_SECTIONS.flatMap((section) =>
  section.items.map((item) => item.to),
)

/**
 * What to call the destination at this pathname, as a breadcrumb would.
 *
 * Distinct from `navItemForPath`, which answers with the entry that *gates* a
 * path: for a nested destination that is the parent, so it would name
 * `/tools/web-search` "Tools". A breadcrumb wants the leaf.
 */
export function navLabelForPath(pathname: string): string | undefined {
  const child = NAV_ITEMS.flatMap((item) => item.children ?? []).find(
    (one) => one.to === pathname,
  )
  return child?.label ?? navItemForPath(pathname)?.label
}

/**
 * Which sidebar a pathname belongs under.
 *
 * Derived from the registry rather than from a path prefix, because the two
 * contexts do not split cleanly by URL: `/workspaces` and `/settings` are
 * organization destinations whose paths look like anything else, and
 * `/members` is a workspace one that sits directly under the root. Anything
 * unregistered (the guide, the 404 splat) belongs to the workspace context,
 * which is the one the shell opens in.
 */
export function navContextForPath(pathname: string): NavContext {
  const item = navItemForPath(pathname)
  if (!item) return "workspace"
  return ORG_PATHS.includes(item.to) ? "organization" : "workspace"
}

/**
 * The registry entry a pathname belongs to, if any.
 *
 * What lets the shell answer a gated-off destination with "not available here"
 * rather than rendering a page whose every request the server will refuse: the
 * link is gone from the sidebar, but a bookmark, a shared URL, or a gateway
 * restarted into another mode can still land on the route.
 *
 * A path matches its entry exactly or as a prefix, so a future child route
 * (`/routing/new`) inherits its parent's gating. The index is matched exactly
 * only; as a prefix it would claim every path in the dashboard.
 *
 * **An exact match wins over a prefix match**, and the two passes are why: with
 * a single scan, `/organization/members` would resolve to `/organization`,
 * which is registered ahead of it. The gating would still be right (both name
 * the same surface), but everything else that asks "which entry is this page"
 * would be wrong: the shell titles its gated-off panel from the entry it gets
 * back, and the sidebar highlights it.
 *
 * An unregistered path (`/docs`, the 404 splat) has no entry and is therefore
 * never gated, which is right: the registry governs the destinations it
 * declares and nothing else.
 */
export function navItemForPath(pathname: string): NavItem | undefined {
  const exact = NAV_ITEMS.find((item) => pathname === item.to)
  if (exact) return exact
  // A nested destination answers with the entry that gates it, so a child route
  // is never treated as unregistered (and therefore ungated).
  const child = NAV_CHILD_PARENTS.get(pathname)
  if (child) return child
  // Longest prefix, not first: `/organization/members/x` is under both
  // `/organization` and `/organization/members`, and the deeper entry is the
  // one that describes it. Ordering the scan rather than the registry, because
  // the registry's order is the sidebar's.
  return NAV_ITEMS.filter(
    (item) => item.to !== "/" && pathname.startsWith(`${item.to}/`),
  ).sort((a, b) => b.to.length - a.to.length)[0]
}

/** A section that has at least one visible entry, paired with those entries. */
export interface VisibleNavSection {
  section: NavSection
  items: readonly NavItem[]
}

/**
 * The sections worth rendering, with the entries worth rendering in them.
 *
 * Filters before the caller indexes, which is the point: the sidebar draws its
 * divider and top margin above every section *after* the first, so keying that
 * off the registry index would leave a stray top border above the first visible
 * group once a section ahead of it empties out. Not reachable in this build,
 * where the index section is ungated and so always renders first, and reachable
 * as soon as an overlay contributes a section or a gated one empties, which is
 * the whole point of the seam. `otari-ai/frontend`'s sidebar keys off rendered
 * position for the same reason.
 *
 * A section with no visible entry is dropped whole, heading included: an empty
 * heading over nothing reads worse than no heading.
 */
export function visibleNavSections(
  sections: readonly NavSection[],
  isVisible: (item: NavItem) => boolean,
): VisibleNavSection[] {
  return sections
    .map((section) => ({ section, items: section.items.filter(isVisible) }))
    .filter(({ items }) => items.length > 0)
}
