import { Button, Popover } from "@heroui/react"
import { useState } from "react"
import { useOrganizationContext } from "@/shared/api/hooks"
import { useSelectedWorkspace } from "@/shared/hooks/SelectedWorkspace"

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

  // Both hops optional: the context can answer without an organization (a
  // failed read, or a shape a test supplies), and the switcher is chrome that
  // renders around whatever else is wrong rather than taking the shell down.
  const organizationName = context.data?.organization?.name ?? "Organization"

  const workspaceName = isLoading
    ? "Loading…"
    : (selected?.name ?? "No workspace")

  return (
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
        <Popover.Dialog className="flex w-64 flex-col">
          <div className="px-2 pb-1 text-[11px] font-semibold tracking-wider text-muted uppercase">
            Organization
          </div>
          <div className="px-2 pb-2 text-sm text-foreground">
            {organizationName}
          </div>
          <div className="border-t border-border pt-2">
            <div className="px-2 pb-1 text-[11px] font-semibold tracking-wider text-muted uppercase">
              Workspaces ({memberships.length})
            </div>
            {memberships.length === 0 ? (
              <p className="px-2 py-1 text-xs text-muted">
                You do not belong to a workspace yet.
              </p>
            ) : (
              <ul className="flex flex-col">
                {memberships.map((membership) => (
                  <li key={membership.workspace_id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm text-foreground hover:bg-surface-alt hover:text-foreground"
                      onClick={() => {
                        select(membership.workspace_id)
                        setOpen(false)
                      }}
                    >
                      {membership.name}
                      {membership.workspace_id === selected?.workspace_id ? (
                        // Text rather than an aria-label on a bare span: the
                        // check mark is the only thing distinguishing the
                        // current workspace, so it needs a name that is read
                        // out rather than an attribute the role does not carry.
                        <>
                          <span aria-hidden="true">✓</span>
                          <span className="sr-only">Selected</span>
                        </>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="mt-2 border-t border-border px-2 pt-2 text-xs text-muted">
            Scopes members, API keys, usage, and the request log. Routing and
            provider credentials stay deployment-wide.
          </p>
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  )
}
