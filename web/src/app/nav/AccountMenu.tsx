import { Button, Popover } from "@heroui/react"
import { useState } from "react"

import { useAuth } from "@/features/auth/AuthContext"
import { EntitlementGate } from "@/shared/components/EntitlementGate"
import { useDeployment } from "@/shared/hooks/useDeployment"
import {
  THEME_PREFERENCES,
  type ThemePreference,
  useTheme,
} from "@/shared/hooks/useTheme"
import { NAV_ICON_CLASS, navRowClass } from "./rowStyles"

// The control that ends the sidebar, and the menu it opens: account settings,
// appearance, the legal pages, who you are signed in as, and the way out. The
// design's "Menu member · Linear order" artboard is the order and the geometry.
//
// Two of these are real in a standalone gateway. Appearance drives the dark
// token block globals.css has carried since the design foundation was rehomed,
// and logging out ends the master-key session. The rest describe a per-user
// account, and this deployment has one session shared by whoever holds the
// master key: Account settings and Data & privacy are disabled with the reason
// rather than omitted, because they are coming (otari-ai#1716) and a menu that
// silently lacks them reads as a menu that will never have them. Terms of
// service is different again, and gated: it is a hosted document, so it appears
// only for a deployment that has one to point at.

const THEME_LABELS: Record<ThemePreference, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
}

// 36px rows at 13.5px, which is the menu's own scale: a step down from the
// rail's 44px/14px, because a menu row is read once on the way to a decision
// rather than scanned as a standing list.
const MENU_ROW =
  "flex min-h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-[0.84375rem] leading-[1.125rem] font-medium transition-colors"
const MENU_ROW_RESTING = "text-foreground hover:bg-surface-alt"
const MENU_ROW_DISABLED = "cursor-not-allowed text-muted opacity-60"
const MENU_DIVIDER = "my-0.5 h-px shrink-0 bg-border"

// Whose session this is. A standalone gateway issues one, for the operator
// identity it provisioned itself, and the membership context does not carry the
// caller's own name, so the session kind is the most this can honestly say. The
// design's identity block shows a name over an email; there is no email here, so
// the second line names the credential instead of inventing an address.
function sessionIdentity(sessionType: string): {
  name: string
  initials: string
  detail: string
} {
  if (sessionType === "local_operator") {
    return {
      name: "Operator",
      initials: "OP",
      detail: "Master-key session",
    }
  }
  return { name: "Signed in", initials: "··", detail: "This gateway" }
}

function MenuItem({
  label,
  icon,
  onPress,
  isDisabled,
  title,
  trailing,
  expanded,
}: {
  label: string
  icon: React.ReactNode
  onPress?: () => void
  isDisabled?: boolean
  title?: string
  trailing?: string
  expanded?: boolean
}) {
  return (
    <button
      type="button"
      disabled={isDisabled}
      title={title}
      // A disabled button takes no focus, so the tooltip is pointer-only. Fold
      // the reason into the name instead, which a screen reader still reads
      // when browsing past the item.
      aria-label={isDisabled && title ? `${label} (${title})` : undefined}
      aria-expanded={expanded}
      onClick={onPress}
      className={`${MENU_ROW} ${isDisabled ? MENU_ROW_DISABLED : MENU_ROW_RESTING}`}
    >
      {icon}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {trailing ? (
        <span className="shrink-0 text-xs font-normal text-muted">
          {trailing}
        </span>
      ) : null}
    </button>
  )
}

function MenuExternalLink({
  label,
  icon,
  href,
}: {
  label: string
  icon: React.ReactNode
  href: string
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`${MENU_ROW} ${MENU_ROW_RESTING}`}
    >
      {icon}
      <span className="min-w-0 flex-1 truncate">{label}</span>
    </a>
  )
}

const AccountIcon = (
  <svg
    aria-hidden="true"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    className={`${NAV_ICON_CLASS} text-muted`}
  >
    <circle cx="12" cy="8" r="3.5" />
    <path d="M5 20a7 7 0 0 1 14 0" strokeLinecap="round" />
  </svg>
)

const AppearanceIcon = (
  <svg
    aria-hidden="true"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    className={`${NAV_ICON_CLASS} text-muted`}
  >
    <path d="M20 13a8 8 0 1 1-9-9 6 6 0 0 0 9 9z" strokeLinejoin="round" />
  </svg>
)

const TermsIcon = (
  <svg
    aria-hidden="true"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    className={`${NAV_ICON_CLASS} text-muted`}
  >
    <path d="M6.5 3.5h7l4.5 4.5v12h-11.5z" strokeLinejoin="round" />
    <path d="M13.5 3.5v4.5h4.5" strokeLinejoin="round" />
    <path d="M9 13h6M9 16.5h4" strokeLinecap="round" />
  </svg>
)

const PrivacyIcon = (
  <svg
    aria-hidden="true"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    className={`${NAV_ICON_CLASS} text-muted`}
  >
    <path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z" strokeLinejoin="round" />
    <path d="m9 12 2 2 3.5-3.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const LogOutIcon = (
  <svg
    aria-hidden="true"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    className={`${NAV_ICON_CLASS} text-muted`}
  >
    <path
      d="M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h4M16 15l3-3-3-3M19 12H10"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

/**
 * Appearance: one row carrying the current preference, opening the three.
 *
 * The design draws the closed state, a row with "System" on the right, which is
 * what a menu wants: the setting is one line until you are changing it. The
 * three options were previously always on show as a radio group, which spent
 * three rows of the menu on a setting nobody opened the menu for.
 *
 * Kept as real radios rather than buttons, so the group is one tab stop and
 * arrow-navigable, and so the browser's own focus ring lands on the option a
 * keyboard user is on. `System` is a preference in its own right and stays
 * selectable: it is the only value that keeps following the OS.
 */
function AppearanceControl() {
  const { preference, setPreference } = useTheme()
  const [open, setOpen] = useState(false)

  return (
    <div className="flex flex-col">
      <MenuItem
        label="Appearance"
        icon={AppearanceIcon}
        trailing={THEME_LABELS[preference]}
        expanded={open}
        onPress={() => setOpen((value) => !value)}
      />
      {open ? (
        <fieldset className="flex flex-col pt-0.5">
          <legend className="sr-only">Appearance</legend>
          {THEME_PREFERENCES.map((option) => (
            <label
              key={option}
              // Indented past the row's icon lane, the way a nested nav row is,
              // so the three read as this row's options rather than as three
              // more entries in the menu.
              className={`${MENU_ROW} cursor-pointer pl-[2.75rem] ${
                preference === option
                  ? "bg-surface-alt text-foreground"
                  : MENU_ROW_RESTING
              }`}
            >
              <input
                type="radio"
                name="appearance"
                className="sr-only"
                checked={preference === option}
                onChange={() => setPreference(option)}
              />
              <span className="min-w-0 flex-1 truncate">
                {THEME_LABELS[option]}
              </span>
              {preference === option ? (
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  className="h-4 w-4 shrink-0 text-accent"
                >
                  <path
                    d="m5.5 10 3 3 6-6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : null}
            </label>
          ))}
        </fieldset>
      ) : null}
    </div>
  )
}

export function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const { logout } = useAuth()
  const { session_type, management_url } = useDeployment()
  const [open, setOpen] = useState(false)
  const identity = sessionIdentity(session_type)

  return (
    <Popover isOpen={open} onOpenChange={setOpen}>
      {/* HeroUI's Button, not a plain one: the popover wires its trigger through
          react-aria, and a bare <button> leaves it unopenable. `w-auto!` is what
          makes it span the rail, overriding the width the variant sets, which
          otherwise leaves this a pill in the corner. */}
      <Button
        variant="ghost"
        aria-label="Account"
        className={`${navRowClass({ collapsed })} w-auto! justify-start`}
      >
        <span className="flex h-[1.625rem] w-[1.625rem] shrink-0 items-center justify-center rounded-full border border-border bg-surface-alt text-[0.5625rem] font-semibold text-muted">
          {identity.initials}
        </span>
        {collapsed ? null : (
          <>
            <span className="min-w-0 flex-1 truncate text-left text-foreground">
              {identity.name}
            </span>
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              className="h-4 w-4 shrink-0 text-muted"
            >
              <path
                d="M8 10l4 4 4-4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </>
        )}
      </Button>
      {/* Opens upward: the control is pinned to the bottom of the rail. */}
      <Popover.Content placement="top start">
        <Popover.Dialog className="flex w-[17rem] flex-col gap-1.5">
          <MenuItem
            label="Account settings"
            icon={AccountIcon}
            title="A standalone gateway has one shared session, so there is no per-user account yet."
            isDisabled
          />
          <AppearanceControl />
          <div className={MENU_DIVIDER} />
          {/* Hosted-only, and gated twice over: the entitlement says the
              deployment has terms to show, and `management_url` is where they
              are. A self-hosted gateway is neither, so the row is absent rather
              than pointing somewhere invented. */}
          {management_url ? (
            <EntitlementGate capability="legal.terms">
              <MenuExternalLink
                label="Terms of service"
                icon={TermsIcon}
                href={`${management_url.replace(/\/$/, "")}/terms`}
              />
            </EntitlementGate>
          ) : null}
          <MenuItem
            label="Data & privacy"
            icon={PrivacyIcon}
            title="The gateway stores its data locally and reports nothing outward, so there is nothing to configure here yet."
            isDisabled
          />
          <div className={MENU_DIVIDER} />
          {/* Who you are, at the foot of the menu rather than in the trigger:
              the rail has room for one line, and this is where the design puts
              the second. */}
          <div className="flex items-center gap-2.5 px-2.5 py-2">
            <span className="flex h-[1.875rem] w-[1.875rem] shrink-0 items-center justify-center rounded-full bg-surface-alt text-[0.6875rem] leading-[0.875rem] font-semibold text-muted">
              {identity.initials}
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-0.5 text-left">
              <span className="truncate text-[0.84375rem] leading-[1.125rem] font-semibold text-foreground">
                {identity.name}
              </span>
              <span className="truncate text-[0.71875rem] leading-[0.9375rem] text-muted">
                {identity.detail}
              </span>
            </span>
          </div>
          {/* Neutral, not danger-colored. Ending a session is reversible by
              signing in again, so red here spends the color that marks the
              deletes on the pages behind this menu. */}
          <MenuItem label="Log out" icon={LogOutIcon} onPress={logout} />
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  )
}
