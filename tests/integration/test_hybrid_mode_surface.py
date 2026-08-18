from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from gateway.api.deps import reset_config
from gateway.core.config import GatewayConfig
from gateway.core.database import reset_db
from gateway.main import create_app


def _hybrid_database_url(tmp_path: Path) -> str:
    """An isolated, real SQLite file per test.

    Hybrid mode initializes a database and runs migrations against it now
    (see #1643); every test in this file needs its own so they don't share
    state through a default ``./otari.db`` in the working directory.
    """
    return f"sqlite:///{tmp_path / 'hybrid.db'}"


def test_hybrid_mode_starts_with_a_working_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hybrid mode initializes its own local database and runs migrations against it.

    This is the reversal of what this test used to pin (hybrid boots even
    with an unreachable database): #1643's gateway survivals (aliases,
    routing memory, router preferences, files, batches) need a shadow
    identity row to key on, so hybrid mode is no longer database-less. See
    test_hybrid_mode_fails_to_start_with_an_unreachable_database for the
    other half of this reversal: a real, working database is now required,
    the same as standalone.
    """
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")

    config = GatewayConfig(
        mode="hybrid",
        database_url=_hybrid_database_url(tmp_path),
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["mode"] == "hybrid"
    assert payload["platform_reachable"] in {"yes", "no"}

    reset_config()
    reset_db()


def test_hybrid_mode_fails_to_start_with_an_unreachable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half of the reversal above: hybrid mode now needs a real database.

    Deliberately does not clean up config/db state on the failure path (there
    is nothing to clean up: init_db never got far enough to set the module
    globals reset_db() clears), matching how a standalone boot against a bad
    database_url already fails today.
    """
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")

    config = GatewayConfig(
        mode="hybrid",
        database_url="postgresql://127.0.0.1:1/does-not-exist",
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    # init_db (and, with auto_migrate on by default, the migration run) fires
    # on ASGI startup, i.e. when the TestClient context is entered, not at
    # create_app() itself.
    with pytest.raises(OperationalError), TestClient(app):
        pass

    reset_config()


def test_hybrid_mode_disables_local_management_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")

    config = GatewayConfig(
        mode="hybrid",
        database_url=_hybrid_database_url(tmp_path),
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    with TestClient(app) as client:
        users_response = client.post("/v1/users", json={"user_id": "u1"})
        keys_response = client.get("/v1/keys")
        budgets_response = client.get("/v1/budgets")
        usage_response = client.get("/v1/usage")

    expected = {"detail": "This endpoint is not available in hybrid mode. Manage this resource via the platform UI."}
    assert users_response.status_code == 404
    assert users_response.json() == expected
    assert keys_response.status_code == 404
    assert keys_response.json() == expected
    assert budgets_response.status_code == 404
    assert budgets_response.json() == expected
    assert usage_response.status_code == 404
    assert usage_response.json() == expected

    reset_config()
    reset_db()


def test_hybrid_mode_disables_dashboard_management_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The admin-dashboard management surface is standalone-only; in hybrid mode
    # it must be unavailable (owned by the platform), with the same helpful hint.
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")

    config = GatewayConfig(
        mode="hybrid",
        database_url=_hybrid_database_url(tmp_path),
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    expected = {"detail": "This endpoint is not available in hybrid mode. Manage this resource via the platform UI."}
    with TestClient(app) as client:
        for path in ("/v1/settings", "/v1/aliases", "/v1/providers", "/v1/pricing"):
            response = client.get(path)
            assert response.status_code == 404, path
            assert response.json() == expected, path

        # State-changing verbs are stubbed too (api_route covers every method), so
        # a write cannot slip past the hybrid gate and reach a local handler.
        patch_settings = client.patch("/v1/settings", json={"model_discovery": False})
        assert patch_settings.status_code == 404
        assert patch_settings.json() == expected
        post_alias = client.post("/v1/aliases", json={"name": "x", "target": "anthropic:claude-opus-4"})
        assert post_alias.status_code == 404
        assert post_alias.json() == expected
        assert client.delete("/v1/aliases/x").status_code == 404

    reset_config()
    reset_db()


def test_hybrid_mode_omits_model_management_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # models.router is standalone-only (register_routers returns early in hybrid),
    # so the dashboard's model-management reads have no route at all. Guards
    # against re-mounting models.router in hybrid, which would expose them.
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")

    config = GatewayConfig(
        mode="hybrid",
        database_url=_hybrid_database_url(tmp_path),
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    with TestClient(app) as client:
        for path in ("/v1/models/metadata", "/v1/models/discoverable"):
            assert client.get(path).status_code == 404, path

    reset_config()
    reset_db()


def test_hybrid_mode_root_falls_back_to_tutorial_without_a_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hybrid serves the same dashboard bundle as standalone (it renders the
    # data-plane landing page there), so an unbuilt checkout degrades the same
    # way: the get-started tutorial at the root. Pinned with the bundle absent so
    # the assertion does not depend on whether this checkout happens to have one.
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")
    monkeypatch.setattr("gateway.main.get_dashboard_dir", lambda: None)

    config = GatewayConfig(
        mode="hybrid",
        database_url=_hybrid_database_url(tmp_path),
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Your gateway is running." in response.text

    reset_config()
    reset_db()


def test_hybrid_mode_health_reports_reachability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")

    async def _reachable(_: GatewayConfig) -> bool:
        return True

    monkeypatch.setattr("gateway.api.routes.health._check_platform_reachability", _reachable)

    config = GatewayConfig(
        mode="hybrid",
        database_url=_hybrid_database_url(tmp_path),
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    with TestClient(app) as client:
        response = client.get("/health")
        readiness_response = client.get("/health/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "mode": "hybrid", "platform_reachable": "yes"}
    assert readiness_response.status_code == 200
    assert readiness_response.json()["platform"] == "connected"

    reset_config()
    reset_db()


def test_hybrid_mode_readiness_fails_when_platform_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTARI_AI_TOKEN", "gw_test_token")

    async def _unreachable(_: GatewayConfig) -> bool:
        return False

    monkeypatch.setattr("gateway.api.routes.health._check_platform_reachability", _unreachable)

    config = GatewayConfig(
        mode="hybrid",
        database_url=_hybrid_database_url(tmp_path),
        platform={"base_url": "http://localhost:8100/api/v1"},
    )
    app = create_app(config)

    with TestClient(app) as client:
        response = client.get("/health/readiness")

    assert response.status_code == 503
    assert response.json()["detail"]["platform"] == "unavailable"

    reset_config()
    reset_db()
