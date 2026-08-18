"""Unit tests for platform_identity.ensure_local_user.

Real SQLite engine per test, mirroring test_runtime_settings_service.py's
pattern: this touches the users table's unique constraint (the PK), which an
in-memory mock session cannot exercise honestly. Engine creation, use, and
disposal all happen inside one asyncio.run() per test, so aiosqlite's
background connection thread is torn down before that call's event loop
closes (disposing it after would leak the thread into whatever test runs
next, surfacing as an unrelated "Event loop is closed" warning there).
"""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from gateway.models.entities import Base, User
from gateway.services.platform_identity import (
    SHADOW_USER_ORIGIN,
    ensure_local_user,
    reset_known_user_cache,
)


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    reset_known_user_cache()


async def _make_engine(tmp_path: Path) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def test_ensure_local_user_creates_a_shadow_row(tmp_path: Path) -> None:
    async def _run() -> User | None:
        engine = await _make_engine(tmp_path)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                returned_id = await ensure_local_user(session, "plat-user-1")
                assert returned_id == "plat-user-1"
            async with factory() as session:
                found: User | None = await session.scalar(select(User).where(User.user_id == "plat-user-1"))
                return found
        finally:
            await engine.dispose()

    user = asyncio.run(_run())
    assert user is not None
    assert user.blocked is False
    assert user.budget_id is None
    assert user.allowed_models is None
    assert user.metadata_ == {"origin": SHADOW_USER_ORIGIN}


def test_ensure_local_user_is_idempotent(tmp_path: Path) -> None:
    """Re-running for the same identity is a no-op, not a duplicate-key error."""

    async def _run() -> int:
        engine = await _make_engine(tmp_path)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                await ensure_local_user(session, "plat-user-2")
            reset_known_user_cache()  # force past the in-process cache, onto the DB path
            async with factory() as session:
                await ensure_local_user(session, "plat-user-2")
            async with factory() as session:
                rows = (await session.scalars(select(User).where(User.user_id == "plat-user-2"))).all()
                return len(rows)
        finally:
            await engine.dispose()

    assert asyncio.run(_run()) == 1


def test_ensure_local_user_concurrent_first_use_does_not_raise(tmp_path: Path) -> None:
    """Two requests racing to create the same identity's shadow row must not
    surface a duplicate-key error into either request; on_conflict_do_nothing
    is what makes this safe rather than a check-then-insert."""

    async def _run() -> int:
        engine = await _make_engine(tmp_path)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)

            async def _ensure() -> None:
                async with factory() as session:
                    await ensure_local_user(session, "plat-user-race")

            await asyncio.gather(_ensure(), _ensure())
            async with factory() as session:
                rows = (await session.scalars(select(User).where(User.user_id == "plat-user-race"))).all()
                return len(rows)
        finally:
            await engine.dispose()

    assert asyncio.run(_run()) == 1


def test_ensure_local_user_does_not_touch_an_existing_operator_created_row(tmp_path: Path) -> None:
    """A platform identity that happens to collide with an operator-created
    user (e.g. a standalone user_id an operator later re-parents through the
    bridge) must not be overwritten: on_conflict_do_nothing leaves it alone."""

    async def _run() -> User | None:
        engine = await _make_engine(tmp_path)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                session.add(User(user_id="shared-id", alias="operator's user", blocked=True))
                await session.commit()
            async with factory() as session:
                await ensure_local_user(session, "shared-id")
            async with factory() as session:
                found: User | None = await session.scalar(select(User).where(User.user_id == "shared-id"))
                return found
        finally:
            await engine.dispose()

    user = asyncio.run(_run())
    assert user is not None
    assert user.alias == "operator's user"
    assert user.blocked is True
    assert user.metadata_ == {}


def test_ensure_local_user_second_call_hits_the_in_process_cache(tmp_path: Path) -> None:
    """A second call for an already-known identity, within the same process,
    does no DB work at all: the session is never touched."""

    async def _run() -> None:
        engine = await _make_engine(tmp_path)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                await ensure_local_user(session, "plat-user-cached")
            # A closed session would raise if ensure_local_user tried to use
            # it; reaching the cached branch must never do that.
            async with factory() as session:
                await session.close()
                await ensure_local_user(session, "plat-user-cached")
        finally:
            await engine.dispose()

    asyncio.run(_run())
