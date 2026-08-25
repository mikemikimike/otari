"""The identity convergence's Alembic chain, exercised on SQLite.

Sibling of ``test_exact_budget_schema_chain.py`` and for the same reason: the
OSS base ships SQLite by default, and a revision that retypes a column can only
do that there by rebuilding the table, which is where a constraint or an index
goes missing.

The other half of the file is the property the change lives or dies on. A
deployment upgrading across otari-ai#1727 has live API keys in the field, and
nobody is going to re-issue them: the plaintext hashes to the same
``api_keys.key_hash``, but the row's owner has moved from a string primary key
to a UUID foreign key. So the last test boots the gateway on a database migrated
with a key already in it and authenticates with that key's original plaintext.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, inspect, text

import gateway.models  # noqa: F401  (registers every table on the shared metadata)
from gateway.auth.models import hash_key
from gateway.core.config import API_KEY_HEADER, GatewayConfig
from gateway.main import create_app

_ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
_CONVERGENCE_REVISION = "b7d1c4e9a3f6"
_BEFORE_CONVERGENCE = "d2f5b8c0e4a7"

# Every table whose owner column the revision re-points, and whether that column
# is nullable afterwards.
_SCOPED: dict[str, bool] = {
    "api_keys": True,
    "usage_logs": True,
    "budget_reset_logs": True,
    "model_aliases": True,
    "routing_policies": True,
    "routing_memory": False,
    "router_preferences": False,
    "file_objects": False,
    "batches": False,
    "agent_telemetry": True,
}

# The indexes and constraints the SQLite rebuild has to bring back with it.
_SURVIVING_INDEXES = {
    "model_aliases": {"ix_model_aliases_user_id", "uq_model_aliases_workspace_global_name"},
    "routing_policies": {"ix_routing_policies_user_id", "uq_routing_policies_workspace_global_name"},
    "usage_logs": {"ix_usage_logs_user_id", "ix_usage_logs_user_id_timestamp"},
    "routing_memory": {
        "ix_routing_memory_user_id",
        "ix_routing_memory_workspace_user_model",
        "ix_routing_memory_workspace_user_created",
        "ix_routing_memory_workspace_user_model_task",
    },
    "router_preferences": {
        "ix_router_preferences_user_id",
        "ix_router_preferences_workspace_user_created",
    },
}

_PLAINTEXT_KEY = "gw-a-key-minted-long-before-the-convergence-landed-here"


def _alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


def _tenancy_ids(connection: Connection) -> tuple[str, str]:
    """The organization and workspace the migration chain already seeded."""
    organization_id = connection.execute(
        text("SELECT id FROM organization WHERE slug = 'default'")
    ).scalar_one()
    workspace_id = connection.execute(text("SELECT id FROM workspace LIMIT 1")).scalar_one()
    return str(organization_id), str(workspace_id)


def _seed_pre_convergence(connection: Connection) -> dict[str, Any]:
    """A database as an upgrading deployment has it: two identity tables, in use.

    Three ``users`` rows, covering every case the fold has to tell apart: an
    operator-defined id, the shadow row tenancy minted for a member (keyed on
    that member's UUID rendered as a string), and a soft-deleted one. Plus a live
    API key on the first, and one request-plane row in each of the ten tables.
    """
    organization_id, workspace_id = _tenancy_ids(connection)
    member_id = uuid.uuid4()

    connection.execute(
        text(
            'INSERT INTO "user" (id, email, is_active, is_superuser, full_name, '
            "active_organization_id, default_organization_id, created_at) "
            "VALUES (:id, :email, 1, 0, 'Ada', :org, :org, CURRENT_TIMESTAMP)"
        ),
        {"id": member_id.hex, "email": "ada@example.com", "org": organization_id},
    )
    connection.execute(
        text(
            "INSERT INTO budgets (budget_id, name, max_budget, created_at, updated_at) "
            "VALUES ('cap', 'cap', 10.0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO users (user_id, alias, spend, reserved, budget_id, blocked, "
            "deleted_at, created_at, updated_at, metadata) VALUES "
            "('alice', 'Alice', 1.5, 0.25, 'cap', 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '{}'), "
            "(:member, 'Ada', 2.5, 0, NULL, 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '{}'), "
            "('gone', NULL, 0, 0, NULL, 0, '2026-01-01 00:00:00', CURRENT_TIMESTAMP, "
            " CURRENT_TIMESTAMP, '{}')"
        ),
        {"member": str(member_id)},
    )

    scope = {"ws": workspace_id, "hash": hash_key(_PLAINTEXT_KEY)}
    statements = (
        "INSERT INTO api_keys (id, key_hash, key_name, user_id, created_at, is_active, metadata, "
        "  key_prefix, exclude_from_budget, workspace_id) "
        "VALUES ('k-live', :hash, 'field key', 'alice', CURRENT_TIMESTAMP, 1, '{}', 'gw-a', 0, :ws)",
        "INSERT INTO usage_logs (id, api_key_id, user_id, timestamp, model, endpoint, status, source, "
        "  counts_toward_budget, workspace_id, cost) "
        "VALUES ('u1', 'k-live', 'alice', CURRENT_TIMESTAMP, 'm', '/v1/chat/completions', 'success', "
        "  'gateway', 1, :ws, 0.5)",
        "INSERT INTO budget_reset_logs (user_id, budget_id, previous_spend, reset_at) "
        "VALUES ('alice', 'cap', 3.0, CURRENT_TIMESTAMP)",
        "INSERT INTO model_aliases (id, name, target, user_id, created_at, updated_at, workspace_id) "
        "VALUES ('a1', 'fast', 'openai:gpt-4o-mini', 'alice', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :ws)",
        "INSERT INTO model_aliases (id, name, target, user_id, created_at, updated_at, workspace_id) "
        "VALUES ('a2', 'fast', 'openai:gpt-4o', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :ws)",
        "INSERT INTO routing_policies (id, name, spec, user_id, created_at, updated_at, workspace_id) "
        "VALUES ('p1', 'cheap', '{}', 'alice', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :ws)",
        "INSERT INTO routing_memory (id, user_id, workspace_id, embedding_model, embedding, qualities, "
        "  label_source, created_at) "
        "VALUES ('r1', 'alice', :ws, 'e', '[0.1]', '{}', 'human', CURRENT_TIMESTAMP)",
        "INSERT INTO router_preferences (id, user_id, workspace_id, prompt, scores, label_source, created_at) "
        "VALUES ('rp1', 'alice', :ws, 'hi', '{}', 'human', CURRENT_TIMESTAMP)",
        "INSERT INTO file_objects (id, user_id, workspace_id, filename, mime_type, bytes, purpose, "
        "  storage_ref, created_at, metadata) "
        "VALUES ('f1', 'alice', :ws, 'a.txt', 'text/plain', 3, 'user_data', 'ref', CURRENT_TIMESTAMP, '{}')",
        "INSERT INTO batches (id, provider, user_id, api_key_id, model, created_at, workspace_id) "
        "VALUES ('b-1', 'openai', 'alice', 'k-live', 'm', CURRENT_TIMESTAMP, :ws)",
        "INSERT INTO agent_telemetry (id, api_key_id, user_id, timestamp, name, source, dedup_key, created_at) "
        "VALUES ('t1', 'k-live', 'alice', CURRENT_TIMESTAMP, 'tool_result', 'claude_code', 'd1', "
        "  CURRENT_TIMESTAMP)",
    )
    for statement in statements:
        connection.execute(text(statement), scope)

    return {"member_id": member_id, "workspace_id": workspace_id}


@pytest.fixture
def before_convergence(tmp_path: Path) -> Iterator[tuple[Config, Engine, dict[str, Any]]]:
    """A populated SQLite database at the revision before the convergence."""
    database_url = f"sqlite:///{tmp_path / 'convergence.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, _BEFORE_CONVERGENCE)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        seeded = _seed_pre_convergence(connection)
    try:
        yield config, engine, seeded
    finally:
        engine.dispose()


def _owner_of(engine: Engine, table: str) -> str | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(f'SELECT u.external_id FROM {table} t JOIN "user" u ON u.id = t.user_id')  # noqa: S608
        ).first()
    return None if row is None else str(row[0])


def test_every_request_plane_row_keeps_a_resolvable_owner(
    before_convergence: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """The no-orphaned-billable-rows requirement, checked on all ten tables.

    A row whose owner does not resolve is worse than a lost row: it is spend
    nobody can attribute, on a table (``usage_logs``, ``batches``,
    ``budget_reset_logs``) that exists to answer who owes what.
    """
    config, engine, _ = before_convergence
    command.upgrade(config, _CONVERGENCE_REVISION)

    for table in _SCOPED:
        with engine.connect() as connection:
            stranded = connection.execute(
                text(  # noqa: S608 - table names are the literals above
                    f'SELECT COUNT(*) FROM {table} WHERE user_id IS NOT NULL '
                    f'AND user_id NOT IN (SELECT id FROM "user")'
                )
            ).scalar_one()
        assert stranded == 0, table
        assert _owner_of(engine, table) is not None, table


def test_the_shadow_attribution_row_merges_rather_than_duplicating(
    before_convergence: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """The workaround otari-ai#1727 was filed against, removed rather than carried.

    Tenancy used to mint a ``users`` row per member, keyed on the member's UUID
    rendered as a string. Those are the same identity, so the fold has to
    recognize them and bring their counters across; minting a second identity
    beside the member would leave the member unable to own a key and its spend
    stranded on a row nothing joins to.
    """
    config, engine, seeded = before_convergence
    member_id = seeded["member_id"]
    command.upgrade(config, _CONVERGENCE_REVISION)

    with engine.connect() as connection:
        rows = connection.execute(
            text('SELECT external_id, spend, reserved, alias FROM "user" ORDER BY external_id')
        ).all()
        identities = {str(row[0]): row for row in rows}

    # Three ``users`` rows and one pre-existing identity became three identities,
    # not four: the shadow row is the identity it shadowed.
    assert len(identities) == 3
    assert str(member_id) in identities
    assert float(identities[str(member_id)][1]) == 2.5
    assert float(identities["alice"][1]) == 1.5
    assert float(identities["alice"][2]) == 0.25


def test_a_soft_deleted_user_becomes_a_deactivated_identity(
    before_convergence: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """Its history stays resolvable and it cannot sign in, which is both halves."""
    config, engine = before_convergence[0], before_convergence[1]
    command.upgrade(config, _CONVERGENCE_REVISION)

    with engine.connect() as connection:
        deleted_at, is_active = connection.execute(
            text('SELECT deleted_at, is_active FROM "user" WHERE external_id = :handle'),
            {"handle": "gone"},
        ).one()
    assert deleted_at is not None
    assert not is_active


def test_the_rebuild_keeps_every_index_the_owner_column_leads(
    before_convergence: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """SQLite rebuilds each table to retype the column; the indexes have to survive it.

    Including the partial unique indexes on aliases and policies, which cover the
    workspace-wide rows the composite constraint cannot (both engines treat NULLs
    as distinct in a unique index).
    """
    config, engine = before_convergence[0], before_convergence[1]
    command.upgrade(config, _CONVERGENCE_REVISION)

    inspector = inspect(engine)
    for table, expected in _SURVIVING_INDEXES.items():
        present = {index["name"] for index in inspector.get_indexes(table)}
        assert expected <= present, (table, expected - present)


def test_the_owner_column_points_at_the_identity_with_its_nullability_kept(
    before_convergence: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """All ten, at ``user.id``, each as nullable as its model says."""
    config, engine = before_convergence[0], before_convergence[1]
    command.upgrade(config, _CONVERGENCE_REVISION)

    inspector = inspect(engine)
    for table, nullable in _SCOPED.items():
        owner = next(c for c in inspector.get_columns(table) if c["name"] == "user_id")
        assert owner["nullable"] is nullable, table
        targets = {
            fk["referred_table"] for fk in inspector.get_foreign_keys(table) if fk["constrained_columns"] == ["user_id"]
        }
        assert targets == {"user"}, table

    assert "users" not in inspector.get_table_names()


def test_the_downgrade_puts_the_rows_back_where_they_were(
    before_convergence: tuple[Config, Engine, dict[str, Any]],
) -> None:
    """Round trip: every owner is spelled as its handle again, counters intact."""
    config, engine, seeded = before_convergence
    command.upgrade(config, _CONVERGENCE_REVISION)
    command.downgrade(config, _BEFORE_CONVERGENCE)

    with engine.connect() as connection:
        restored = {
            str(row[0]): (float(row[1]), float(row[2]))
            for row in connection.execute(text("SELECT user_id, spend, reserved FROM users")).all()
        }
        owners = {
            table: connection.execute(text(f"SELECT user_id FROM {table} LIMIT 1")).scalar_one()  # noqa: S608
            for table in _SCOPED
        }

    assert restored["alice"] == (1.5, 0.25)
    assert restored[str(seeded["member_id"])] == (2.5, 0.0)
    assert restored["gone"] == (0.0, 0.0)
    # ``api_keys`` holds two rows only in the fixture's imagination; each of these
    # tables holds exactly one, and it belongs to the handle it always did.
    assert set(owners.values()) == {"alice"}


def test_a_key_minted_before_the_convergence_still_authenticates(tmp_path: Path) -> None:
    """The property nothing else in this change is worth having without.

    Live keys are in the field and cannot be re-issued, so the plaintext an
    operator is already sending has to keep resolving: to a row (the hash never
    moved), and through that row to an owner the budget gate accepts. Boots the
    real app on the migrated database rather than asserting on the schema,
    because the question is whether a request authenticates, not whether a
    column exists.
    """
    database_path = tmp_path / "surviving-key.db"
    database_url = f"sqlite:///{database_path}"
    config = _alembic_config(database_url)
    command.upgrade(config, _BEFORE_CONVERGENCE)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        _seed_pre_convergence(connection)
    command.upgrade(config, _CONVERGENCE_REVISION)
    engine.dispose()

    gateway_config = GatewayConfig(
        database_url=database_url,
        master_key="otari-mk-convergence",
        bootstrap_api_key=False,
        require_pricing=False,
    )
    with TestClient(create_app(gateway_config)) as client:
        authenticated = client.get("/v1/models", headers={API_KEY_HEADER: _PLAINTEXT_KEY})
        assert authenticated.status_code == 200, authenticated.text

        # And the owner still reads as the id the operator typed, so a key list,
        # a usage filter and a ``user`` field all still name the same thing.
        listed = client.get("/v1/keys", headers={API_KEY_HEADER: "otari-mk-convergence"})
        assert listed.status_code == 200, listed.text
        assert [key["user_id"] for key in listed.json()] == ["alice"]

        refused = client.get("/v1/models", headers={API_KEY_HEADER: "gw-not-a-key-anyone-ever-minted-here"})
        assert refused.status_code == 401
