import { createFileRoute } from "@tanstack/react-router"

import { ModelPricingPage } from "@/features/pricing/ModelPricingPage"

export const Route = createFileRoute("/organization/pricing")({
  component: ModelPricingPage,
})
