import { Link } from "@tanstack/react-router"

import { EntitlementGate } from "@/shared/components/EntitlementGate"
import { useDeployment } from "@/shared/hooks/useDeployment"

// The right end of the top bar: the links that are not destinations in either
// rail, and the balance.
//
// The design puts three things here. Documentation is the guide bundled with
// this gateway, which used to sit inside the account menu; it belongs in the
// chrome, because it is read alongside a page rather than instead of one, and
// the design's account menu has no row for it.
//
// Playground and the balance are hosted surfaces, and each is gated on the two
// things it actually needs rather than on a flag that stands in for them. The
// playground is a page otari.ai serves and this gateway does not, so the link
// needs both the entitlement and a `management_url` to point at, which only a
// gateway attached to otari.ai has. The balance needs an entitlement and a
// figure: this gateway meters spend but holds no wallet, so there is nothing to
// report and a zero here would be a claim rather than a reading.

const ACTION =
  "flex min-h-[2.125rem] items-center rounded-md px-1 text-[0.8125rem] leading-[1.125rem] font-medium text-muted transition-colors hover:text-foreground"

function Balance({ amount }: { amount: number }) {
  return (
    <span className="flex min-h-[2.125rem] shrink-0 items-center px-1">
      <span className="rounded-2xl bg-success-subtle px-1.5 text-xs font-medium text-success">
        {amount.toLocaleString(undefined, {
          style: "currency",
          currency: "USD",
        })}
      </span>
    </span>
  )
}

/**
 * @param balance Spendable credit, when the deployment holds a wallet. Nothing
 * in this build supplies one; it is the seam an overlay build fills.
 */
export function TopBarActions({ balance }: { balance?: number }) {
  const { management_url } = useDeployment()
  const platform = management_url?.replace(/\/$/, "")

  return (
    // Hidden below the md breakpoint, where the mobile header has room for the
    // dismiss control and the trail and nothing else.
    <div className="hidden shrink-0 items-center gap-5 md:flex">
      <Link to="/docs" className={ACTION}>
        Documentation
      </Link>
      {platform ? (
        <EntitlementGate capability="playground">
          <a
            href={`${platform}/playground`}
            target="_blank"
            rel="noopener noreferrer"
            className={ACTION}
          >
            Playground
          </a>
        </EntitlementGate>
      ) : null}
      {balance === undefined ? null : (
        <EntitlementGate capability="billing">
          <Balance amount={balance} />
        </EntitlementGate>
      )}
    </div>
  )
}
