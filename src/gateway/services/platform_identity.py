"""Bridge a platform-supplied caller identity onto a local shadow ``User`` row.

Hybrid mode has no local user directory; the platform is the identity
authority there. But this gateway's own survival tables (``model_aliases``,
``routing_policies``, ``routing_memory``, ``router_preferences``,
``file_objects``, ``batches``) all carry a foreign key to ``users.user_id``,
four of them ``NOT NULL``, so keying anything on a hybrid caller's identity
needs a local row for that key to point at. This module creates that row on
first sight of a platform ``user_id`` and never touches it again: a shadow row
is deliberately not synchronized with the platform user's alias, blocked
status, or anything else the platform owns.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models.entities import User

# Provenance marker distinguishing a platform-originated shadow row from one
# an operator created directly (standalone /v1/users), so a future
# re-parenting pass (see otari-ai#1643's fan-out) can tell them apart.
SHADOW_USER_ORIGIN = "platform"

# In-process cache of platform user ids already known to have a local row.
# A write-through set, not a TTL cache like alias_service's: a shadow row is
# created once and never edited or deleted, so there is nothing to
# invalidate and no refresher to converge sibling workers on.
_known_user_ids: set[str] = set()


async def ensure_local_user(db: AsyncSession, platform_user_id: str) -> str:
    """Idempotently ensure a local ``User`` row exists for a platform identity.

    Returns ``platform_user_id`` unchanged; the point of this call is the
    side effect, and the return value only saves the caller a redundant
    variable. Race-safe under concurrent first requests for the same
    identity: the write is a dialect-native "insert, do nothing on conflict"
    rather than a check-then-insert, so two workers racing to create the same
    row never raise a duplicate-key error into a request path.
    """
    if platform_user_id in _known_user_ids:
        return platform_user_id

    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    insert_stmt = pg_insert if dialect_name == "postgresql" else sqlite_insert
    stmt = (
        insert_stmt(User)
        .values(
            user_id=platform_user_id,
            budget_id=None,
            blocked=False,
            allowed_models=None,
            metadata_={"origin": SHADOW_USER_ORIGIN},
        )
        .on_conflict_do_nothing(index_elements=[User.user_id])
    )
    await db.execute(stmt)
    await db.commit()
    _known_user_ids.add(platform_user_id)
    return platform_user_id


def reset_known_user_cache() -> None:
    """Clear the in-process cache. Test-only; nothing in production needs this."""
    _known_user_ids.clear()
