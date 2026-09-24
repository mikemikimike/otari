"""Shared failure contract for every streamed file-storage adapter."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Generator
from dataclasses import dataclass
from pathlib import Path

import pytest

from gateway.adapters.file_storage_adapter import FsspecFileStore, LocalDirFileStore, S3FileStore
from gateway.exceptions.files_exceptions import UploadTooLargeError
from gateway.ports.file_storage_port import FileStoragePort
from gateway.services.files._service import _capped


@dataclass(frozen=True)
class StoreCase:
    store: FileStoragePort
    assert_empty: Callable[[], Awaitable[None]]


@pytest.fixture(params=("local", "fsspec", "s3"))
def store_case(request: pytest.FixtureRequest, tmp_path: Path) -> Generator[StoreCase, None, None]:
    store: FileStoragePort
    if request.param == "local":
        store = LocalDirFileStore(str(tmp_path))

        async def assert_empty() -> None:
            assert not [path for path in tmp_path.rglob("*") if path.is_file()]

        yield StoreCase(store, assert_empty)
        return

    if request.param == "fsspec":
        fsspec = pytest.importorskip("fsspec")
        filesystem = fsspec.filesystem("memory")
        root = f"otari-stream-contract-{uuid.uuid4().hex}"
        store = FsspecFileStore(f"memory://{root}")

        async def assert_empty() -> None:
            assert filesystem.find(root) == []

        try:
            yield StoreCase(store, assert_empty)
        finally:
            filesystem.rm(root, recursive=True)
        return

    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    bucket = f"otari-stream-contract-{uuid.uuid4().hex}"
    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=bucket)
        store = S3FileStore(bucket=bucket, endpoint_url=None, region="us-east-1")

        async def assert_empty() -> None:
            listing = await asyncio.to_thread(client.list_objects_v2, Bucket=bucket)
            assert listing.get("KeyCount", 0) == 0
            uploads = await asyncio.to_thread(client.list_multipart_uploads, Bucket=bucket)
            assert uploads.get("Uploads", []) == []

        yield StoreCase(store, assert_empty)


@pytest.mark.asyncio
async def test_failed_source_leaves_no_object(store_case: StoreCase) -> None:
    async def failing_chunks() -> AsyncIterator[bytes]:
        yield b"partial bytes"
        raise RuntimeError("source failed")

    with pytest.raises(RuntimeError, match="source failed"):
        await store_case.store.put_stream(f"file-{uuid.uuid4().hex}", failing_chunks())

    await store_case.assert_empty()


@pytest.mark.asyncio
async def test_size_refusal_leaves_no_object(store_case: StoreCase) -> None:
    async def oversized_chunks() -> AsyncIterator[bytes]:
        yield b"1234"
        yield b"5678"

    with pytest.raises(UploadTooLargeError):
        await store_case.store.put_stream(f"file-{uuid.uuid4().hex}", _capped(oversized_chunks(), 5))

    await store_case.assert_empty()


@pytest.mark.asyncio
async def test_cancellation_mid_stream_leaves_no_object(store_case: StoreCase) -> None:
    started = asyncio.Event()

    async def blocked_chunks() -> AsyncIterator[bytes]:
        yield b"partial bytes"
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(store_case.store.put_stream(f"file-{uuid.uuid4().hex}", blocked_chunks()))
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await store_case.assert_empty()
