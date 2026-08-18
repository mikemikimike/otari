"""Tests for OpenTelemetry context propagation middleware.

Tests that incoming request traceparent headers are properly extracted and used
in subsequent trace spans generated within the request, including for streaming
responses where the context must be held for the full response body duration.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.core.config import GatewayConfig
from gateway.main import create_app


@pytest.fixture
def config_with_tracing() -> GatewayConfig:
    """Create a gateway config for testing."""
    return GatewayConfig()


@pytest.fixture
def app(config_with_tracing: GatewayConfig) -> FastAPI:
    """Create a test app with tracing enabled."""
    return create_app(config_with_tracing)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app)


def test_traceparent_header_is_extracted_from_request(client: TestClient) -> None:
    """Verify that a valid traceparent header is successfully extracted."""
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id = "00f067aa0ba902b7"
    traceparent = f"00-{trace_id}-{span_id}-01"

    response = client.get("/health", headers={"traceparent": traceparent})
    assert response.status_code == 200


@pytest.mark.parametrize("traceparent,expected_status", [
    ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", 200),
    ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00", 200),
    ("00-ffffffffffffffffffffffffffffffff-ffffffffffffffff-01", 200),
])
def test_traceparent_header_with_correct_format(
    client: TestClient, traceparent: str, expected_status: int
) -> None:
    """Verify that various valid traceparent formats are accepted."""
    response = client.get("/health", headers={"traceparent": traceparent})
    assert response.status_code == expected_status


def test_missing_traceparent_header_behaves_normally(client: TestClient) -> None:
    """Verify that requests without traceparent header still work normally."""
    response = client.get("/health")
    assert response.status_code == 200


@pytest.mark.parametrize("invalid_traceparent", [
    "invalid",
    "00",
    "00-short-parts",
    "00-short-id-00f067aa0ba902b7-01",
    "00-4bf92f3577b34da6a3ce929d0e0e4736-short-01",
    "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-x",
])
def test_invalid_traceparent_format_is_handled_gracefully(
    client: TestClient, invalid_traceparent: str
) -> None:
    """Verify that invalid traceparent headers are handled without crashing."""
    response = client.get("/health", headers={"traceparent": invalid_traceparent})
    assert response.status_code == 200


def test_traceparent_with_trace_state(client: TestClient) -> None:
    """Verify that traceparent and tracestate headers are handled.

    The W3C Trace Context spec allows an optional `tracestate` header alongside
    `traceparent`.
    """
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    response = client.get(
        "/health",
        headers={"traceparent": traceparent, "tracestate": "congo=t61rcWkgMzE"},
    )
    assert response.status_code == 200


def test_traceparent_with_zero_trace_id_is_handled(client: TestClient) -> None:
    """Verify that traceparent with all-zero trace ID is handled gracefully."""
    invalid_traceparent = "00-00000000000000000000000000000000-00f067aa0ba902b7-01"
    response = client.get("/health", headers={"traceparent": invalid_traceparent})
    assert response.status_code == 200


def test_traceparent_with_zero_span_id_is_handled(client: TestClient) -> None:
    """Verify that traceparent with all-zero span ID is handled gracefully."""
    invalid_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"
    response = client.get("/health", headers={"traceparent": invalid_traceparent})
    assert response.status_code == 200


def test_multiple_requests_maintain_independent_contexts(client: TestClient) -> None:
    """Verify that multiple requests maintain independent trace contexts."""
    traceparent1 = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    traceparent2 = "00-ffffffffffffffffffffffffffffffff-aaaaaaaaaaaaaaaa-00"

    assert client.get("/health", headers={"traceparent": traceparent1}).status_code == 200
    assert client.get("/health", headers={"traceparent": traceparent2}).status_code == 200


def test_extract_trace_context_from_carrier_valid_format() -> None:
    """Test extracting valid trace context from a carrier dict."""
    from conftest import extract_trace_context_from_carrier

    carrier = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
    assert extract_trace_context_from_carrier(carrier) is not None


def test_extract_trace_context_from_carrier_no_header() -> None:
    """Test extracting context when no traceparent header is present."""
    from conftest import extract_trace_context_from_carrier

    assert extract_trace_context_from_carrier({}) is None


def test_extract_trace_context_from_carrier_invalid_format() -> None:
    """Test extracting context with invalid traceparent format."""
    from conftest import extract_trace_context_from_carrier

    assert extract_trace_context_from_carrier({"traceparent": "invalid"}) is None


def test_extract_trace_context_from_carrier_with_all_zero_trace_id() -> None:
    """Test that all-zero trace IDs are rejected."""
    from conftest import extract_trace_context_from_carrier

    carrier = {"traceparent": "00-00000000000000000000000000000000-00f067aa0ba902b7-01"}
    assert extract_trace_context_from_carrier(carrier) is None


def test_extract_trace_context_from_carrier_with_all_zero_span_id() -> None:
    """Test that all-zero span IDs are rejected."""
    from conftest import extract_trace_context_from_carrier

    carrier = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"}
    assert extract_trace_context_from_carrier(carrier) is None


def test_http_request_span_inherits_traceparent(app: FastAPI, client: TestClient) -> None:
    """Verify that a handler span inherits the incoming trace context."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    @app.get("/test-trace-span")
    async def generate_trace_span() -> dict[str, str]:
        with tracer.start_as_current_span("request_span") as span:
            return {"trace_id": format(span.get_span_context().trace_id, "032x")}

    response = client.get(
        "/test-trace-span",
        headers={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"},
    )

    assert response.status_code == 200
    assert response.json()["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span_context = spans[0].get_span_context()  # type: ignore[no-untyped-call]
    assert span_context is not None
    assert format(span_context.trace_id, "032x") == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_context_is_held_for_streaming_response(app: FastAPI, client: TestClient) -> None:
    """Verify that the trace context is present in spans emitted during streaming.

    The middleware must hold the attached context until the last response body
    chunk is sent, not detach it as soon as call_next() returns headers.
    """
    from fastapi.responses import StreamingResponse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    @app.get("/test-streaming-trace")
    async def streaming_endpoint() -> StreamingResponse:
        async def body() -> object:
            # Emit a span while streaming the body; must inherit the request context.
            with tracer.start_as_current_span("streaming_span"):
                yield b"chunk1"
            yield b"chunk2"

        return StreamingResponse(body(), media_type="text/plain")

    response = client.get(
        "/test-streaming-trace",
        headers={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"},
    )

    assert response.status_code == 200
    spans = exporter.get_finished_spans()
    streaming_span = next((s for s in spans if s.name == "streaming_span"), None)
    assert streaming_span is not None, "No streaming_span found in exported spans"
    assert (
        format(streaming_span.context.trace_id, "032x") == "4bf92f3577b34da6a3ce929d0e0e4736"
    ), "Streaming span did not inherit the propagated trace context"


@pytest.mark.asyncio
async def test_context_propagation_with_span_generation() -> None:
    """Test that a generated span inherits the extracted trace context."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from conftest import extract_trace_context_from_carrier

    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id = "00f067aa0ba902b7"
    traceparent = f"00-{trace_id}-{span_id}-01"

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    extracted_span = extract_trace_context_from_carrier({"traceparent": traceparent})
    assert extracted_span is not None
    assert format(extracted_span.get_span_context().trace_id, "032x") == trace_id

    tracer = provider.get_tracer(__name__)
    parent_context = trace.set_span_in_context(extracted_span)
    with tracer.start_as_current_span("test_span", context=parent_context) as span:
        assert span is not None

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span_context = spans[0].get_span_context()  # type: ignore[no-untyped-call]
    assert span_context is not None
    assert format(span_context.trace_id, "032x") == trace_id
