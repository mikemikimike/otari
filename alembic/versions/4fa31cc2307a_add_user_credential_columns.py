"""Add nullable credential columns to user.

Revision ID: 4fa31cc2307a
Revises: a3c7e1b9d5f2
Create Date: 2026-08-19 21:27:29.965175

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4fa31cc2307a"
down_revision: str | Sequence[str] | None = "a3c7e1b9d5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # All nullable, no server_default: existing identities stay NULL on every
    # one of these, which is what "unread by anything yet" (otari#645) means
    # in the schema. oauth_provider is a plain string rather than a DB-level
    # enum so the chain stays dialect-neutral for SQLite.
    op.add_column("user", sa.Column("hashed_password", sa.String(), nullable=True))
    op.add_column("user", sa.Column("oauth_provider", sa.String(length=50), nullable=True))
    op.add_column("user", sa.Column("email_verification_token", sa.String(), nullable=True))
    op.add_column("user", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    # Unique like user.email: nullable so most rows carry no pending
    # verification, unique so the verification flow can look an identity up
    # by the token it was issued.
    op.create_index(op.f("ix_user_email_verification_token"), "user", ["email_verification_token"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_email_verification_token"), table_name="user")
    # Batch mode: SQLite has no ALTER TABLE ... DROP COLUMN, so dropping any of
    # these on that engine requires the table-rebuild path.
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("terms_accepted_at")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_verification_token")
        batch_op.drop_column("oauth_provider")
        batch_op.drop_column("hashed_password")
