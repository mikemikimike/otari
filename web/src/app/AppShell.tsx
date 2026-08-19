import { Button, Popover } from "@heroui/react"
import { Link, Outlet, useLocation } from "@tanstack/react-router"
import { clsx } from "clsx"
import type {
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  ReactNode,
  PointerEvent as ReactPointerEvent,
} from "react"
import { useCallback, useEffect, useRef, useState } from "react"
import { ConnectionStatus } from "@/app/ConnectionStatus"
import { AccountMenu } from "@/app/nav/AccountMenu"
import { Breadcrumbs } from "@/app/nav/Breadcrumbs"
import {
  NAV_SECTIONS,
  navContextForPath,
  navItemForPath,
  navLabelForPath,
  ORG_NAV_SECTIONS,
  visibleNavSections,
} from "@/app/nav/registry"
import { NAV_SECTION_HEADING_CLASS, navRowClass } from "@/app/nav/rowStyles"
import { TopBarActions } from "@/app/nav/TopBarActions"
import type { NavItem, NavPath } from "@/app/nav/types"
import { useNavVisibility } from "@/app/nav/useNavVisibility"
import { WorkspaceSwitcher } from "@/app/nav/WorkspaceSwitcher"
import { UpdatePrompt } from "@/app/UpdatePrompt"
import { PricingWarning } from "@/features/models/PricingWarning"
import { canManage } from "@/features/organization/roles"
import { useOrganizationContext } from "@/shared/api/hooks"
import { EmptyState } from "@/shared/components/ui"
import { useSelectedWorkspace } from "@/shared/hooks/SelectedWorkspace"

const MIN_SIDEBAR = 200
const MAX_SIDEBAR = 480
const DEFAULT_SIDEBAR = 264
const COLLAPSED_SIDEBAR = 72
const SIDEBAR_WIDTH_KEY = "otari.dashboard.sidebarWidth"
const SIDEBAR_COLLAPSED_KEY = "otari.dashboard.sidebarCollapsed"
const SIDEBAR_STEP = 16

// Below this width the sidebar's fixed footprint squashes page content, so it
// switches to an off-canvas drawer toggled from the header. Matches Tailwind's
// `md` breakpoint (the classes that hide the trigger and drawer chrome use `md:`).
const MOBILE_QUERY = "(max-width: 767px)"

const clampSidebar = (width: number) =>
  Math.min(MAX_SIDEBAR, Math.max(MIN_SIDEBAR, width))

function readIsMobile(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function")
    return false
  return window.matchMedia(MOBILE_QUERY).matches
}

function readStoredSidebarWidth(): number {
  if (typeof window === "undefined") return DEFAULT_SIDEBAR
  try {
    const raw = window.localStorage.getItem(SIDEBAR_WIDTH_KEY)
    const parsed = raw ? Number.parseInt(raw, 10) : Number.NaN
    return Number.isNaN(parsed) ? DEFAULT_SIDEBAR : clampSidebar(parsed)
  } catch {
    // Storage can throw when disabled (e.g. blocked cookies / private mode);
    // fall back to the default rather than white-screening the shell.
    return DEFAULT_SIDEBAR
  }
}

function readStoredCollapsed(): boolean {
  if (typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1"
  } catch {
    return false
  }
}

/**
 * One row of the rail, pointing at one destination.
 *
 * Shared by the leaves, a group's children, and a group that has collapsed to a
 * single child, so the three cannot drift: they are the same row with a
 * different indent and a different label.
 *
 * Collapsed, the label survives as the accessible name and as the tooltip,
 * because the visible text is what a sighted reader loses and the only thing an
 * assistive one had.
 */
function NavRowLink({
  to,
  label,
  icon,
  isActive,
  collapsed,
  nested,
  onNavigate,
}: {
  to: NavPath
  label: string
  icon?: ReactNode
  isActive: boolean
  collapsed?: boolean
  nested?: boolean
  onNavigate: () => void
}) {
  return (
    <Link
      to={to}
      // Exact, because the default is a prefix match: on /organization/members
      // that leaves `aria-current` on "Organization" as well as on the child.
      activeOptions={{ exact: true }}
      onClick={onNavigate}
      className={navRowClass({ isActive, collapsed, nested })}
      aria-label={collapsed ? label : undefined}
      title={collapsed ? label : undefined}
    >
      {icon}
      {collapsed ? null : (
        <span className="min-w-0 flex-1 truncate">{label}</span>
      )}
    </Link>
  )
}

/**
 * A sidebar entry with destinations nested under it, drawn the way the design
 * draws Routing and Tools: a row that expands rather than navigates, and
 * indented children below it.
 *
 * Open when the current route is one of its children, so arriving by URL shows
 * where you are rather than a collapsed group. Held in state after that, so
 * closing it stays closed while you read the page it opened.
 *
 * Three shapes, and which one it takes is decided by how many children survive
 * gating and whether the rail is collapsed:
 *
 * **One child** and it is not a group at all, but that child wearing the
 * parent's name and glyph. A disclosure that opens onto a single row asks for a
 * click to tell you nothing, and this is reachable: a deployment without the
 * tools surface leaves Routing holding only Policies.
 *
 * **Collapsed** and it is an icon that opens a flyout of the children. This is
 * the case the rail used to lose: the parent linked straight to its own page, so
 * Guardrails, Web search and Code execution had no collapsed affordance at all
 * and a bookmark was the only way back to them.
 */
function NavGroup({
  item,
  currentPath,
  onNavigate,
  isVisible,
  collapsed,
}: {
  item: NavItem
  currentPath: string
  onNavigate: () => void
  isVisible: (item: NavItem) => boolean
  collapsed: boolean
}) {
  // A child declaring its own surface is gated on it. Without this the field
  // was decoration: Guardrails is grouped under Routing but served by the tools
  // surface, so a deployment without that surface kept the link and landed on
  // the "not available here" panel.
  const children = (item.children ?? []).filter((child) =>
    child.surface ? isVisible({ ...item, surface: child.surface }) : true,
  )
  const holdsCurrent = children.some((child) => child.to === currentPath)
  const [open, setOpen] = useState(holdsCurrent)
  const [flyoutOpen, setFlyoutOpen] = useState(false)
  // Follows the route when navigation lands inside the group from elsewhere
  // (a link on a page, a bookmark), without fighting a manual close.
  const [lastHeld, setLastHeld] = useState(holdsCurrent)
  if (holdsCurrent !== lastHeld) {
    setLastHeld(holdsCurrent)
    if (holdsCurrent) setOpen(true)
  }

  const only = children.length === 1 ? children[0] : undefined
  if (only) {
    return (
      <NavRowLink
        to={only.to}
        label={item.label}
        icon={item.icon}
        isActive={currentPath === only.to}
        collapsed={collapsed}
        onNavigate={onNavigate}
      />
    )
  }

  if (collapsed) {
    return (
      <Popover isOpen={flyoutOpen} onOpenChange={setFlyoutOpen}>
        {/* HeroUI's Button, not a plain one: the popover wires its trigger
            through react-aria, and a bare <button> leaves it unopenable. */}
        <Button
          variant="ghost"
          aria-label={item.label}
          className={`${navRowClass({ isActive: holdsCurrent, collapsed: true })} w-auto!`}
        >
          {item.icon}
        </Button>
        <Popover.Content placement="right top">
          <Popover.Dialog
            aria-label={item.label}
            className="flex w-56 flex-col gap-0.5"
          >
            {/* Named, because the icon that opened this is the only other thing
                saying which group these belong to, and it is off to the side. */}
            <p className="flex min-h-8 items-center px-3 text-overline">
              {item.label}
            </p>
            {children.map((child) => (
              <NavRowLink
                key={child.to}
                to={child.to}
                label={child.label}
                isActive={currentPath === child.to}
                onNavigate={() => {
                  setFlyoutOpen(false)
                  onNavigate()
                }}
              />
            ))}
          </Popover.Dialog>
        </Popover.Content>
      </Popover>
    )
  }

  return (
    <div className={clsx("flex flex-col", open && "gap-0.5")}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={navRowClass({ isActive: holdsCurrent })}
      >
        {item.icon}
        <span className="min-w-0 flex-1 truncate text-left">{item.label}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          className={clsx(
            "h-4 w-4 shrink-0 transition-transform duration-150 motion-reduce:transition-none",
            open && "rotate-180",
          )}
        >
          <path
            d="M8 10l4 4 4-4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open
        ? children.map((child) => (
            <NavRowLink
              key={child.to}
              to={child.to}
              label={child.label}
              isActive={currentPath === child.to}
              // Indented past the parent's icon lane rather than repeating a
              // glyph, which is what marks the row as nested.
              nested
              onNavigate={onNavigate}
            />
          ))
        : null}
    </div>
  )
}

export function AppShell() {
  // Navigation is data: the shell renders whatever the registry declares and
  // decides visibility from the deployment, the entitlements, and the flags,
  // rather than each page asking what it is running against.
  const isVisible = useNavVisibility()
  const { pathname } = useLocation()
  // A gated-off destination is still reachable by bookmark or shared URL, so the
  // shell answers those with a panel instead of a page whose every request the
  // server would refuse. An unregistered path (the guide, the 404 splat) has no
  // entry and is never gated.
  const currentItem = navItemForPath(pathname)
  const routeIsGatedOff = currentItem !== undefined && !isVisible(currentItem)
  // Which of the two sidebars this path belongs under. The organization context
  // is a separate rail reached from the footer, not a section inside the
  // workspace one, so the two never render together.
  const navContext = navContextForPath(pathname)
  const inOrganization = navContext === "organization"
  // Filtered before it is indexed, so the divider and top margin below key off
  // the first *rendered* section rather than the first registered one.
  const visibleSections = visibleNavSections(
    inOrganization ? ORG_NAV_SECTIONS : NAV_SECTIONS,
    isVisible,
  )
  const organization = useOrganizationContext()
  const { selected: selectedWorkspace } = useSelectedWorkspace()
  // Always true in a standalone deployment, where the one session is the local
  // operator and it owns the organization the gateway provisioned for itself.
  // Written anyway because it becomes load-bearing the moment per-user sign-in
  // lands (otari-ai#1716), and because an overlay build can already be reached
  // by someone who is not an admin.
  // Fails open when the context errors rather than resolving false: Users,
  // budgets and settings are reachable only through this entry, the routes still
  // work by URL, and the server authorizes every request behind it regardless.
  // Hiding the way there because one query failed strands three destinations.
  const managesOrganization =
    canManage(organization.data) || organization.isError

  const asideRef = useRef<HTMLElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const [sidebarWidth, setSidebarWidth] = useState<number>(
    readStoredSidebarWidth,
  )
  const [collapsed, setCollapsed] = useState<boolean>(readStoredCollapsed)
  const [resizing, setResizing] = useState(false)
  const [isMobile, setIsMobile] = useState<boolean>(readIsMobile)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  // Track the mobile breakpoint so the sidebar can render as an off-canvas
  // drawer below it and as the resizable rail above it. Closing the drawer when
  // the viewport grows past the breakpoint keeps a stale open state from leaving
  // a fixed overlay stranded over the desktop layout.
  useEffect(() => {
    if (
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    )
      return
    const query = window.matchMedia(MOBILE_QUERY)
    const onChange = (event: MediaQueryListEvent) => {
      setIsMobile(event.matches)
      if (!event.matches) setMobileNavOpen(false)
    }
    // Safari < 14 (and some older engines) only expose the deprecated
    // addListener/removeListener; fall back to it so the shell doesn't throw.
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", onChange)
      return () => query.removeEventListener("change", onChange)
    }
    query.addListener(onChange)
    return () => query.removeListener(onChange)
  }, [])

  // Escape closes the drawer, matching the dismissible-overlay convention.
  useEffect(() => {
    if (!mobileNavOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileNavOpen(false)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [mobileNavOpen])

  // Focus management for the mobile drawer, which is a modal overlay: move focus
  // into it when it opens and restore focus to the toggle when it closes, so
  // keyboard and screen-reader users are neither stranded inside a hidden panel
  // nor dropped back to the top of the document. The isMobile guard means a
  // breakpoint change to desktop (which also closes the drawer) never yanks focus
  // to the now-hidden toggle.
  useEffect(() => {
    if (!isMobile) return
    if (mobileNavOpen) {
      asideRef.current?.focus()
    } else if (asideRef.current?.contains(document.activeElement)) {
      toggleRef.current?.focus()
    }
  }, [isMobile, mobileNavOpen])

  useEffect(() => {
    const id = window.setTimeout(() => {
      try {
        window.localStorage.setItem(
          SIDEBAR_WIDTH_KEY,
          String(Math.round(sidebarWidth)),
        )
      } catch {
        // Ignore storage errors; the width still applies for this session.
      }
    }, 200)
    return () => window.clearTimeout(id)
  }, [sidebarWidth])

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0")
    } catch {
      // Ignore storage errors; the collapse state still applies for this session.
    }
  }, [collapsed])

  const startResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.currentTarget.setPointerCapture(event.pointerId)
      setResizing(true)
    },
    [],
  )

  const moveResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
    const left = asideRef.current?.getBoundingClientRect().left ?? 0
    setSidebarWidth(clampSidebar(event.clientX - left))
  }, [])

  const endResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    setResizing(false)
  }, [])

  // Move focus (and scroll) to the page's main region, past the header and the
  // whole nav. A plain anchor to `#main-content` can't do this: the router runs
  // on hash history, so that href would register as a route change. Focusing
  // the ref directly keeps the route intact; `main` carries tabIndex={-1} so it
  // can accept programmatic focus without joining the tab order.
  const skipToMain = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>) => {
      event.preventDefault()
      // Focusing the region also scrolls it into view, so no separate scroll call.
      mainRef.current?.focus()
    },
    [],
  )

  const nudgeResize = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault()
        setSidebarWidth((width) => clampSidebar(width - SIDEBAR_STEP))
      } else if (event.key === "ArrowRight") {
        event.preventDefault()
        setSidebarWidth((width) => clampSidebar(width + SIDEBAR_STEP))
      }
    },
    [],
  )

  const width = collapsed ? COLLAPSED_SIDEBAR : sidebarWidth
  // The collapse rail and resize handle are desktop-only affordances; on mobile
  // the drawer always shows the full-width, labeled nav.
  const effectiveCollapsed = isMobile ? false : collapsed
  // While the mobile drawer is open, the page behind it is inert: that is what
  // keeps an AT virtual cursor and Tab out of controls nobody can see. The top
  // bar is deliberately not included, because the control that closes the drawer
  // is in it, and the trail beside that control is the one thing worth reading
  // while the drawer is open.
  const backgroundInert = isMobile && mobileNavOpen ? true : undefined

  return (
    <div
      className={clsx(
        "relative flex h-full flex-col overflow-hidden",
        resizing && "cursor-col-resize select-none",
      )}
    >
      {/* The first tab stop: a keyboard user can jump straight to the page body
          instead of tabbing through the whole nav on every route. Visually hidden
          until focused, then pinned top-left over the header (z above it). Goes
          inert with the drawer (like the header/main it targets) so it is not the
          one live background control an AT cursor reaches ahead of the modal, only
          to no-op against an inert main. */}
      <button
        type="button"
        inert={backgroundInert}
        onClick={skipToMain}
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:border focus:border-accent focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-link focus:shadow-md focus:outline-none"
      >
        Skip to main content
      </button>
      <UpdatePrompt />
      <ConnectionStatus />
      <PricingWarning />
      <div className="flex min-h-0 flex-1">
        <aside
          ref={asideRef}
          id="app-sidebar"
          // Named on mobile, where it is a panel that slides over the page
          // rather than the page's own rail. Not a dialog and not modal: the
          // design fills the viewport below the top bar, so nothing is left
          // behind it to trap focus away from, and the control that dismisses it
          // lives in that bar. While closed it is off-canvas, so inert takes its
          // links out of the tab order and the accessibility tree until opened.
          aria-label={isMobile ? "Navigation" : undefined}
          tabIndex={isMobile ? -1 : undefined}
          inert={isMobile && !mobileNavOpen ? true : undefined}
          style={isMobile ? undefined : { width }}
          className={clsx(
            "flex flex-col gap-4 border-r border-border bg-background-alt p-3 focus:outline-none",
            isMobile
              ? clsx(
                  // Full width, starting below the top bar: `top-14` pairs with
                  // the header's `min-h-14`, which is exact because everything in
                  // that bar truncates rather than wrapping. The design fills the
                  // viewport this way, which is why there is no backdrop to dim
                  // and no shadow to lift it off a page you cannot see.
                  "fixed inset-x-0 top-14 bottom-0 z-40 w-full transition-transform duration-200",
                  mobileNavOpen ? "translate-x-0" : "-translate-x-full",
                )
              : clsx(
                  "relative shrink-0",
                  !resizing && "transition-[width] duration-150",
                ),
          )}
        >
          {/* The scope the rail below belongs to. In the workspace context that
              is the switcher; in the organization context it is the way back
              out, which is how the prototype leaves that rail. */}
          {inOrganization ? (
            <div className="flex min-h-14 items-center">
              <Link
                to="/"
                onClick={() => setMobileNavOpen(false)}
                className={navRowClass({ collapsed: effectiveCollapsed })}
                aria-label={
                  effectiveCollapsed
                    ? `Back to ${selectedWorkspace?.name ?? "workspace"}`
                    : undefined
                }
                title={
                  effectiveCollapsed
                    ? `Back to ${selectedWorkspace?.name ?? "workspace"}`
                    : undefined
                }
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="h-4 w-4 shrink-0"
                >
                  <path
                    d="M19 12H4M10 6l-6 6 6 6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {effectiveCollapsed ? null : (
                  <span className="min-w-0 flex-1 truncate">
                    {`Back to ${selectedWorkspace?.name ?? "workspace"}`}
                  </span>
                )}
              </Link>
            </div>
          ) : (
            <WorkspaceSwitcher collapsed={effectiveCollapsed} />
          )}
          <nav
            // Named because the header's breadcrumb is a navigation landmark
            // too, and two unnamed ones give a screen-reader user no way to tell
            // the rail from the trail.
            aria-label="Sidebar"
            // Expanded, one 2px rhythm runs through rows *and* between groups:
            // the 32px heading block is what separates one group from the next.
            // Collapsed there are no headings, so the gap has to do that work.
            className={clsx(
              "flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden",
              effectiveCollapsed ? "gap-3" : "gap-0.5",
            )}
          >
            {visibleSections.map(({ section, items }) => {
              return (
                <section
                  key={section.id}
                  aria-label={section.label}
                  className="flex flex-col gap-0.5"
                >
                  {/* A heading labels each group when expanded. Collapsed there is
                      no width for one, and an unlabeled group never had one, so in
                      both cases the rhythm above does the separating instead of a
                      rule: a divider between every pair of groups reads as five
                      lists rather than one rail. */}
                  {!effectiveCollapsed && section.label ? (
                    <p className={NAV_SECTION_HEADING_CLASS}>{section.label}</p>
                  ) : null}
                  <div className="flex flex-col gap-0.5">
                    {items.map((item) =>
                      item.children ? (
                        <NavGroup
                          key={item.to}
                          item={item}
                          currentPath={pathname}
                          onNavigate={() => setMobileNavOpen(false)}
                          isVisible={isVisible}
                          collapsed={effectiveCollapsed}
                        />
                      ) : (
                        // Highlighted from the registry's own answer rather than
                        // from `activeProps`, whose default match is a prefix
                        // one: on `/organization/members` that lights up
                        // "General" as well, since `/organization` is its parent
                        // route. `navItemForPath` prefers the exact entry, and a
                        // future child route (`/routing/new`) still resolves to
                        // its parent, which is the highlight that route wants.
                        <NavRowLink
                          key={item.to}
                          to={item.to}
                          label={item.label}
                          icon={item.icon}
                          isActive={currentItem?.to === item.to}
                          collapsed={effectiveCollapsed}
                          // Tapping a destination dismisses the mobile drawer so
                          // the page it landed on is visible, not behind it.
                          onNavigate={() => setMobileNavOpen(false)}
                        />
                      ),
                    )}
                  </div>
                </section>
              )
            })}
          </nav>
          {/* The account block, set off by a rule as in the navigation prototype:
              the way onto the organization rail, the bundled guide, and the
              account control whose menu carries appearance and sign-out. */}
          <div className="flex flex-col gap-1 border-t border-border pt-1 pb-[env(safe-area-inset-bottom)]">
            {/* The way into the organization rail. Only in the workspace
                context, since the organization one has its own way back, and
                only for someone who manages the organization: it is the single
                destination the design hides outright rather than degrading to
                read-only (artboard A2 is the member variant, and this row is
                what it drops).

                Drawn as an ordinary nav row, which is how the design draws it.
                It used to be a bordered box with a trailing chevron, on the
                argument that a context switch should not look like a page and
                that an operator whose sidebar used to list Users, Budgets and
                Settings needed to find where they went. Both were true and
                neither survives the design: the box makes the footer read as a
                button bar under the rail rather than as the end of it, and the
                chevron promises a submenu that never opens. */}
            {!inOrganization && managesOrganization ? (
              <Link
                to="/organization/members"
                onClick={() => setMobileNavOpen(false)}
                className={navRowClass({ collapsed: effectiveCollapsed })}
                aria-label={effectiveCollapsed ? "Organization" : undefined}
                title={
                  effectiveCollapsed
                    ? "Organization: members, spend and budgets, users, settings"
                    : undefined
                }
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  className="h-4 w-4 shrink-0"
                >
                  <circle cx="12" cy="12" r="3" />
                  <path
                    d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
                    strokeLinejoin="round"
                  />
                </svg>
                {effectiveCollapsed ? null : (
                  <span className="min-w-0 flex-1 truncate">Organization</span>
                )}
              </Link>
            ) : null}
            {/* One control, not a stack of links: the guide, appearance, and
                sign-out all live in its menu, which is how the prototype ends
                the rail. Sign-out used to sit in the page header. */}
            {/* The design rules the account row off from the row above it, so
                the control that ends the rail is not read as one more
                destination in the group that changes context. */}
            {!inOrganization && managesOrganization ? (
              <div aria-hidden="true" className="h-px shrink-0 bg-border" />
            ) : null}
            <AccountMenu collapsed={effectiveCollapsed} />
          </div>
          {collapsed || isMobile ? null : (
            // biome-ignore lint/a11y/useSemanticElements: <hr> is a thematic break; this is a keyboard-operable resize handle
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize sidebar"
              aria-valuenow={Math.round(sidebarWidth)}
              aria-valuemin={MIN_SIDEBAR}
              aria-valuemax={MAX_SIDEBAR}
              tabIndex={0}
              onPointerDown={startResize}
              onPointerMove={moveResize}
              onPointerUp={endResize}
              onKeyDown={nudgeResize}
              className={clsx(
                "absolute top-0 right-0 z-10 h-full w-1.5 cursor-col-resize touch-none transition-colors",
                "hover:bg-accent focus-visible:bg-accent focus:outline-none",
                resizing ? "bg-accent" : "bg-transparent",
              )}
            />
          )}
        </aside>
        {/* The right-hand pane: the header sits beside the rail rather than above
            it, which is what lets the sidebar run the full height of the window. */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header
            // The design's top bar sits on the page ground rather than on a
            // card fill, so the rail is the only chrome that reads as a surface.
            className="flex min-h-14 shrink-0 items-center gap-4 border-b border-border bg-background pr-5 pl-4"
          >
            <div className="flex min-w-0 flex-1 items-center gap-4">
              <button
                type="button"
                ref={toggleRef}
                onClick={() => setMobileNavOpen((value) => !value)}
                aria-label={
                  mobileNavOpen ? "Close navigation" : "Open navigation"
                }
                aria-expanded={mobileNavOpen}
                aria-controls="app-sidebar"
                className="-ml-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-alt hover:text-foreground md:hidden"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  className="h-5 w-5"
                >
                  <path
                    d={
                      mobileNavOpen
                        ? "M6 6l12 12M18 6L6 18"
                        : "M4 6h16M4 12h16M4 18h16"
                    }
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              {/* Collapse lives here, at the head of the content pane, rather
                  than floating on the rail's edge: the rail now runs the full
                  height of the window and has no edge above the fold to hang it
                  on. Desktop-only, as before; on mobile the drawer is dismissed
                  from the control to its left or from the backdrop. */}
              <button
                type="button"
                onClick={() => setCollapsed((value) => !value)}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-pressed={collapsed}
                title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                className="-ml-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-alt hover:text-foreground md:flex"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="h-4 w-4"
                >
                  <rect x="3" y="4" width="18" height="16" rx="2" />
                  <path d="M9 4v16" strokeLinecap="round" />
                </svg>
              </button>
              <Breadcrumbs pathname={pathname} />
            </div>
            <TopBarActions />
          </header>
          <main
            ref={mainRef}
            id="main-content"
            // tabIndex={-1} lets the skip link move focus here programmatically
            // without adding the region itself to the natural tab order.
            tabIndex={-1}
            inert={backgroundInert}
            className="flex-1 overflow-y-auto focus:outline-none"
          >
            <div className="mx-auto flex max-w-[1800px] flex-col gap-6 px-4 py-5 md:px-6 md:py-6">
              {routeIsGatedOff ? (
                <EmptyState
                  // The leaf's name, not the group's: someone who followed a
                  // link to Guardrails should not be told "Routing" is missing.
                  title={`${navLabelForPath(pathname) ?? currentItem.label} is not available here`}
                  description="This deployment does not serve that page. Pick a destination from the sidebar."
                />
              ) : (
                <Outlet />
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}
