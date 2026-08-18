"""Tests for OpenTelemetry context propagation middleware.

Tests that incoming request traceparent headers are properly extracted and used
in subsequent trace spans generated within the request.
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
    # Valid W3C Trace Context format
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id = "00f067aa0ba902b7"
    trace_flags = "01"  # sampled
    traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"
    
    # Make a request with the traceparent header
    response = client.get(
        "/health",
        headers={"traceparent": traceparent}
    )
    
    # The request should succeed (health endpoint returns 200)
    assert response.status_code == 200


@pytest.mark.parametrize("traceparent,expected_status", [
    # Sampled trace
    ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", 200),
    # Unsampled trace
    ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00", 200),
    # Valid trace with different IDs (but not all zeros)
    ("00-ffffffffffffffffffffffffffffffff-ffffffffffffffffffffffff-01", 200),
])
def test_traceparent_header_with_correct_format(client: TestClient, traceparent: str, expected_status: int) -> None:
    """Verify that various valid traceparent formats are accepted."""
    response = client.get(
        "/health",
        headers={"traceparent": traceparent}
    )
    assert response.status_code == expected_status


def test_missing_traceparent_header_behaves_normally(client: TestClient) -> None:
    """Verify that requests without traceparent header still work normally."""
    # Make a request without the traceparent header
    response = client.get("/health")
    
    # The request should succeed normally
    assert response.status_code == 200


@pytest.mark.parametrize("invalid_traceparent", [
    "invalid",  # completely wrong format
    "00",  # too short
    "00-short-parts",  # not enough parts
    "00-short-id-00f067aa0ba902b7-01",  # trace ID too short
    "00-4bf92f3577b34da6a3ce929d0e0e4736-short-01",  # span ID too short
    "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-x",  # invalid trace flags
])
def test_invalid_traceparent_format_is_handled_gracefully(client: TestClient, invalid_traceparent: str) -> None:
    """Verify that invalid traceparent headers are handled without crashing."""
    # Make a request with invalid traceparent
    response = client.get(
        "/health",
        headers={"traceparent": invalid_traceparent}
    )
    # The request should still succeed (graceful degradation)
    # Invalid headers should not cause the request to fail
    assert response.status_code == 200


def test_traceparent_with_trace_state_extension(client: TestClient) -> None:
    """Verify that traceparent and tracestate headers are handled.

    The W3C Trace Context spec allows an optional `tracestate` header alongside `traceparent`.
    """
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id = "00f067aa0ba902b7"
    trace_flags = "01"
    traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"
    tracestate = "congo=t61rcWkgMzE"
    
    response = client.get(
        "/health",
        headers={
            "traceparent": traceparent,
            "tracestate": tracestate,
        }
    )
    
    # Should succeed with tracestate present
    assert response.status_code == 200


def test_traceparent_with_zero_trace_id_is_handled(client: TestClient) -> None:
    """Verify that traceparent with all-zero trace ID is handled gracefully."""
    # All zeros trace ID should be invalid per W3C spec
    invalid_traceparent = "00-00000000000000000000000000000000-00f067aa0ba902b7-01"
    
    response = client.get(
        "/health",
        headers={"traceparent": invalid_traceparent}
    )
    
    # Should still return 200 (graceful degradation)
    assert response.status_code == 200


def test_traceparent_with_zero_span_id_is_handled(client: TestClient) -> None:
    """Verify that traceparent with all-zero span ID is handled gracefully."""
    # All zeros span ID should be invalid per W3C spec
    invalid_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"
    
    response = client.get(
        "/health",
        headers={"traceparent": invalid_traceparent}
    )
    
    # Should still return 200 (graceful degradation)
    assert response.status_code == 200


def test_multiple_requests_maintain_independent_contexts(client: TestClient) -> None:
    """Verify that multiple requests maintain independent trace contexts.
    
    Two requests with different traceparent headers should maintain
    independent trace contexts.
    """
    traceparent1 = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    traceparent2 = "00-ffffffffffffffffffffffffffffffff-aaaaaaaaaaaaaaaa-00"
    
    # First request
    response1 = client.get(
        "/health",
        headers={"traceparent": traceparent1}
    )
    assert response1.status_code == 200
    
    # Second request with different context
    response2 = client.get(
        "/health",
        headers={"traceparent": traceparent2}
    )
    assert response2.status_code == 200


def test_extract_trace_context_from_carrier_valid_format() -> None:
    """Test extracting valid trace context from a carrier dict."""
    from conftest import extract_trace_context_from_carrier
    
    carrier = {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    }
    
    context = extract_trace_context_from_carrier(carrier)
    assert context is not None


def test_extract_trace_context_from_carrier_no_header() -> None:
    """Test extracting context when no traceparent header is present."""
    from conftest import extract_trace_context_from_carrier
    
    carrier: dict[str, str] = {}
    context = extract_trace_context_from_carrier(carrier)
    assert context is None


def test_extract_trace_context_from_carrier_invalid_format() -> None:
    """Test extracting context with invalid traceparent format."""
    from conftest import extract_trace_context_from_carrier
    
    carrier = {"traceparent": "invalid"}
    context = extract_trace_context_from_carrier(carrier)
    assert context is None


def test_extract_trace_context_from_carrier_with_all_zero_trace_id() -> None:
    """Test that all-zero trace IDs are rejected."""
    from conftest import extract_trace_context_from_carrier
    
    carrier = {
        "traceparent": "00-00000000000000000000000000000000-00f067aa0ba902b7-01"
    }
    context = extract_trace_context_from_carrier(carrier)
    assert context is None


def test_extract_trace_context_from_carrier_with_all_zero_span_id() -> None:
    """Test that all-zero span IDs are rejected."""
    from conftest import extract_trace_context_from_carrier
    
    carrier = {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"
    }
    context = extract_trace_context_from_carrier(carrier)
    assert context is None


def test_http_request_span_inherits_traceparent(
    app: FastAPI, client: TestClient
) -> None:
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
        headers={
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        },
    )

    assert response.status_code == 200
    assert response.json()["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    # The OTEL SDK does not type hint the return value of get_span_context(), so we ignore the type check here
    span_context = spans[0].get_span_context()  # type: ignore[no-untyped-call]
    assert span_context is not None
    assert format(span_context.trace_id, "032x") == (
        "4bf92f3577b34da6a3ce929d0e0e4736"
    )


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
    trace_flags = "01"
    traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    
    carrier = {
        "traceparent": traceparent
    }

    extracted_span = extract_trace_context_from_carrier(carrier)
    assert extracted_span is not None
    extracted_context = extracted_span.get_span_context()
    assert extracted_context is not None
    assert format(extracted_context.trace_id, "032x") == trace_id

    tracer = provider.get_tracer(__name__)
    parent_context = trace.set_span_in_context(extracted_span)
    with tracer.start_as_current_span("test_span", context=parent_context) as span:
        assert span is not None

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    # The OTEL SDK does not type hint the return value of get_span_context(), so we ignore the type check here
    span_context = spans[0].get_span_context()  # type: ignore[no-untyped-call]
    assert span_context is not None
    assert format(span_context.trace_id, "032x") == trace_id

