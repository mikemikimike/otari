"""Tests for OpenTelemetry context propagation middleware."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from starlette.responses import StreamingResponse

from gateway.context_propagation import extract_trace_context
from gateway.core.config import GatewayConfig
from gateway.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app(GatewayConfig())


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    ("traceparent", "expected_trace_id"),
    [
        ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", "4bf92f3577b34da6a3ce929d0e0e4736"),
        ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00", "4bf92f3577b34da6a3ce929d0e0e4736"),
        ("00-ffffffffffffffffffffffffffffffff-aaaaaaaaaaaaaaaa-01", "ffffffffffffffffffffffffffffffff"),
    ],
)
def test_http_request_span_inherits_traceparent(
    app: FastAPI,
    client: TestClient,
    traceparent: str,
    expected_trace_id: str,
) -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer(__name__)

    @app.get("/test-trace-span")
    async def generate_trace_span() -> dict[str, str]:
        with tracer.start_as_current_span("request_span") as span:
            span_context = span.get_span_context()
            return {
                "trace_id": format(span_context.trace_id, "032x"),
                "vendor_tracestate": span_context.trace_state.get("vendor") or "",
            }

    response = client.get(
        "/test-trace-span",
        headers={
            "traceparent": traceparent,
            "tracestate": "vendor=value",
        },
    )

    assert response.status_code == 200
    assert response.json()["trace_id"] == expected_trace_id
    assert response.json()["vendor_tracestate"] == "value"


@pytest.mark.parametrize(
    "invalid_traceparent",
    [
        "invalid",
        "00",
        "00-short-parts",
        "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
        "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",
    ],
)
def test_invalid_traceparent_creates_new_root_span(
    app: FastAPI,
    client: TestClient,
    invalid_traceparent: str,
) -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer(__name__)

    @app.get("/test-invalid-traceparent")
    async def generate_trace_span() -> dict[str, str]:
        with tracer.start_as_current_span("request_span") as span:
            return {"trace_id": format(span.get_span_context().trace_id, "032x")}

    response = client.get(
        "/test-invalid-traceparent",
        headers={
            "traceparent": invalid_traceparent,
        },
    )

    assert response.status_code == 200
    trace_id = response.json()["trace_id"]
    assert trace_id != "00000000000000000000000000000000"


def test_missing_traceparent_creates_new_root_span(app: FastAPI, client: TestClient) -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer(__name__)

    @app.get("/test-missing-traceparent")
    async def generate_trace_span() -> dict[str, str]:
        with tracer.start_as_current_span("request_span") as span:
            return {"trace_id": format(span.get_span_context().trace_id, "032x")}

    response = client.get("/test-missing-traceparent")

    assert response.status_code == 200
    assert response.json()["trace_id"] != "00000000000000000000000000000000"


def test_extract_trace_context_valid_format() -> None:
    context = extract_trace_context(
        {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
    )
    assert context is not None


@pytest.mark.parametrize(
    "carrier",
    [
        {},
        {"traceparent": "invalid"},
        {"traceparent": "00-00000000000000000000000000000000-00f067aa0ba902b7-01"},
        {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"},
    ],
)
def test_extract_trace_context_invalid_or_missing(carrier: dict[str, str]) -> None:
    assert extract_trace_context(carrier) is None


def test_streaming_response_span_inherits_traceparent() -> None:
    app = create_app(GatewayConfig())

    @app.get("/test-stream-trace-span")
    async def generate_stream_trace_span() -> StreamingResponse:
        async def stream() -> AsyncIterator[bytes]:
            trace_id = format(trace.get_current_span().get_span_context().trace_id, "032x")
            yield trace_id.encode("utf-8")

        return StreamingResponse(stream(), media_type="text/plain")

    incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    with TestClient(app) as client:
        response = client.get(
            "/test-stream-trace-span",
            headers={"traceparent": f"00-{incoming_trace_id}-00f067aa0ba902b7-01"},
        )

    assert response.status_code == 200
    assert response.text == incoming_trace_id


def test_trace_context_propagation_can_be_disabled() -> None:
    app = create_app(GatewayConfig(accept_incoming_trace_context=False))
    provider = TracerProvider()
    tracer = provider.get_tracer(__name__)

    @app.get("/test-disabled-trace-context")
    async def generate_trace_span() -> dict[str, str]:
        with tracer.start_as_current_span("request_span") as span:
            return {"trace_id": format(span.get_span_context().trace_id, "032x")}

    incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    with TestClient(app) as client:
        response = client.get(
            "/test-disabled-trace-context",
            headers={"traceparent": f"00-{incoming_trace_id}-00f067aa0ba902b7-01"},
        )

    assert response.status_code == 200
    assert response.json()["trace_id"] != incoming_trace_id
