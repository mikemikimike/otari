"""What a hosted control plane serves, and what it refuses.

The mirror of ``test_hybrid_mode_surface``: that file asserts a hybrid gateway
does not serve the management plane, this one that a hosted control plane does
not serve the data plane. The refusal is a billing boundary (otari#822): an
organization's wallet is debited by the usage a data-plane gateway reports back
to the control plane, so a completion the control plane served itself is a
completion nobody reports and nobody pays for.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.api.deps import reset_config
from gateway.core.config import API_KEY_HEADER, GatewayConfig
from gateway.core.database import reset_db
from gateway.main import create_app

DATA_PLANE_URL = "https://gateway.otari.example"
MASTER_KEY = "test-master-key"

# One request per data-plane path, verb included, so a stub that covered the
# prefix but not the verb the real route takes would fail here.
DATA_PLANE_REQUESTS: tuple[tuple[str, str], ...] = (
    ("POST", "/v1/chat/completions"),
    ("POST", "/v1/messages"),
    ("POST", "/v1/messages/count_tokens"),
    ("POST", "/v1/responses"),
    ("POST", "/v1/embeddings"),
    ("POST", "/v1/images/generations"),
    ("POST", "/v1/audio/transcriptions"),
    ("POST", "/v1/audio/speech"),
    ("POST", "/v1/rerank"),
    ("POST", "/v1/moderations"),
    ("POST", "/v1/search"),
    ("POST", "/v1/search/tavily"),
    ("POST", "/v1/batches"),
    ("GET", "/v1/batches/batch_abc"),
    ("POST", "/v1/batches/batch_abc/cancel"),
    ("GET", "/v1/files"),
    ("POST", "/v1/files"),
    ("GET", "/v1/files/file_abc/content"),
)

# The route modules that make up the data plane, checked by module rather than by
# path because that is the claim: the router is not registered. A path check
# cannot say it, since the stub answers on the same paths.
DATA_PLANE_MODULES: tuple[str, ...] = (
    "chat",
    "messages",
    "responses",
    "embeddings",
    "images",
    "audio",
    "rerank",
    "moderations",
    "search",
    "batches",
    "files",
)

# The paths a hosted deployment's own dashboard still needs, including the two
# that sit one character away from a refused prefix.
MANAGEMENT_PATHS: tuple[str, ...] = (
    "/v1/models",
    "/v1/pricing",
    "/v1/tools",
    "/v1/search-tools",
    "/v1/keys",
    "/v1/usage",
    "/v1/organizations/me/provider-keys",
)


@pytest.fixture(autouse=True)
def _reset_process_state() -> Generator[None, None, None]:
    """Put the process-wide config and engine back, whether or not the test passed."""
    yield
    reset_config()
    reset_db()


def _hosted(tmp_path: Path, data_plane_url: str | None = DATA_PLANE_URL) -> GatewayConfig:
    return GatewayConfig(
        mode="hosted",
        database_url=f"sqlite:///{tmp_path / 'hosted.db'}",
        master_key=MASTER_KEY,
        data_plane_url=data_plane_url,
    )


def _standalone(tmp_path: Path) -> GatewayConfig:
    return GatewayConfig(
        database_url=f"sqlite:///{tmp_path / 'standalone.db'}",
        master_key=MASTER_KEY,
    )


def _mounted_paths(config: GatewayConfig) -> set[str]:
    return {getattr(route, "path", "") for route in create_app(config).routes}


def _mounted_route_modules(config: GatewayConfig) -> set[str]:
    """Which ``api.routes`` modules contributed a route to this app.

    The registration question asked directly. A path cannot answer it here,
    because ``hosted_mode``'s catch-alls answer on the paths the real routers
    would have taken, so ``"/v1/embeddings" in mounted`` is true either way.
    """
    return {
        getattr(getattr(route, "endpoint", None), "__module__", "") for route in create_app(config).routes
    }


@pytest.mark.parametrize(("method", "path"), DATA_PLANE_REQUESTS, ids=[p for _, p in DATA_PLANE_REQUESTS])
def test_hosted_mode_refuses_every_data_plane_path(tmp_path: Path, method: str, path: str) -> None:
    with TestClient(create_app(_hosted(tmp_path))) as client:
        response = client.request(method, path, json={})

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "This endpoint is not available on a hosted control plane. "
            f"Send inference requests to the data-plane gateway at {DATA_PLANE_URL}."
        )
    }


def test_hosted_mode_refuses_without_naming_this_host_when_no_data_plane_is_configured(
    tmp_path: Path,
) -> None:
    """``data_plane_url`` is optional, and the refusal still has to be truthful.

    Naming the host the caller just reached would be worse than naming nothing,
    so the sentence stops instead of falling back to it.
    """
    with TestClient(create_app(_hosted(tmp_path, data_plane_url=None))) as client:
        response = client.post("/v1/chat/completions", json={})

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail == (
        "This endpoint is not available on a hosted control plane. "
        "Send inference requests to the data-plane gateway."
    )
    assert "testserver" not in detail


def test_hosted_mode_refuses_a_verb_the_path_never_took(tmp_path: Path) -> None:
    """A client that guessed the method wrong reads the explanation, not a 405.

    The point is that the path is not served here at all, and a 405 would say
    the opposite: that the path exists and the request was nearly right.
    """
    with TestClient(create_app(_hosted(tmp_path))) as client:
        response = client.get("/v1/chat/completions")

    assert response.status_code == 404
    assert DATA_PLANE_URL in response.json()["detail"]


def test_hosted_mode_refuses_a_head_probe(tmp_path: Path) -> None:
    """``HEAD`` is enumerated, not derived, so it needs its own assertion.

    FastAPI adds ``HEAD`` alongside ``GET`` only when a route leaves its methods
    unspecified, and these stubs spell theirs out, so leaving it off the list
    answered 405 to exactly the probing tooling most likely to reach for it. The
    body is empty by definition of the method; the status is the whole answer.
    """
    with TestClient(create_app(_hosted(tmp_path))) as client:
        response = client.head("/v1/chat/completions")

    assert response.status_code == 404


def test_hosted_mode_refusal_needs_no_credential(tmp_path: Path) -> None:
    """The refusal is reachable unauthenticated, deliberately.

    It carries only ``data_plane_url``, which ``GET /v1/bootstrap`` already
    publishes to any browser that asks, so there is nothing here to withhold.
    Requiring a key would mean a client pointed at the wrong host reads 401 and
    goes looking for a credential problem it does not have.
    """
    with TestClient(create_app(_hosted(tmp_path))) as client:
        response = client.post("/v1/chat/completions", json={}, headers={})

    assert response.status_code == 404
    assert DATA_PLANE_URL in response.json()["detail"]


def test_hosted_mode_mounts_no_inference_route_at_all(tmp_path: Path) -> None:
    """Absence is the guard, not a check on the way in.

    A refusal implemented as a dependency on the real handler would leave the
    billable code path registered and one bug away from running. These
    assertions are what say it is not registered: the catch-all stub is mounted,
    and the route it stands in for is not.
    """
    modules = _mounted_route_modules(_hosted(tmp_path))

    assert "gateway.api.routes.hosted_mode" in modules
    for module in DATA_PLANE_MODULES:
        assert f"gateway.api.routes.{module}" not in modules, (
            f"{module} routes are still registered on a hosted control plane"
        )


def test_hosted_mode_still_serves_the_management_plane(tmp_path: Path) -> None:
    """Dropping the data plane must not take a management router with it.

    ``/v1/search-tools`` and ``/v1/models`` are the near misses worth naming:
    the first sits under a refused prefix's neighbor and the second is a
    catalog read the dashboard cannot render a page without.
    """
    mounted = _mounted_paths(_hosted(tmp_path))

    for path in MANAGEMENT_PATHS:
        assert any(candidate.startswith(path) for candidate in mounted), f"{path} is not mounted"


def test_hosted_mode_still_answers_the_management_plane(tmp_path: Path) -> None:
    """Mounted is not the same as working, so one management call is made for real.

    ``/v1/keys`` is the one to pick: it is the page a hosted operator uses to
    hand somebody a key for the data-plane gateway, so it is exactly the surface
    that must survive the data plane being taken away.
    """
    with TestClient(create_app(_hosted(tmp_path))) as client:
        response = client.get("/v1/keys", headers={API_KEY_HEADER: f"Bearer {MASTER_KEY}"})

    assert response.status_code == 200


def test_standalone_still_serves_the_whole_data_plane(tmp_path: Path) -> None:
    """The other half of the split: a single-tenant gateway is unaffected.

    It bills its own requests against its own database, so nothing here is
    unbilled and every inference route stays mounted, with no stub over it.
    """
    modules = _mounted_route_modules(_standalone(tmp_path))

    for module in DATA_PLANE_MODULES:
        assert f"gateway.api.routes.{module}" in modules, f"{module} went missing from a standalone gateway"
    assert "gateway.api.routes.hosted_mode" not in modules


def test_a_deployment_mounts_at_most_one_mode_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The two stub routers cover opposite halves and must not overlap.

    Hybrid stubs the management prefixes it does not own and keeps chat;
    hosted stubs chat and keeps the management prefixes. A deployment that
    mounted both would refuse a path the other one serves.
    """
    hosted = _mounted_route_modules(_hosted(tmp_path))
    assert "gateway.api.routes.hosted_mode" in hosted
    assert "gateway.api.routes.hybrid_mode" not in hosted

    reset_config()
    reset_db()

    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")
    hybrid_config = GatewayConfig(mode="hybrid", platform={"base_url": "http://localhost:8100/api/v1"})
    hybrid = _mounted_route_modules(hybrid_config)
    assert "gateway.api.routes.hybrid_mode" in hybrid
    assert "gateway.api.routes.hosted_mode" not in hybrid
    # And the three inference routers hybrid mode does support are untouched by
    # the split that took them away from hosted mode.
    assert {"gateway.api.routes.chat", "gateway.api.routes.messages", "gateway.api.routes.responses"} <= hybrid
