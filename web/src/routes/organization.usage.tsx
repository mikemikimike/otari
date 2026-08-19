import { createFileRoute } from "@tanstack/react-router"

import { UsagePage } from "@/features/usage/UsagePage"

// The same page as `/usage`, with the workspace filter dropped: `/v1/usage` is
// unscoped without a `workspace_id`, so the tenant-wide view is the workspace
// one asked a wider question rather than a second page to keep in step.
export const Route = createFileRoute("/organization/usage")({
  component: () => <UsagePage scope="organization" />,
})
