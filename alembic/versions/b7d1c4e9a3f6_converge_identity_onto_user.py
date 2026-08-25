"""Converge otari's two identities onto ``user``.

``users`` (string primary key, ``spend``, ``reserved``) and ``user`` (UUID
primary key, tenancy) were two tables describing one thing, and every
request-plane foreign key pointed at the first one. otari-ai#1727 settles that:
``user`` is the identity, the ten request-plane foreign keys point at ``user.id``,
and the operator-defined string survives as ``user.external_id``.

**Nothing an operator typed changes spelling.** ``external_id`` is unique and
indexed and carries the old primary key verbatim, so a live API key still
resolves to its owner, a ``user`` field on a request still matches, and a
``config.yml`` scoped to a user still applies. Only the storage moved.

**The shadow rows merge rather than duplicate.** A tenancy member could not own a
key without a ``users`` row minted for it, keyed on the member's UUID rendered as
a string. Those rows are recognized here (their id parses as a UUID naming a live
identity) and folded onto the identity itself, counters included, which is the
workaround being removed rather than carried. Every other ``users`` row becomes a
new identity in the deployment's default organization, active exactly when it was
not soft-deleted, matching what the reconciliation spec says a migrated gateway
user becomes.

**Add, backfill, swap, rather than a single ALTER.** Each of the ten tables gets a
UUID column beside its string one, has it filled from the identity table in one
statement, and only then loses the old column, which is the shape that keeps a
half-applied step recoverable and the one both engines can do. SQLite cannot
alter a constraint at all, so the swap runs through ``batch_alter_table`` there
and rebuilds the table; the indexes that lead with ``user_id`` are dropped and
recreated explicitly rather than left to reflection, because PostgreSQL drops
them with the column and would not bring them back.

The new columns follow the models rather than the old DDL where the two had
drifted: ``budget_reset_logs.user_id`` becomes nullable (it has always been
declared nullable, and its ``ON DELETE SET NULL`` could never have fired while
the column refused NULL), and every foreign key is created with the ``ondelete``
its model declares.

Revision ID: b7d1c4e9a3f6
Revises: d2f5b8c0e4a7
Create Date: 2026-08-25
"""

import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "b7d1c4e9a3f6"
down_revision: str | None = "d2f5b8c0e4a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match provisioning_service, which looks the default up by these values
# and only creates one when the lookup misses.
DEFAULT_ORGANIZATION_NAME = "Default organization"
DEFAULT_ORGANIZATION_SLUG = "default"


class _Scoped:
    """One request-plane table's owner column, as it has to be rebuilt."""

    def __init__(self, table: str, *, nullable: bool, ondelete: str, indexes: tuple[tuple[str, tuple[str, ...]], ...]):
        self.table = table
        self.nullable = nullable
        self.ondelete = ondelete
        # Every index that leads with (or contains) the owner column, with the
        # columns it spans. Recreated verbatim after the swap.
        self.indexes = indexes


# The ten, in no significant order: nothing here depends on another's state.
SCOPED: tuple[_Scoped, ...] = (
    _Scoped(
        "api_keys",
        nullable=True,
        ondelete="CASCADE",
        indexes=(("ix_api_keys_user_id", ("user_id",)),),
    ),
    _Scoped(
        "usage_logs",
        nullable=True,
        ondelete="SET NULL",
        indexes=(
            ("ix_usage_logs_user_id", ("user_id",)),
            ("ix_usage_logs_user_id_timestamp", ("user_id", "timestamp")),
        ),
    ),
    _Scoped(
        "budget_reset_logs",
        nullable=True,
        ondelete="SET NULL",
        indexes=(("ix_budget_reset_logs_user_id", ("user_id",)),),
    ),
    _Scoped(
        "model_aliases",
        nullable=True,
        ondelete="CASCADE",
        indexes=(("ix_model_aliases_user_id", ("user_id",)),),
    ),
    _Scoped(
        "routing_policies",
        nullable=True,
        ondelete="CASCADE",
        indexes=(("ix_routing_policies_user_id", ("user_id",)),),
    ),
    _Scoped(
        "routing_memory",
        nullable=False,
        ondelete="CASCADE",
        indexes=(
            ("ix_routing_memory_user_id", ("user_id",)),
            ("ix_routing_memory_workspace_user_model", ("workspace_id", "user_id", "embedding_model")),
            ("ix_routing_memory_workspace_user_created", ("workspace_id", "user_id", "created_at")),
            (
                "ix_routing_memory_workspace_user_model_task",
                ("workspace_id", "user_id", "embedding_model", "task_id"),
            ),
        ),
    ),
    _Scoped(
        "router_preferences",
        nullable=False,
        ondelete="CASCADE",
        indexes=(
            ("ix_router_preferences_user_id", ("user_id",)),
            ("ix_router_preferences_workspace_user_created", ("workspace_id", "user_id", "created_at")),
        ),
    ),
    _Scoped(
        "file_objects",
        nullable=False,
        ondelete="CASCADE",
        indexes=(("ix_file_objects_user_id", ("user_id",)),),
    ),
    _Scoped(
        "batches",
        nullable=False,
        ondelete="CASCADE",
        indexes=(("ix_batches_user_id", ("user_id",)),),
    ),
    _Scoped(
        "agent_telemetry",
        nullable=True,
        ondelete="SET NULL",
        indexes=(
            ("ix_agent_telemetry_user_id", ("user_id",)),
            ("ix_agent_telemetry_user_id_timestamp", ("user_id", "timestamp")),
        ),
    ),
)

# The two tables whose uniqueness spans the owner column, and the partial index
# that covers the workspace-wide (NULL owner) rows the composite constraint
# cannot. Both lead with ``workspace_id`` since the survivals change widened
# them, and are rebuilt here exactly as they are rather than narrowed back.
_SCOPED_UNIQUE: dict[str, tuple[str, str]] = {
    "model_aliases": ("uq_model_aliases_workspace_name_user", "uq_model_aliases_workspace_global_name"),
    "routing_policies": (
        "uq_routing_policies_workspace_name_user",
        "uq_routing_policies_workspace_global_name",
    ),
}

# The request-plane columns that move from ``users`` onto ``user``, in the order
# the copy below reads them.
_CARRIED = (
    "alias",
    "spend",
    "reserved",
    "budget_id",
    "allowed_models",
    "budget_started_at",
    "next_budget_reset_at",
    "blocked",
    "deleted_at",
    "metadata",
)


def _uuid_literal(bind: sa.engine.Connection, value: uuid.UUID) -> str:
    """Render a UUID the way this dialect stores one.

    ``sa.Uuid`` is native on PostgreSQL and CHAR(32) hex on SQLite, so a value
    bound as a plain string has to match the storage form or it joins to nothing.
    """
    return value.hex if bind.dialect.name == "sqlite" else str(value)


def _default_organization_id(bind: sa.engine.Connection) -> uuid.UUID:
    """The organization a migrated gateway user belongs to.

    ``user.active_organization_id`` is NOT NULL, so every row created here needs
    one. Same slug ``provisioning_service`` and the workspace-scope migration
    look up, so whichever ran first wins and this adopts it rather than creating
    a second default. Falls back to the oldest organization before minting one,
    matching ``services/workspace_scope.default_workspace_id``: an operator who
    renamed the default must not end up with two.
    """
    found = bind.execute(
        sa.text("SELECT id FROM organization WHERE slug = :slug"), {"slug": DEFAULT_ORGANIZATION_SLUG}
    ).scalar()
    if found is not None:
        return uuid.UUID(str(found))

    found = bind.execute(sa.text("SELECT id FROM organization ORDER BY created_at, id LIMIT 1")).scalar()
    if found is not None:
        return uuid.UUID(str(found))

    organization_id = uuid.uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO organization (id, name, slug, created_by_user_id, created_at) "
            "VALUES (:id, :name, :slug, NULL, CURRENT_TIMESTAMP)"
        ),
        {
            "id": _uuid_literal(bind, organization_id),
            "name": DEFAULT_ORGANIZATION_NAME,
            "slug": DEFAULT_ORGANIZATION_SLUG,
        },
    )
    return organization_id


def _add_identity_columns() -> None:
    """The request-plane half of the identity row, all nullable for the backfill."""
    op.add_column("user", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("alias", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("spend", sa.Numeric(precision=18, scale=6), nullable=False, server_default="0"))
    op.add_column("user", sa.Column("reserved", sa.Numeric(precision=18, scale=6), nullable=False, server_default="0"))
    op.add_column("user", sa.Column("budget_id", sa.String(), nullable=True))
    op.add_column("user", sa.Column("allowed_models", sa.JSON(), nullable=True))
    op.add_column("user", sa.Column("budget_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("next_budget_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index(op.f("ix_user_budget_id"), "user", ["budget_id"], unique=False)
    op.create_index(op.f("ix_user_deleted_at"), "user", ["deleted_at"], unique=False)
    with op.batch_alter_table("user") as batch:
        batch.create_foreign_key("fk_user_budget_id_budgets", "budgets", ["budget_id"], ["budget_id"])


def _json_typed(statement: sa.TextClause) -> sa.TextClause:
    """Bind the two JSON parameters as JSON on whichever engine is underneath."""
    return statement.bindparams(
        sa.bindparam("allowed_models", type_=sa.JSON()),
        sa.bindparam("metadata", type_=sa.JSON()),
    )


def _fold_users_into_identities(bind: sa.engine.Connection) -> None:
    """Give every identity an ``external_id``, and every gateway user an identity."""
    identities = {
        uuid.UUID(str(row[0])): row[1] for row in bind.execute(sa.text('SELECT id, alias FROM "user"')).fetchall()
    }
    for identity_id in identities:
        # Written per row rather than derived in SQL: the id renders as CHAR(32)
        # hex on SQLite and dashed on PostgreSQL, and the handle has to be the
        # dashed form on both, because that is the spelling the roster already
        # published as ``attribution_user_id`` and the one a shadow row holds.
        bind.execute(
            sa.text('UPDATE "user" SET external_id = :handle WHERE id = :id'),
            {"handle": str(identity_id), "id": _uuid_literal(bind, identity_id)},
        )

    quoted = ", ".join(f'"{column}"' for column in _CARRIED)
    # Typed on the way out and on the way back in. psycopg2 hands a ``json``
    # column back as a Python object and refuses to bind one again, while SQLite
    # hands back the raw text; naming the type on both ends is what makes one
    # statement work on either engine instead of double-encoding on one of them.
    rows = bind.execute(
        sa.text(f"SELECT user_id, created_at, updated_at, {quoted} FROM users").columns(
            allowed_models=sa.JSON(), metadata=sa.JSON()
        )
    ).fetchall()
    if not rows:
        return

    merged_assignments = ", ".join(f'"{column}" = :{column}' for column in _CARRIED if column != "alias")
    placeholders = ", ".join(f":{column}" for column in _CARRIED)
    organization_id: uuid.UUID | None = None

    for row in rows:
        handle = str(row[0])
        values: dict[str, Any] = dict(zip(_CARRIED, row[3:], strict=True))
        merged = _merged_identity(handle, identities)
        if merged is not None:
            # A shadow attribution row: the identity already exists, so its
            # counters and budget window come across and nothing new is minted.
            # That is the workaround this issue was filed against, removed here
            # rather than carried forward.
            alias = values.pop("alias")
            bind.execute(
                _json_typed(sa.text(f'UPDATE "user" SET {merged_assignments} WHERE id = :identity')),
                {**values, "identity": _uuid_literal(bind, merged)},
            )
            # The alias only fills a gap: an identity's own is the one a human
            # set, and the shadow row's was derived from it.
            if alias is not None and identities[merged] is None:
                bind.execute(
                    sa.text('UPDATE "user" SET alias = :alias WHERE id = :identity'),
                    {"alias": alias, "identity": _uuid_literal(bind, merged)},
                )
            continue

        if organization_id is None:
            organization_id = _default_organization_id(bind)
        identity_id = uuid.uuid4()
        bind.execute(
            _json_typed(
                sa.text(
                    f'INSERT INTO "user" (id, external_id, email, is_active, is_superuser, full_name, '
                    f"active_organization_id, default_organization_id, created_at, updated_at, {quoted}) "
                    f"VALUES (:identity, :external_id, NULL, :is_active, :is_superuser, NULL, "
                    f":organization_id, :organization_id, :created_at, :updated_at, {placeholders})"
                )
            ),
            {
                **values,
                "identity": _uuid_literal(bind, identity_id),
                "external_id": handle,
                # A soft-deleted gateway user becomes a deactivated identity, so
                # its history stays resolvable without it being able to sign in.
                # Same mapping ``UserRepository.create_local_identity`` documents.
                "is_active": values["deleted_at"] is None,
                "is_superuser": False,
                "organization_id": _uuid_literal(bind, organization_id),
                "created_at": row[1],
                "updated_at": row[2],
            },
        )


def _merged_identity(handle: str, identities: dict[uuid.UUID, Any]) -> uuid.UUID | None:
    """The identity a ``users`` row is a shadow of, when it is one.

    otari's tenancy minted a request-plane row per member keyed on the member's
    UUID rendered as a string, so a handle that parses as a UUID naming a live
    identity is that row rather than an operator-defined id. A handle that merely
    looks like a UUID but names no identity is treated as an ordinary gateway
    user, which is the conservative reading: it gets its own identity and keeps
    its history.
    """
    try:
        parsed = uuid.UUID(handle)
    except ValueError:
        return None
    return parsed if parsed in identities else None


def _orphan_guard(bind: sa.engine.Connection, table: str, column: str) -> None:
    """Refuse to tighten a column that did not resolve for every row.

    SQLite does not enforce foreign keys unless a deployment turned them on, so
    a row can name an owner that never existed. Tightening around it would fail
    with a bare NOT NULL violation naming no table; this says which one, and
    stops before anything is dropped.
    """
    stranded = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")  # noqa: S608 - table names are literals above
    ).scalar_one()
    if stranded:
        msg = (
            f"{stranded} row(s) in {table} name an owner with no row in users, so they cannot be "
            "re-pointed at an identity. Delete them or give them a valid owner, then migrate again."
        )
        raise RuntimeError(msg)


def _swap_owner_column(bind: sa.engine.Connection, scoped: _Scoped) -> None:
    """Replace one table's string owner column with the identity's id."""
    table = scoped.table
    op.add_column(table, sa.Column("user_uuid", sa.Uuid(), nullable=True))
    # One statement rather than one per user: both engines correlate an UPDATE
    # against a subquery, and ``external_id`` is unique so it selects one row.
    op.execute(
        sa.text(
            f'UPDATE {table} SET user_uuid = (SELECT u.id FROM "user" u WHERE u.external_id = {table}.user_id)'  # noqa: S608
        )
    )
    if not scoped.nullable:
        _orphan_guard(bind, table, "user_uuid")

    unique = _SCOPED_UNIQUE.get(table)
    if unique is not None:
        op.drop_index(unique[1], table_name=table)
    for name, _columns in scoped.indexes:
        op.drop_index(name, table_name=table)

    # Two batches, not one. Alembic applies a batch's operations to a reflected
    # copy of the table and rebuilds it once; a constraint created in the same
    # batch that renames the column it names is built against the pre-rename
    # copy and silently does not survive the rebuild. The second batch sees the
    # column under its final name.
    with op.batch_alter_table(table) as batch:
        if unique is not None:
            batch.drop_constraint(unique[0], type_="unique")
        batch.drop_column("user_id")
        batch.alter_column("user_uuid", new_column_name="user_id", existing_type=sa.Uuid(), nullable=scoped.nullable)
    with op.batch_alter_table(table) as batch:
        batch.create_foreign_key(f"fk_{table}_user_id", "user", ["user_id"], ["id"], ondelete=scoped.ondelete)
        if unique is not None:
            batch.create_unique_constraint(unique[0], ["workspace_id", "name", "user_id"])

    for name, columns in scoped.indexes:
        op.create_index(name, table, list(columns), unique=False)
    if unique is not None:
        op.create_index(
            unique[1],
            table,
            ["workspace_id", "name"],
            unique=True,
            sqlite_where=sa.text("user_id IS NULL"),
            postgresql_where=sa.text("user_id IS NULL"),
        )


def upgrade() -> None:
    bind = op.get_bind()
    _add_identity_columns()
    _fold_users_into_identities(bind)

    # Only now: every row has one, and it is what the swap below joins on.
    with op.batch_alter_table("user") as batch:
        batch.alter_column("external_id", existing_type=sa.String(length=255), nullable=False)
    op.create_index(op.f("ix_user_external_id"), "user", ["external_id"], unique=True)

    for scoped in SCOPED:
        _swap_owner_column(bind, scoped)

    op.drop_index("ix_users_budget_id", table_name="users")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_table("users")


def _restore_users_table(bind: sa.engine.Connection) -> None:
    """Recreate ``users`` and repopulate it from the identities."""
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=True),
        sa.Column("spend", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("reserved", sa.Numeric(precision=18, scale=6), nullable=False, server_default="0"),
        sa.Column("budget_id", sa.String(), nullable=True),
        sa.Column("allowed_models", sa.JSON(), nullable=True),
        sa.Column("budget_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_budget_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.budget_id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_users_budget_id", "users", ["budget_id"], unique=False)
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"], unique=False)
    carried = ", ".join(f'"{column}"' for column in _CARRIED)
    # Every identity comes back as a gateway user, the ones tenancy minted
    # included: that is what the shadow rows were, and recreating them is what
    # makes the downgrade leave a database the pre-convergence code can serve.
    bind.execute(
        sa.text(
            f"INSERT INTO users (user_id, created_at, updated_at, {carried}) "
            f'SELECT external_id, created_at, COALESCE(updated_at, created_at), {carried} FROM "user"'
        )
    )


def _unswap_owner_column(scoped: _Scoped) -> None:
    """Put one table's string owner column back."""
    table = scoped.table
    op.add_column(table, sa.Column("user_handle", sa.String(), nullable=True))
    op.execute(
        sa.text(
            f'UPDATE {table} SET user_handle = (SELECT u.external_id FROM "user" u WHERE u.id = {table}.user_id)'
        )
    )

    unique = _SCOPED_UNIQUE.get(table)
    if unique is not None:
        op.drop_index(unique[1], table_name=table)
    for name, _columns in scoped.indexes:
        op.drop_index(name, table_name=table)

    with op.batch_alter_table(table) as batch:
        if unique is not None:
            batch.drop_constraint(unique[0], type_="unique")
        batch.drop_constraint(f"fk_{table}_user_id", type_="foreignkey")
        batch.drop_column("user_id")
        batch.alter_column(
            "user_handle", new_column_name="user_id", existing_type=sa.String(), nullable=scoped.nullable
        )
    with op.batch_alter_table(table) as batch:
        batch.create_foreign_key(
            f"fk_{table}_user_id_users", "users", ["user_id"], ["user_id"], ondelete=scoped.ondelete
        )
        if unique is not None:
            batch.create_unique_constraint(unique[0], ["workspace_id", "name", "user_id"])

    for name, columns in scoped.indexes:
        op.create_index(name, table, list(columns), unique=False)
    if unique is not None:
        op.create_index(
            unique[1],
            table,
            ["workspace_id", "name"],
            unique=True,
            sqlite_where=sa.text("user_id IS NULL"),
            postgresql_where=sa.text("user_id IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    _restore_users_table(bind)
    for scoped in SCOPED:
        _unswap_owner_column(scoped)

    op.drop_index(op.f("ix_user_external_id"), table_name="user")
    op.drop_index(op.f("ix_user_deleted_at"), table_name="user")
    op.drop_index(op.f("ix_user_budget_id"), table_name="user")
    with op.batch_alter_table("user") as batch:
        batch.drop_constraint("fk_user_budget_id_budgets", type_="foreignkey")
    for column in ("external_id", *_CARRIED):
        op.drop_column("user", column)
