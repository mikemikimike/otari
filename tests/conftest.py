import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if "gateway" in sys.modules:
    del sys.modules["gateway"]


@pytest.fixture(autouse=True)
def _no_background_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop the app lifespan from dialing providers and models.dev for real.

    Every ``TestClient(app)`` runs the lifespan, which starts the discovery and
    catalog refreshers; their first act is to prime the cache from a live dial.
    That is right in production and wrong in a test: it makes real outbound calls
    from every app boot, and it races a test that patches the dial *after*
    startup, so the read then serves whatever the unpatched prime cached.

    Suppressing the refreshers leaves the cache empty, so a read takes the
    cold-provider path and dials once, under whatever the test has patched.
    A test that wants the warm-cache read path seeds the cache itself.

    Lives in the root conftest, not the integration one, because the unit suite
    builds apps too (``tests/unit/test_gateway_root_page.py``,
    ``test_tools_endpoint.py``, ``test_settings_endpoint.py`` and others all use
    ``TestClient(create_app(...))``). Scoping this to ``tests/integration`` left
    every one of those making live models.dev fetches on CI, which is both wrong
    on its own terms and what surfaced the unbounded-shutdown bug that
    ``_stop_refresher`` now guards against. A test that wants the real refresher
    calls it directly rather than through the lifespan.
    """

    async def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("gateway.main.run_discovery_refresher", _noop)
    monkeypatch.setattr("gateway.main.run_catalog_refresher", _noop)


@pytest.fixture(autouse=True)
def _reset_default_workspace() -> None:
    """Drop the memoized key workspaces before each test.

    ``workspace_scope`` memoizes each key's workspace, because a usage row is
    written on the hot path and must not pay a lookup for something immutable.
    Immutable within one database, and every test empties its own, so an id
    cached by the previous test can name a row that is gone and the next insert
    then fails its foreign key. Same reason the alias and provider caches have
    resets.
    """
    from gateway.services.workspace_scope import reset_key_workspace_cache

    reset_key_workspace_cache()


@pytest.fixture(autouse=True)
def _reset_default_pricing() -> Generator[None, None, None]:
    """Restore process-wide pricing state to its default before each test.

    ``configure_default_pricing`` is set at app startup, so a test that builds an
    app with a different ``default_pricing`` would otherwise leak that state into
    later tests that call ``find_model_pricing`` directly. Reset to off, matching
    the config field's opt-in default; tests that need defaults enable explicitly.

    Also clear the memoized genai-prices resolutions so a real price cached by one
    test cannot mask another test that patches ``calc_price`` to fail.
    """
    from gateway.services.pricing_refresh_service import reset_price_refresh_state
    from gateway.services.pricing_service import configure_default_pricing, configure_provider_types

    configure_default_pricing(False)
    configure_provider_types(None)
    reset_price_refresh_state()
    yield
    configure_default_pricing(False)
    configure_provider_types(None)
    reset_price_refresh_state()


def seed_identity_id(db: Any, external_id: str, **columns: Any) -> Any:
    """The identity a directly-built request-plane row belongs to, created if absent.

    The sibling of :func:`seed_workspace_id`, and needed for the same reason:
    since otari-ai#1727 the ten request-plane tables store ``user.id``, so a
    fixture that inserts one of those rows without going through a route has to
    resolve the operator-defined handle it is thinking in to the id the column
    holds. Get-or-create, because the handle is what a test names and it should
    not have to know whether an earlier line already seeded it.

    ``active_organization_id`` is NOT NULL, so the identity lands in the same
    default organization a master-key write does.

    Imports inside the function, for the reason ``seed_workspace_id`` gives.
    """
    from gateway.models.tenancy import Organization, User

    existing = db.query(User).filter(User.external_id == external_id).first()
    if existing is not None:
        return existing.id

    organization = db.query(Organization).filter(Organization.slug == "default").first()
    if organization is None:
        organization = Organization(name="Default organization", slug="default")
        db.add(organization)
        db.flush()
    user = User(external_id=external_id, active_organization_id=organization.id, **columns)
    db.add(user)
    db.flush()
    return user.id


async def seed_identity_id_async(db: Any, external_id: str, **columns: Any) -> Any:
    """:func:`seed_identity_id` for the async session fixtures.

    Takes the identity's other columns too, because the async fixtures that need
    this are the budget tests, and what they are seeding is a spend counter.
    """
    from sqlalchemy import select

    from gateway.models.tenancy import Organization, User

    existing = (
        await db.execute(select(User).where(User.external_id == external_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    organization_id = (
        await db.execute(select(Organization.id).where(Organization.slug == "default"))
    ).scalar_one_or_none()
    if organization_id is None:
        organization = Organization(name="Default organization", slug="default")
        db.add(organization)
        await db.flush()
        organization_id = organization.id
    user = User(external_id=external_id, active_organization_id=organization_id, **columns)
    db.add(user)
    await db.flush()
    return user.id


def seed_workspace_id(db: Any) -> Any:
    """The workspace a directly-built request-plane row belongs to.

    Fixtures that insert ``UsageLog`` or ``APIKey`` rows through a sync session
    skip the routes that would resolve a workspace for them, and the column is
    NOT NULL. The migration seeds a default; this finds it, and creates one on a
    schema built by ``create_all`` rather than by migrations.

    Imports inside the function: this module puts ``src`` on ``sys.path`` at
    import time, so a top-level ``gateway`` import here would run before that.
    """
    from gateway.models.tenancy import Organization, Workspace

    workspace = (
        db.query(Workspace)
        .join(Organization, Organization.id == Workspace.organization_id)
        .filter(Organization.slug == "default")
        .first()
    )
    if workspace is not None:
        return workspace.id

    organization = db.query(Organization).filter(Organization.slug == "default").first()
    if organization is None:
        organization = Organization(name="Default organization", slug="default")
        db.add(organization)
        db.flush()
    workspace = Workspace(name="Default workspace", organization_id=organization.id)
    db.add(workspace)
    db.flush()
    return workspace.id
