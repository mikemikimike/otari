"""Converge the two revisions that claimed ``a3c7e1b9d5f2`` as their parent.

``b6e8c2a4d7f1`` (#640, ``scoped_budgets.reset_alignment``) and
``f2a4c6d8b0e3`` (#667, three ``user`` credential columns) were authored in
parallel against the same parent and merged in that order, which left two heads:
Alembic accepts the pair without complaint until ``upgrade head`` refuses to
choose between them.

A merge revision rather than re-parenting one of the two. Re-parenting would
strand any database that already ran ``b6e8c2a4d7f1`` from ``a3c7e1b9d5f2``,
which is what running the app on #640's branch before it merged, or
``upgrade heads``, would do: the revision would become the head, ``upgrade
head`` a no-op, and #667's columns would never be created, silently, until
tenancy code touched them. This converges from either side, so both of those
databases and a fresh one all reach one head.

Empty by design: the two strands are independent (a ``scoped_budgets`` rebuild
against added ``user`` columns), so there is nothing to reconcile beyond the
chain itself.

Revision ID: d0f2b4a6c8e1
Revises: ('f2a4c6d8b0e3', 'b6e8c2a4d7f1')
Create Date: 2026-08-20
"""

from collections.abc import Sequence

revision: str = "d0f2b4a6c8e1"
down_revision: str | Sequence[str] | None = ("f2a4c6d8b0e3", "b6e8c2a4d7f1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to do: this revision exists to leave one head."""


def downgrade() -> None:
    """Nothing to undo; splitting the chain again is what ``downgrade`` of the two strands does."""
