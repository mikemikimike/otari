from fastapi import Depends, FastAPI

from gateway.api.deps import require_capability
from gateway.api.routes import (
    admin,
    agent_telemetry,
    aliases,
    audio,
    auth_oauth,
    auth_password,
    auth_password_reset,
    auth_session,
    auth_signup,
    auth_webauthn,
    batches,
    bootstrap,
    budgets,
    chat,
    embeddings,
    files,
    health,
    hosted_mode,
    hybrid_mode,
    images,
    invitations,
    keys,
    mail,
    maintenance_mode,
    messages,
    models,
    moderations,
    org_provider_keys,
    organization_guardrails,
    organization_pricing,
    organizations,
    otlp,
    pricing,
    providers,
    rerank,
    responses,
    routing,
    routing_memory,
    scoped_budgets,
    search,
    search_tools,
    settings,
    tool_settings,
    tools,
    usage,
    users,
    workspace_activation,
    workspace_code_execution_policy,
    workspace_mcp_servers,
    workspace_member_budget_policies,
    workspace_web_search,
    workspaces,
)
from gateway.container import Container
from gateway.core.config import GatewayConfig


def register_routers(app: FastAPI, config: GatewayConfig) -> None:
    """Mount Otari's own routers, then whatever the bootstrap contributed."""
    _register_core_routers(app, config)
    _register_contributed_routers(app)
    # Last, and after the contributed routers on purpose. Both stub routers are
    # ``{path:path}`` catch-alls over whole prefixes (/v1/organizations,
    # /v1/usage for one; /v1/chat, /v1/batches for the other), and FastAPI
    # serves the first route that matches, so registering them earlier would
    # swallow an overlay route under any of those prefixes and answer with the
    # stub instead. They are a fallback for a path nothing else serves, so they
    # are mounted like one.
    #
    # A deployment mounts at most one of them: they cover opposite halves, the
    # management plane a hybrid gateway does not own and the data plane a hosted
    # control plane does not serve, and no mode is missing both.
    if config.is_hybrid_mode:
        app.include_router(hybrid_mode.router)
    elif config.is_hosted_mode:
        app.include_router(hosted_mode.router)


def _register_data_plane_routers(app: FastAPI, config: GatewayConfig) -> None:
    """Mount the OpenAI-compatible inference surface, unless this is a control plane.

    Hosted mode gets none of it. A hosted deployment is the multi-tenant control
    plane: an organization's wallet is debited by the usage a data-plane gateway
    reports back to it, so inference served *by* the control plane is inference
    nobody reports and nobody is billed for (otari#822). The routers are left
    unmounted rather than guarded on the way in, so there is no billable code
    path to reach at all, and ``hosted_mode``'s stubs answer these paths with
    the data-plane address instead of a bare 404.

    Hybrid mode keeps the three that support it (multi-attempt fallback plus
    usage reporting) and none of the rest.
    """
    if config.is_hosted_mode:
        return

    app.include_router(chat.router)
    app.include_router(messages.router)
    app.include_router(responses.router)

    if config.is_hybrid_mode:
        return

    app.include_router(embeddings.router)
    app.include_router(images.router)
    app.include_router(audio.router)
    app.include_router(rerank.router)
    app.include_router(search.router)
    app.include_router(batches.router)
    app.include_router(moderations.router)
    # Storage for inference rather than inference itself: batch input and
    # output, and file inputs to a completion. It travels with the set because
    # every consumer of an uploaded file is in it.
    app.include_router(files.router)


def _register_contributed_routers(app: FastAPI) -> None:
    """Mount the routers this build's bootstrap contributed, each behind its gate.

    The additive half of the extension seam: an overlay records a router on the
    container and Otari mounts it, gated on the capability it names. Mounted in
    both modes, because an overlay may extend the data plane as readily as the
    management plane. With no bootstrap configured there are none, so this is a
    no-op for the plain build.

    Mounted after Otari's own routers and before whichever mode stub router
    this deployment gets, so a contribution cannot take a path the core already
    serves and a stub's catch-alls cannot take one the contribution serves.
    """
    container: Container = app.state.container
    for contribution in container.router_contributions():
        app.include_router(
            contribution.router,
            dependencies=[Depends(require_capability(contribution.capability))],
        )


def _register_core_routers(app: FastAPI, config: GatewayConfig) -> None:
    app.include_router(health.router)
    # Registered in every mode on purpose: the deployment bootstrap is how a
    # browser learns which mode it reached, so it is the one management-adjacent
    # route a hybrid gateway still answers.
    app.include_router(bootstrap.router)

    _register_data_plane_routers(app, config)

    if config.is_hybrid_mode:
        # The hybrid stub router is mounted by register_routers, after the
        # contributed routers; see the note there.
        return  # The management routers below are skipped in hybrid mode only

    app.include_router(admin.router)
    app.include_router(auth_session.router)
    app.include_router(auth_password.router)
    app.include_router(auth_signup.router)
    app.include_router(auth_password_reset.router)
    app.include_router(auth_webauthn.router)
    app.include_router(auth_oauth.router)
    app.include_router(models.router)
    app.include_router(providers.router)
    app.include_router(keys.router)
    app.include_router(users.router)
    app.include_router(organizations.router)
    app.include_router(organization_pricing.router)
    app.include_router(organization_guardrails.router)
    app.include_router(workspaces.router)
    app.include_router(invitations.router)
    app.include_router(workspace_member_budget_policies.router)
    app.include_router(workspace_activation.router)
    app.include_router(workspace_mcp_servers.router)
    app.include_router(workspace_code_execution_policy.router)
    app.include_router(workspace_web_search.router)
    app.include_router(org_provider_keys.org_router)
    app.include_router(org_provider_keys.workspace_router)
    app.include_router(budgets.router)
    app.include_router(scoped_budgets.router)
    app.include_router(aliases.router)
    app.include_router(routing.router)
    app.include_router(routing_memory.router)
    app.include_router(pricing.router)
    app.include_router(usage.router)
    app.include_router(agent_telemetry.router)
    app.include_router(otlp.router)
    app.include_router(settings.router)
    app.include_router(mail.router)
    app.include_router(maintenance_mode.router)
    app.include_router(tool_settings.router)
    app.include_router(search_tools.router)
    app.include_router(tools.router)
