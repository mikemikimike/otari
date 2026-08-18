"""OpenTelemetry context propagation middleware for W3C Trace Context.

This middleware extracts the traceparent (and tracestate) headers from incoming
requests using the standard `TraceContextTextMapPropagator`, and sets up the
OpenTelemetry context so that subsequent spans created in the request are
properly linked to the parent trace, with any vendor `tracestate` preserved.

If the header is not present, the middleware allows normal OpenTelemetry behavior
(new traces are created as needed).

For streaming responses the context is held open until the last response body
chunk has been sent, then detached. This mirrors the pattern used by
`MetricsMiddleware`: raw ASGI middleware blocks inside
`await self.app(scope, receive, send)` until the response is fully consumed,
unlike `BaseHTTPMiddleware` whose `call_next()` returns as soon as headers are
ready and therefore detaches too early for streaming endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class TraceContextPropagationMiddleware:
    """ASGI middleware that extracts W3C Trace Context from incoming requests.

    When a request contains a traceparent header, this middleware extracts the
    trace context and attaches it to the OpenTelemetry context for the lifetime
    of the request, including the full streaming response body. The context is
    detached only after the last response body chunk has been sent.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extracted_context = _extract_context_from_scope(scope)

        if extracted_context is None:
            await self.app(scope, receive, send)
            return

        token = otel_context.attach(extracted_context)
        try:
            await self.app(scope, receive, send)
        finally:
            otel_context.detach(token)


def _extract_context_from_scope(scope: Scope) -> Context | None:
    """Extract W3C Trace Context from an ASGI scope's headers."""
    headers = dict(scope.get("headers") or [])
    carrier = {k.decode(): v.decode() for k, v in headers.items()}
    return _extract_context_from_carrier(carrier)


def _extract_context_from_carrier(carrier: Any) -> Context | None:
    """Extract W3C Trace Context (traceparent + tracestate) from a carrier.

    Delegates to the standard `TraceContextTextMapPropagator` instead of
    hand-parsing the headers, so vendor `tracestate` entries are preserved
    on the resulting span context.

    Args:
        carrier: A mapping of request headers (e.g. `request.headers`).

    Returns:
        An OpenTelemetry Context with the extracted trace context, or None if
        no valid traceparent is present.
    """
    context = TraceContextTextMapPropagator().extract(carrier=carrier)

    if trace.get_current_span(context).get_span_context().trace_id == trace.INVALID_TRACE_ID:
        return None

    return context
