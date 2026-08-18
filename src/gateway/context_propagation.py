"""OpenTelemetry context propagation middleware for W3C Trace Context.

This middleware extracts the traceparent (and tracestate) headers from incoming
requests using the standard `TraceContextTextMapPropagator`, and sets up the
OpenTelemetry context so that subsequent spans created in the request are
properly linked to the parent trace, with any vendor `tracestate` preserved.

If the header is not present, the middleware allows normal OpenTelemetry behavior
(new traces are created as needed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from gateway.log_config import logger

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class TraceContextPropagationMiddleware:
    """Pure ASGI middleware that extracts W3C Trace Context from incoming requests.

    When a request contains a traceparent header, this middleware extracts the
    trace context and sets it in the OpenTelemetry context, so subsequent spans
    are linked to the parent trace. Implemented as raw ASGI (like
    `MetricsMiddleware`) rather than `BaseHTTPMiddleware`, whose `call_next`
    returns before a streaming response body finishes sending, which would
    detach the context before streaming spans are done.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process incoming request and extract trace context.

        Extracts the traceparent header if present and sets the OpenTelemetry
        context before passing the request to the next middleware/handler.
        Uses pure ASGI so context detachment happens after streaming responses
        are fully sent.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extracted_context = _extract_context_from_carrier(Headers(scope=scope))

        if extracted_context is None:
            await self.app(scope, receive, send)
            return

        token = otel_context.attach(extracted_context)
        try:
            # Awaiting here spans the full response, including a streamed body,
            # so the context stays attached until streaming completes.
            await self.app(scope, receive, send)
        finally:
            otel_context.detach(token)


def _extract_context_from_carrier(carrier: Any) -> Context | None:
    """Extract W3C Trace Context (traceparent + tracestate) from a carrier.

    Delegates to the standard `TraceContextTextMapPropagator` instead of
    hand-parsing the headers, so vendor `tracestate` entries are preserved
    on the resulting span context.

    Args:
        carrier: A mapping of request headers (e.g. `request.headers`).

    Returns:
        An OpenTelemetry Context with the extracted trace context, or None if
        extraction failed or no valid traceparent is present.
    """
    try:
        context = TraceContextTextMapPropagator().extract(carrier=carrier)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to extract trace context: %s", exc)
        return None

    if trace.get_current_span(context).get_span_context().trace_id == trace.INVALID_TRACE_ID:
        return None

    return context
