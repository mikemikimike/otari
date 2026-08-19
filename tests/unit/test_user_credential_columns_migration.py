"""The user-credential-columns revision's Alembic chain, exercised on SQLite.

otari#645 adds five nullable columns to ``user`` ahead of the authentication
track. Driven against a real file database, like
``test_tenancy_schema_chain.py``, because the downgrade's column drops go
through SQLite's batch-mode table rebuild, and that rebuild is what could
silently lose the unique index on ``email_verification_token``.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text

_ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
_REVISION = "4fa31cc2307a"
_PREVIOUS_REVISION = "a3c7e1b9d5f2"
_NEW_COLUMNS = {
    "hashed_password",
    "oauth_provider",
    "email_verification_token",
    "email_verified_at",
    "terms_accepted_at",
}


def _alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture
def sqlite_at_head(tmp_path: Path) -> Iterator[tuple[Config, Engine]]:
    """A SQLite database migrated to head, with its config for further steps."""
    database_url = f"sqlite:///{tmp_path / 'user_credentials.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        yield config, engine
    finally:
        engine.dispose()


def test_alembic_chain_has_a_single_head() -> None:
    """otari#645's DoD: the chain must not fork."""
    script = ScriptDirectory.from_config(_alembic_config("sqlite:///:memory:"))
    assert script.get_heads() == [_REVISION]


def test_upgrade_adds_all_five_columns_nullable(sqlite_at_head: tuple[Config, Engine]) -> None:
    _, engine = sqlite_at_head
    columns = {column["name"]: column for column in inspect(engine).get_columns("user")}

    assert _NEW_COLUMNS <= columns.keys()
    assert all(columns[name]["nullable"] is True for name in _NEW_COLUMNS)


def test_email_verification_token_is_uniquely_indexed(sqlite_at_head: tuple[Config, Engine]) -> None:
    """Nullable and unique, matching ``user.email``'s existing shape."""
    _, engine = sqlite_at_head
    indexes = [
        index
        for index in inspect(engine).get_indexes("user")
        if index["column_names"] == ["email_verification_token"]
    ]
    assert [index["unique"] for index in indexes] == [True]


def test_existing_rows_survive_the_upgrade_with_new_columns_null(tmp_path: Path) -> None:
    """A v0.x database's rows must come through intact, per the issue's DoD."""
    url = f"sqlite:///{tmp_path / 'existing.db'}"
    config = _alembic_config(url)

    command.upgrade(config, _PREVIOUS_REVISION)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organization (id, slug, name, created_at) "
                    "VALUES ('11111111-1111-1111-1111-111111111111', 'ada-org', 'Ada Org', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO user (id, email, is_active, is_superuser, full_name, "
                    "active_organization_id, created_at) "
                    "VALUES ('22222222-2222-2222-2222-222222222222', 'ada@example.com', 1, 0, 'Ada', "
                    "'11111111-1111-1111-1111-111111111111', CURRENT_TIMESTAMP)"
                )
            )

        command.upgrade(config, "head")

        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT email, hashed_password, oauth_provider, email_verification_token, "
                    "email_verified_at, terms_accepted_at FROM user "
                    "WHERE id = '22222222-2222-2222-2222-222222222222'"
                )
            ).one()
            assert row.email == "ada@example.com"
            assert row.hashed_password is None
            assert row.oauth_provider is None
            assert row.email_verification_token is None
            assert row.email_verified_at is None
            assert row.terms_accepted_at is None
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_round_trips(sqlite_at_head: tuple[Config, Engine]) -> None:
    """A downgrade leaves nothing behind for the next upgrade to collide with."""
    config, engine = sqlite_at_head

    command.downgrade(config, _PREVIOUS_REVISION)
    columns = {column["name"] for column in inspect(engine).get_columns("user")}
    assert not (_NEW_COLUMNS & columns)

    command.upgrade(config, _REVISION)
    columns = {column["name"] for column in inspect(engine).get_columns("user")}
    assert _NEW_COLUMNS <= columns


def test_downgrade_leaves_the_rest_of_user_untouched(sqlite_at_head: tuple[Config, Engine]) -> None:
    """The batch-mode rebuild on downgrade must not lose pre-existing columns or the email index."""
    config, engine = sqlite_at_head

    command.downgrade(config, _PREVIOUS_REVISION)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("user")}
    assert {"id", "email", "is_active", "is_superuser", "full_name", "active_organization_id"} <= columns

    email_indexes = [index for index in inspector.get_indexes("user") if index["column_names"] == ["email"]]
    assert [index["unique"] for index in email_indexes] == [True]
