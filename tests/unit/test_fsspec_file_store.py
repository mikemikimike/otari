"""Unit tests for the fsspec-backed file store.

Runs on fsspec's built-in ``memory://`` and ``file://`` filesystems, so the
suite needs no cloud implementation package and no network. What it proves is
the adapter's own contract (refs, streaming, cleanup, error translation); the
cloud implementations are fsspec's to keep working.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from gateway.adapters.file_storage_adapter import FsspecFileStore, build_file_storage_port
from gateway.core.config import GatewayConfig

# The backend is an optional extra; the store module itself imports it lazily.
fsspec = pytest.importorskip("fsspec")


async def _iter(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


@pytest.fixture
def memory_root() -> str:
    # The memory filesystem is process-global; give each test its own prefix
    # and clear it afterwards so one test's blobs never show up in another.
    root = "memory://otari-test"
    fs = fsspec.filesystem("memory")
    if fs.exists("otari-test"):
        fs.rm("otari-test", recursive=True)
    return root


@pytest.mark.asyncio
async def test_put_get_roundtrip(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)
    ref = await store.put("file-abcdef0123", b"hello bytes")
    assert ref == "ab/file-abcdef0123"
    assert await store.get(ref) == b"hello bytes"


@pytest.mark.asyncio
async def test_put_stream_and_get_stream_roundtrip(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)
    payload = b"x" * (2 * 1024 * 1024 + 5)
    ref, size = await store.put_stream("file-streamtest01", _iter([payload[:1000], payload[1000:]]))
    assert size == len(payload)
    collected = bytearray()
    async for chunk in store.get_stream(ref):
        collected.extend(chunk)
    assert bytes(collected) == payload


@pytest.mark.asyncio
async def test_put_stream_removes_partial_blob_on_failure(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)

    async def _failing() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("client went away")

    with pytest.raises(RuntimeError):
        await store.put_stream("file-partial00001", _failing())
    assert await asyncio.to_thread(store._fs.find, store._root) == []


@pytest.mark.asyncio
async def test_put_stream_removes_partial_blob_on_cancellation(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)
    started = asyncio.Event()

    async def _slow() -> AsyncIterator[bytes]:
        yield b"first"
        started.set()
        await asyncio.sleep(30)
        yield b"never"

    task = asyncio.create_task(store.put_stream("file-cancel000001", _slow()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(store._fs.find, store._root) == []


@pytest.mark.asyncio
async def test_concurrent_streams_for_same_id_keep_distinct_objects(memory_root: str) -> None:
    first_store = FsspecFileStore(memory_root)
    second_store = FsspecFileStore(memory_root)
    file_id = "file-concurrentsamekey01"
    existing_ref = await first_store.put(file_id, b"existing")
    streams_ready = 0
    both_streams_ready = asyncio.Event()

    async def chunks(payload: bytes) -> AsyncIterator[bytes]:
        nonlocal streams_ready
        streams_ready += 1
        if streams_ready == 2:
            both_streams_ready.set()
        await both_streams_ready.wait()
        yield payload

    first_upload, second_upload = await asyncio.gather(
        first_store.put_stream(file_id, chunks(b"first")),
        second_store.put_stream(file_id, chunks(b"second")),
    )
    first_ref, first_size = first_upload
    second_ref, second_size = second_upload

    assert first_ref != existing_ref
    assert second_ref != existing_ref
    assert first_ref != second_ref
    assert first_size == len(b"first")
    assert second_size == len(b"second")
    assert await first_store.get(existing_ref) == b"existing"
    assert await first_store.get(first_ref) == b"first"
    assert await second_store.get(second_ref) == b"second"


@pytest.mark.asyncio
async def test_failed_publication_preserves_existing_blob(memory_root: str, monkeypatch: pytest.MonkeyPatch) -> None:
    store = FsspecFileStore(memory_root)
    file_id = "file-pubfail0001"
    ref = await store.put(file_id, b"existing")

    def failed_move(_source: str, _destination: str) -> None:
        raise OSError("publication failed")

    monkeypatch.setattr(store._fs, "mv", failed_move)

    with pytest.raises(OSError, match="publication failed"):
        await store.put_stream(file_id, _iter([b"replacement"]))

    assert await store.get(ref) == b"existing"
    assert await asyncio.to_thread(store._fs.find, store._root) == [store._resolve(ref)]


@pytest.mark.asyncio
async def test_failed_publication_removes_a_partial_new_blob(memory_root: str, monkeypatch: pytest.MonkeyPatch) -> None:
    store = FsspecFileStore(memory_root)

    def partial_move(_source: str, destination: str) -> None:
        store._fs.pipe_file(destination, b"partial")
        raise OSError("publication failed")

    monkeypatch.setattr(store._fs, "mv", partial_move)

    with pytest.raises(OSError, match="publication failed"):
        await store.put_stream("file-newpubfail0001", _iter([b"replacement"]))

    assert await asyncio.to_thread(store._fs.find, store._root) == []


@pytest.mark.asyncio
async def test_failed_destination_check_preserves_existing_blob(
    memory_root: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FsspecFileStore(memory_root)
    ref = await store.put("file-checkfail0001", b"existing")
    move_called = False

    def failed_exists(_candidate: str) -> bool:
        raise OSError("destination check failed")

    def unexpected_move(_source: str, _destination: str) -> None:
        nonlocal move_called
        move_called = True

    monkeypatch.setattr(store._fs, "exists", failed_exists)
    monkeypatch.setattr(store._fs, "mv", unexpected_move)

    with pytest.raises(OSError, match="destination check failed"):
        await store.put_stream("file-checkfail0001", _iter([b"replacement"]))

    assert not move_called
    assert await store.get(ref) == b"existing"
    assert await asyncio.to_thread(store._fs.find, store._root) == [store._resolve(ref)]


@pytest.mark.asyncio
async def test_cancellation_cleanup_preserves_a_concurrent_put(
    memory_root: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FsspecFileStore(memory_root)
    publication_started = threading.Event()
    release_publication = threading.Event()
    cleanup_started = threading.Event()
    release_cleanup = threading.Event()
    put_started = threading.Event()
    original_move = store._fs.mv
    original_remove = store._fs.rm
    original_pipe_file = store._fs.pipe_file
    final_paths: set[str] = set()

    def blocked_move(source: str, destination: str) -> None:
        original_move(source, destination)
        final_paths.add(destination)
        publication_started.set()
        if not release_publication.wait(timeout=5):
            raise TimeoutError("test did not release the publication operation")

    def blocked_remove(path: str, recursive: bool = False, maxdepth: int | None = None) -> None:
        if path in final_paths:
            cleanup_started.set()
            if not release_cleanup.wait(timeout=5):
                raise TimeoutError("test did not release published-file cleanup")
        original_remove(path, recursive=recursive, maxdepth=maxdepth)

    def tracked_pipe_file(path: str, data: bytes) -> None:
        if data == b"replacement":
            put_started.set()
        original_pipe_file(path, data)

    monkeypatch.setattr(store._fs, "mv", blocked_move)
    monkeypatch.setattr(store._fs, "rm", blocked_remove)
    monkeypatch.setattr(store._fs, "pipe_file", tracked_pipe_file)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"cancelled"

    stream_task = asyncio.create_task(store.put_stream("file-cancel-put-race", chunks()))
    put_task: asyncio.Task[str] | None = None
    try:
        assert await asyncio.wait_for(asyncio.to_thread(publication_started.wait), timeout=5)
        assert stream_task.cancel()
        release_publication.set()
        assert await asyncio.wait_for(asyncio.to_thread(cleanup_started.wait), timeout=5)
        put_task = asyncio.create_task(store.put("file-cancel-put-race", b"replacement"))
        await asyncio.sleep(0.1)
        assert not put_started.is_set()
    finally:
        release_publication.set()
        release_cleanup.set()

    with pytest.raises(asyncio.CancelledError):
        await stream_task

    assert put_task is not None
    ref = await put_task
    assert await store.get(ref) == b"replacement"


@pytest.mark.asyncio
async def test_missing_blob_is_file_not_found(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)
    with pytest.raises(FileNotFoundError):
        await store.get("no/file-nope")
    with pytest.raises(FileNotFoundError):
        async for _ in store.get_stream("no/file-nope"):
            pass


@pytest.mark.asyncio
async def test_delete_is_idempotent(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)
    ref = await store.put("file-deleteme0001", b"x")
    await store.delete(ref)
    await store.delete(ref)
    with pytest.raises(FileNotFoundError):
        await store.get(ref)


@pytest.mark.asyncio
async def test_rejects_refs_that_could_leave_the_root(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)
    for bad in ("../escape", "/absolute", "a//b", "a/./b", ""):
        with pytest.raises(ValueError):
            await store.get(bad)


@pytest.mark.asyncio
async def test_backend_client_errors_become_oserror(memory_root: str) -> None:
    store = FsspecFileStore(memory_root)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("some client's own exception class")

    store._fs.cat_file = _boom
    with pytest.raises(OSError, match="fsspec operation failed"):
        await store.get("ab/file-abcdef0123")


@pytest.mark.asyncio
async def test_local_file_protocol_writes_under_the_root(tmp_path: Path) -> None:
    store = FsspecFileStore(f"file://{tmp_path}")
    ref = await store.put("file-abcdef0123", b"on disk")
    assert (tmp_path / "ab" / "file-abcdef0123").read_bytes() == b"on disk"
    assert await store.get(ref) == b"on disk"


def test_build_file_storage_port_fsspec_requires_url() -> None:
    cfg = GatewayConfig(files_backend="fsspec")
    with pytest.raises(ValueError, match="files_url"):
        build_file_storage_port(cfg)


def test_build_file_storage_port_fsspec(tmp_path: Path) -> None:
    cfg = GatewayConfig(
        files_backend="fsspec", files_url=f"file://{tmp_path}", files_storage_options={"auto_mkdir": True}
    )
    assert isinstance(build_file_storage_port(cfg), FsspecFileStore)


def test_missing_fsspec_names_the_extra_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "fsspec.core", None)

    with pytest.raises(ImportError, match=r"uv sync --extra fsspec"):
        FsspecFileStore("memory://otari-test")
