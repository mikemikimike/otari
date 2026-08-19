import { Button, Modal, Popover } from "@heroui/react"
import { useState } from "react"
import { CreateWorkspaceForm } from "@/features/workspaces/WorkspacesPage"
import { useOrganizationContext } from "@/shared/api/hooks"
import { EntitlementGate } from "@/shared/components/EntitlementGate"
import { useSelectedWorkspace } from "@/shared/hooks/SelectedWorkspace"

// The menu's own rhythm, which is the rail's: a 44px row and a 32px heading
// block. The eyebrow above the organization is shorter, because it opens the
// menu rather than separating two groups inside it.
const MENU_HEADING = "flex min-h-8 items-center px-2.5 text-overline"
const MENU_ROW =
  "flex min-h-11 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-sm font-medium transition-colors"
const MENU_ROW_RESTING = "text-foreground hover:bg-surface-alt"
// The current scope is a tinted chip here, unlike the rail, where selection is a
// lifted one. In a menu the tint is the only thing that can carry "this is the
// one you are in" alongside the check; on the rail the fill is read against the
// rail's own ground, which a tint fights.
const MENU_ROW_CURRENT = "bg-primary-subtle text-primary-subtle-foreground"

function CheckMark() {
  return (
    <>
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        className="h-5 w-5 shrink-0 text-accent"
      >
        <path
          d="m5.5 10 3 3 6-6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="sr-only">Selected</span>
    </>
  )
}

function PlusMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      className="h-5 w-5 shrink-0"
    >
      <path d="M10 4.5v11M4.5 10h11" strokeLinecap="round" />
    </svg>
  )
}

// The organization and the workspace the shell is looking at, and the control
// that changes the second. Sits above the nav rather than in it because it
// scopes the destinations below it rather than being one.
//
// It scopes what the gateway both records and resolves per workspace: members,
// API keys, the request log, and the spend and volume charts over it. Two
// things it does not, and the copy in the popover says so rather than implying
// a scope that is not there. Routing policies and aliases carry a workspace
// column but are all stored in the default one on purpose, because resolution
// reads a process-wide name-keyed cache, so filtering them would hide live
// policies. Provider credentials are process-wide config rather than a
// workspace row.
export function WorkspaceSwitcher({ collapsed }: { collapsed: boolean }) {
  const { memberships, selected, select, isLoading } = useSelectedWorkspace()
  const context = useOrganizationContext()
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)

  // Both hops optional: the context can answer without an organization (a
  // failed read, or a shape a test supplies), and the switcher is chrome that
  // renders around whatever else is wrong rather than taking the shell down.
  const organizationName = context.data?.organization?.name ?? "Organization"

  const workspaceName = isLoading
    ? "Loading…"
    : (selected?.name ?? "No workspace")

  return (
    <>
      <Popover isOpen={open} onOpenChange={setOpen}>
        {/* HeroUI's Button, not a plain one: the popover wires its trigger through
          react-aria. `w-auto!` overrides the width the variant sets, which
          otherwise stops this short of the rail rather than spanning it.

          Collapsing narrows the trigger to the mark, but it stays the same
          trigger: the rail's collapsed state is remembered, so a switcher that
          became a plain <div> there would leave an operator unable to change
          workspace until they expanded the rail again. */}
        <Button
          variant="ghost"
          // Names the current workspace rather than replacing it: the label
          // overrides the visible text for assistive tech, so "Switch workspace"
          // alone would make the one thing this control reports unreadable.
          // No `title` companion, which HeroUI's Button does not take: collapsed,
          // the popover itself is what names the current workspace (it marks it
          // with a check), and this label is what assistive tech reads.
          aria-label={`Switch workspace, currently ${workspaceName} in ${organizationName}`}
          // 56px tall in both states, so the rail's first block is the same height
          // whichever context it is in: the organization rail's "Back to" row sits
          // in a box of exactly this height. The fill is the rail's own ground with
          // a border, not a white card, which is what keeps it reading as part of
          // the chrome rather than as the first item in the list.
          className={
            collapsed
              ? "min-h-14 w-full! items-center justify-center rounded-[0.625rem] border border-border bg-background-alt px-0 transition-colors hover:border-accent"
              : "min-h-14 w-full! items-center justify-start gap-2.5 rounded-[0.625rem] border border-border bg-background-alt px-2.5 py-2 text-left transition-colors hover:border-accent"
          }
        >
          {/* The mark is the switcher's hero, as in the prototype: the product
            name is not repeated in the header, so this is where it lives. */}
          <img
            src="/favicon.svg"
            alt=""
            className="h-[1.875rem] w-[1.875rem] shrink-0"
          />
          {collapsed ? null : (
            <>
              <span className="flex min-w-0 flex-1 flex-col gap-px">
                <span className="truncate text-sm leading-[1.125rem] font-semibold tracking-[-0.01em] text-foreground">
                  {workspaceName}
                </span>
                <span className="truncate text-[0.6875rem] leading-[0.875rem] font-medium text-muted">
                  {organizationName}
                </span>
              </span>
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                className="h-5 w-5 shrink-0 text-muted"
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
        <Popover.Content placement="bottom start">
          <Popover.Dialog className="flex w-[19.75rem] flex-col">
            <p className={MENU_HEADING}>Organization</p>
            {/* Not a control: a standalone gateway provisions one organization at
              first boot and mounts no endpoint to switch or create another, so
              this row states the scope rather than offering to change it. It
              still carries the check, because the design's menu marks the
              current scope at both levels and a check that only ever appears on
              one of them reads as an incomplete list. */}
            <div className={`${MENU_ROW} ${MENU_ROW_CURRENT}`}>
              <span className="min-w-0 flex-1 truncate">
                {organizationName}
              </span>
              <CheckMark />
            </div>
            <div className="my-1 border-t border-border" />
            <p className={MENU_HEADING}>Workspaces ({memberships.length})</p>
            {isLoading ? (
              <p className="px-2.5 py-1 text-xs text-muted">
                Loading workspaces…
              </p>
            ) : memberships.length === 0 ? (
              <p className="px-2.5 py-1 text-xs text-muted">
                You do not belong to a workspace yet.
              </p>
            ) : (
              <ul className="flex flex-col">
                {memberships.map((membership) => {
                  const isCurrent =
                    membership.workspace_id === selected?.workspace_id
                  return (
                    <li key={membership.workspace_id}>
                      <button
                        type="button"
                        className={`${MENU_ROW} ${
                          isCurrent ? MENU_ROW_CURRENT : MENU_ROW_RESTING
                        }`}
                        onClick={() => {
                          select(membership.workspace_id)
                          setOpen(false)
                        }}
                      >
                        <span className="min-w-0 flex-1 truncate">
                          {membership.name}
                        </span>
                        {/* The check is the only thing distinguishing the current
                          workspace, so it carries text a screen reader reads
                          rather than an attribute the role does not. */}
                        {isCurrent ? <CheckMark /> : null}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
            <div className="my-1 border-t border-border" />
            <button
              type="button"
              className={`${MENU_ROW} font-semibold text-accent hover:bg-surface-alt`}
              onClick={() => {
                setOpen(false)
                setCreating(true)
              }}
            >
              <PlusMark />
              <span className="min-w-0 flex-1 truncate">Create workspace</span>
            </button>
            {/* Coded, and absent here. A self-hosted gateway is one tenant: it
              mounts no create-organization endpoint, so the row is gated on an
              entitlement this build does not grant rather than rendered as a
              control that would fail. An overlay build that serves several
              organizations grants it and the menu matches the design whole. */}
            <EntitlementGate capability="organizations.create">
              <button
                type="button"
                className={`${MENU_ROW} ${MENU_ROW_RESTING} text-muted`}
                onClick={() => setOpen(false)}
              >
                <PlusMark />
                <span className="min-w-0 flex-1 truncate">
                  Create organization
                </span>
              </button>
            </EntitlementGate>
          </Popover.Dialog>
        </Popover.Content>
      </Popover>
      {/* Reuses the Workspaces page's own form rather than restating its fields:
          the popover has no room for a form, and it dismisses on the first click
          outside itself, which a name field cannot survive. */}
      <Modal isOpen={creating} onOpenChange={setCreating}>
        {/* The menu row is the trigger, and it lives inside a popover that has
            already dismissed by the time this opens, so the modal is driven from
            state instead. HeroUI still renders a press responder for the trigger
            slot and warns when nothing fills it, which is why this is hidden
            rather than absent; `SettingsPage` does the same for its own dialog. */}
        <Modal.Trigger className="hidden">Create workspace</Modal.Trigger>
        {/* An explicit dim: HeroUI maps `--backdrop` to opaque black, which the
            AlertDialog softens itself and the Modal does not, so without this the
            page behind the form goes fully black. */}
        <Modal.Backdrop className="bg-backdrop/50">
          <Modal.Container placement="center" size="md">
            <Modal.Dialog aria-label="Create workspace" className="p-0">
              <CreateWorkspaceForm onClose={() => setCreating(false)} />
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>
    </>
  )
}
