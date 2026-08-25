"""Request-plane reads and writes against the one identity table.

Everything here resolves ``user`` rows by their ``external_id``, the
operator-defined handle the ``users`` table used to hold as its primary key
(otari-ai#1727). The wire still speaks that string everywhere; the ten
request-plane foreign keys store ``user.id`` instead, so the two spellings meet
here and nowhere else.
"""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from gateway.models.tenancy import User

# The owner a key falls back to when it is created without a user_id (the API's
# convenience path, and the first-run bootstrap key). One shared, visible,
# budgetable user rather than a throwaway per key, so nothing is untracked and the
# operator can cap all such keys with a single budget on this user.
DEFAULT_USER_ID = "default"


async def get_active_user(db: AsyncSession, external_id: str, *, for_update: bool = False) -> User | None:
    """Query for a non-deleted identity by its operator-defined handle."""

    stmt = select(User).where(col(User.external_id) == external_id, col(User.deleted_at).is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_user_by_id(db: AsyncSession, identity_id: uuid.UUID, *, for_update: bool = False) -> User | None:
    """Query for a non-deleted identity by primary key.

    The counterpart of :func:`get_active_user` for the paths that already hold
    the id a request-plane row stores (a key's owner, a batch's owner) and would
    otherwise round-trip it through the string to look the same row up again.
    """

    stmt = select(User).where(col(User.id) == identity_id, col(User.deleted_at).is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def external_id_for(db: AsyncSession, identity_id: uuid.UUID | None) -> str | None:
    """The handle a stored owner id spells on the wire, or ``None``.

    Deliberately not memoized. ``POST /v1/users`` revives a soft-deleted row
    rather than minting a second one, so the mapping is in practice immutable,
    but a process cache keyed on an id a test (or an operator deleting a
    database) can recreate is the kind of thing that hands back a handle naming
    no row, and the lookup it would save is one indexed primary-key read.
    """
    if identity_id is None:
        return None
    return (await db.execute(select(col(User.external_id)).where(col(User.id) == identity_id))).scalar_one_or_none()


async def external_ids_for(db: AsyncSession, identity_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """Handles for a page of stored owner ids, in one query.

    What every listing endpoint that echoes ``user_id`` uses: the rows come back
    carrying ids, and this turns the whole page into handles without a lookup
    per row.
    """
    wanted = {identity_id for identity_id in identity_ids if identity_id is not None}
    if not wanted:
        return {}
    rows = await db.execute(
        select(col(User.id), col(User.external_id)).where(col(User.id).in_(list(wanted)))
    )
    return {identity_id: external_id for identity_id, external_id in rows.all()}


async def resolve_identity_id(db: AsyncSession, external_id: str) -> uuid.UUID | None:
    """The stored owner id a handle names, deleted or not.

    Soft-deleted rows are included on purpose: a caller filtering usage or
    telemetry by a handle wants the history of the identity that handle named,
    and refusing to resolve it would silently answer "no rows" instead.
    """
    return (
        await db.execute(select(col(User.id)).where(col(User.external_id) == external_id))
    ).scalar_one_or_none()


async def resolve_identity_ids(db: AsyncSession, external_ids: Sequence[str]) -> dict[str, uuid.UUID]:
    """Stored owner ids for a list of handles, in one query."""
    if not external_ids:
        return {}
    rows = await db.execute(
        select(col(User.external_id), col(User.id)).where(col(User.external_id).in_(list(external_ids)))
    )
    return {external_id: identity_id for external_id, identity_id in rows.all()}


def owned_by_handles(owner_column: Any, handles: Sequence[str]) -> ColumnElement[bool]:
    """Match rows whose stored owner is one of ``handles``.

    The read-side counterpart of :func:`resolve_identity_ids`, for the filter
    builders that are synchronous and have to compose into someone else's
    statement (usage, telemetry, bulk delete). A subquery rather than a join so
    the condition drops into a ``WHERE`` unchanged, which is what keeps a
    listing, its ``/count``, and the delete that follows them scoping the same
    rows.
    """
    matched: ColumnElement[bool] = owner_column.in_(
        select(col(User.id)).where(col(User.external_id).in_(list(handles)))
    )
    return matched


async def _revive(user: User) -> User:
    """Clear a soft delete so the shared default owner is usable again."""
    if user.deleted_at is not None:
        user.deleted_at = None
    return user


async def get_or_create_default_user(db: AsyncSession, *, organization_id: uuid.UUID) -> User:
    """Return the shared ``default`` identity, creating (or reviving) it if needed.

    The caller still owns the final commit. The insert goes through a SAVEPOINT so
    that losing a race to a concurrent creator rolls back only this row, not
    whatever the caller has already staged: ``external_id`` is unique, so
    without this the loser's commit would raise and surface as a 500 for a request
    that should simply have reused the row the winner just created.

    ``organization_id`` is required because ``user.active_organization_id`` is
    NOT NULL: an identity always belongs somewhere. Callers pass the
    deployment's default organization, which is the same scope a master-key
    write already lands in.
    """
    existing = (
        await db.execute(select(User).where(col(User.external_id) == DEFAULT_USER_ID))
    ).scalar_one_or_none()
    if existing is not None:
        return await _revive(existing)

    user = User(
        external_id=DEFAULT_USER_ID,
        alias="Default",
        active_organization_id=organization_id,
    )
    try:
        async with db.begin_nested():
            db.add(user)
        return user
    except IntegrityError:
        # Someone else inserted it between our select and our flush; adopt theirs.
        winner = (
            await db.execute(select(User).where(col(User.external_id) == DEFAULT_USER_ID))
        ).scalar_one_or_none()
        if winner is None:
            raise
        return await _revive(winner)


async def live_identity_ids(db: AsyncSession, identity_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    """Return which of ``identity_ids`` name a usable request-plane owner.

    One query for the whole roster rather than a lookup per member. A row that is
    absent or soft-deleted is left out, so the caller reports ``None`` rather than
    an id that ``POST /v1/keys`` would reject.
    """
    if not identity_ids:
        return set()
    rows = await db.execute(
        select(col(User.id)).where(col(User.id).in_(list(identity_ids)), col(User.deleted_at).is_(None))
    )
    return set(rows.scalars().all())
