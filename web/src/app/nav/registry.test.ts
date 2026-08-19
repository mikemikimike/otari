import { describe, expect, it } from "vitest"

import { BASE_CAPABILITIES } from "@/shared/hooks/useEntitlements"

import {
  composeNavSections,
  NAV_ITEMS,
  NAV_SECTIONS,
  navContextForPath,
  navItemForPath,
  ORG_NAV_SECTIONS,
  visibleNavSections,
} from "./registry"
import type { NavItem, NavSection } from "./types"

describe("nav registry", () => {
  it("exposes the base sections in display order", () => {
    expect(NAV_SECTIONS.map((section) => section.id)).toEqual([
      "observe",
      "gateway",
      "access",
    ])
    // No unlabeled group: the index sits under Observe, which is where the
    // navigation design puts it, so every section in this rail has a heading.
    expect(NAV_SECTIONS.every((section) => section.label)).toBe(true)
  })

  it("exposes the organization sections in display order", () => {
    // The second rail, reached from the sidebar footer. Its own registry, so
    // its order is asserted separately from the workspace one's.
    expect(ORG_NAV_SECTIONS.map((section) => section.id)).toEqual([
      "org-people",
      "org-money",
      "org-gateway",
      "org-general",
    ])
  })

  it("declares every destination the standalone dashboard serves", () => {
    // The whole list, not a sample: the registry is now the only place a
    // destination exists, so an entry dropped in a refactor is a page that
    // silently stops being reachable.
    // Both rails, because NAV_ITEMS is what answers "which entry is this
    // pathname" and a route is gated the same way whichever sidebar links it.
    expect(NAV_ITEMS.map((item) => item.label)).toEqual([
      "Overview",
      "Activity",
      "Usage",
      "Models",
      "Routing",
      "Tools",
      "API keys",
      "Providers",
      "Members",
      "Members & roles",
      "Providers",
      "Workspaces",
      "Spend & budgets",
      "Users",
      "Billing",
      "Guardrails",
      "Gateways",
      "Org usage",
      "Org settings",
      "Settings",
    ])
  })

  it("puts each destination on exactly one rail", () => {
    // The two registries are concatenated into NAV_ITEMS, so a path declared on
    // both would resolve to whichever came first and be gated by that one.
    const paths = NAV_ITEMS.map((item) => item.to)
    expect(paths).toEqual([...new Set(paths)])
  })

  it("sorts a pathname onto the rail that declares it", () => {
    // Not a URL-prefix rule: /workspaces and /settings are organization
    // destinations whose paths look like anything else, and /members is a
    // workspace one directly under the root.
    expect(navContextForPath("/members")).toBe("workspace")
    expect(navContextForPath("/workspaces")).toBe("organization")
    expect(navContextForPath("/settings")).toBe("organization")
    expect(navContextForPath("/organization/members")).toBe("organization")
    // Unregistered paths open in the context the shell starts in.
    expect(navContextForPath("/docs")).toBe("workspace")
  })

  it("splits the tenancy pages across their two surfaces", () => {
    // The organization pages and the workspace pages are separate management
    // prefixes, so they gate separately: a deployment that served one without
    // the other would otherwise show links it refuses every request behind.
    const tenancy = ORG_NAV_SECTIONS.find(
      (section) => section.id === "org-people",
    )
    expect(tenancy?.items.map((item) => [item.label, item.surface])).toEqual([
      ["Members & roles", "organizations"],
      ["Providers", "organization_providers"],
      ["Workspaces", "workspaces"],
    ])
  })

  it("resolves a child route to its own entry, not to its parent's", () => {
    // The first nested pair in the registry, and the reason navItemForPath
    // makes two passes: /organization is registered ahead of
    // /organization/members and matches it as a prefix. The shell titles its
    // gated-off panel from whatever comes back, and the sidebar highlights it,
    // so the parent winning here is a page announcing itself as "General".
    expect(navItemForPath("/organization/members")?.label).toBe(
      "Members & roles",
    )
    expect(navItemForPath("/organization")?.label).toBe("Org settings")
  })

  it("resolves a deeper path to the deepest entry above it", () => {
    // Both /organization and /organization/members are prefixes of this, and
    // the deeper one is what describes it.
    expect(navItemForPath("/organization/members/abc")?.label).toBe(
      "Members & roles",
    )
  })

  it("still resolves an unregistered child route to its parent", () => {
    // The prefix pass is what a future child route (/routing/new) relies on to
    // inherit its parent's gating; only an exact match outranks it.
    expect(navItemForPath("/routing/new")?.label).toBe("Routing")
    expect(navItemForPath("/docs")).toBeUndefined()
  })

  it("points every entry at an absolute path", () => {
    for (const item of NAV_ITEMS) {
      expect(item.to.startsWith("/")).toBe(true)
    }
  })

  it("keeps Routing gated on its surface only", () => {
    // Pinned because the tag is a decision, not an omission: otari.ai gates its
    // own Routing item on `capability: "routing"`, so adding it here would look
    // like a merge fix rather than a call on a provisional split.
    const routing = NAV_ITEMS.find((item) => item.label === "Routing")
    expect(routing?.surface).toBe("routing")
    expect(routing?.capability).toBeUndefined()
  })

  it("leaves the index ungated on all three axes", () => {
    const overview = NAV_ITEMS.find((item) => item.label === "Overview")
    // The deployment's own front page: it reads whatever it is allowed to, so
    // gating it would leave a deployment with no landing page at all.
    expect(overview?.surface).toBeUndefined()
    expect(overview?.capability).toBeUndefined()
    expect(overview?.flag).toBeUndefined()
  })

  it("names the usage surface on both observability pages", () => {
    // Activity and Usage are two views over /v1/usage, so they gate together on
    // the surface rather than each on a name of its own.
    const observability = NAV_SECTIONS.find(
      (section) => section.id === "observe",
    )
    // The index leads the group and is deliberately ungated, so it is skipped:
    // the pair below it is what shares the surface.
    expect(
      observability?.items
        .filter((item) => item.label !== "Overview")
        .map((item) => item.surface),
    ).toEqual(["usage", "usage"])
  })

  it("gates no base entry on a capability or a flag", () => {
    // Neither axis has a base user yet. Routing is the one candidate for a
    // capability, and ARCHITECTURE.md marks that split provisional, so the tag
    // waits for the decision rather than anticipating it. Flags belong to
    // whoever is rolling something out, and the base ships none, so a flagged
    // base entry would be permanently hidden.
    expect(NAV_ITEMS.every((item) => item.capability === undefined)).toBe(true)
    expect(NAV_ITEMS.every((item) => item.flag === undefined)).toBe(true)
  })

  it("entitles every capability the base registry gates on", () => {
    // Vacuous while the assertion above holds, and deliberately kept: it arms
    // itself the moment someone adds the first tag. A base entry gated on a
    // capability the base build does not grant disappears from the sidebar of
    // every standalone gateway, and the two lists are maintained in different
    // files, which is exactly the pair a single commit forgets to update.
    for (const item of NAV_ITEMS) {
      if (item.capability === undefined) continue
      expect(BASE_CAPABILITIES).toContain(item.capability)
    }
  })

  it("gates every declared-but-unserved destination on a surface", () => {
    // The design's organization rail draws four rows this gateway has no endpoint
    // for. Each is declared so the rail matches on a deployment that does serve
    // them, and gated on a surface `STANDALONE_SURFACES` does not report so the
    // row is absent here. Pinned as the whole set, because the failure mode is
    // silent in both directions: a missing gate ships a link to a page that
    // cannot work, and a gate on a surface the bootstrap *does* report hides a
    // page that can.
    const unserved = new Map([
      ["/organization/provider-keys", "organization_providers"],
      ["/organization/billing", "billing"],
      ["/organization/guardrails", "organization_guardrails"],
      ["/organization/gateways", "gateways"],
    ])
    for (const [to, surface] of unserved) {
      expect(navItemForPath(to)?.surface).toBe(surface)
    }
    // And none of those surface names is one a standalone gateway reports, or the
    // gate would be decoration.
    const standalone = [
      "budgets",
      "keys",
      "models",
      "organizations",
      "providers",
      "routing",
      "settings",
      "tools",
      "usage",
      "users",
      "workspaces",
    ]
    for (const surface of unserved.values()) {
      expect(standalone).not.toContain(surface)
    }
  })

  it("appends overlay sections after the base sections", () => {
    const base: NavSection[] = [{ id: "base", items: [] }]
    const overlay: NavSection[] = [
      {
        id: "overlay-billing",
        items: [
          {
            to: "/settings",
            label: "Billing",
            icon: null,
            capability: "billing",
          },
        ],
      },
    ]
    expect(
      composeNavSections(base, overlay).map((section) => section.id),
    ).toEqual(["base", "overlay-billing"])
  })

  it("appends nothing in this build", () => {
    // The overlay tree lives in another repo; the seam here stays empty.
    expect(composeNavSections(NAV_SECTIONS, [])).toEqual(NAV_SECTIONS)
  })
})

describe("visibleNavSections", () => {
  const entry = (label: string, surface?: string): NavItem =>
    ({ to: "/", label, icon: null, surface }) as NavItem

  const sections: NavSection[] = [
    { id: "first", items: [entry("A", "a")] },
    { id: "second", items: [entry("B", "b"), entry("C", "c")] },
    { id: "third", items: [entry("D")] },
  ]

  const hosting =
    (...surfaces: string[]) =>
    (item: NavItem) =>
      item.surface === undefined || surfaces.includes(item.surface)

  it("keeps only the entries that pass, and drops a section left with none", () => {
    const visible = visibleNavSections(sections, hosting("b"))
    expect(visible.map(({ section }) => section.id)).toEqual([
      "second",
      "third",
    ])
    expect(visible[0].items.map((item) => item.label)).toEqual(["B"])
  })

  it("indexes by rendered position, not registry position", () => {
    // The sidebar draws a divider and a top margin above every section after
    // the first, so the first surviving section has to land at index 0. Keyed
    // off the registry index instead, a hidden section ahead of it would leave
    // a stray top border above the first visible group. Not reachable through
    // today's registry, where the ungated index section always renders first,
    // and reachable the moment an overlay contributes a section.
    const visible = visibleNavSections(sections, hosting("c"))
    expect(visible[0].section.id).toBe("second")
    expect(visible.findIndex(({ section }) => section.id === "second")).toBe(0)
  })

  it("returns nothing when every entry is gated away", () => {
    expect(visibleNavSections([sections[0]], hosting())).toEqual([])
  })

  it("keeps an entry that declares no gate at all", () => {
    const visible = visibleNavSections(sections, hosting())
    expect(visible.map(({ section }) => section.id)).toEqual(["third"])
  })
})

describe("navItemForPath", () => {
  it("matches a registered destination exactly", () => {
    expect(navItemForPath("/routing")?.label).toBe("Routing")
  })

  it("matches a child path to its parent entry", () => {
    // A future /routing/new inherits the gating of the destination it sits under
    // rather than escaping it by being unregistered.
    expect(navItemForPath("/routing/new")?.label).toBe("Routing")
  })

  it("matches the index only exactly", () => {
    expect(navItemForPath("/")?.label).toBe("Overview")
    // As a prefix, "/" would claim every path in the dashboard and gate the
    // whole shell on the index's (absent) gating.
    expect(navItemForPath("/keys")?.label).toBe("API keys")
  })

  it("returns nothing for a path the registry does not declare", () => {
    // The bundled guide and the 404 splat are not destinations, so they are
    // never gated.
    expect(navItemForPath("/docs")).toBeUndefined()
    expect(navItemForPath("/nope")).toBeUndefined()
  })
})
