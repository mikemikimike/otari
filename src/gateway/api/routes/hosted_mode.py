"""The data-plane refusals a hosted control plane answers with.

Hosted mode is the multi-tenant control plane: it owns the management API for
several organizations and is not where any of their inference belongs. Customer
inference belongs on the data-plane gateway, which resolves credentials through
this control plane and reports usage back, and that usage report is what debits
an organization's wallet. Inference served here reports to nobody, so it runs
free (otari#822).

``register_routers`` therefore does not mount the OpenAI-compatible data plane in
hosted mode at all, and this router takes its place: the endpoints cannot be
reached because the code that would run them is not registered, not because a
guard on the way in said no. This exists so a client pointed at the wrong host
is told which host is the right one instead of getting a bare 404 that reads
like a version mismatch.

The mirror of ``hybrid_mode`` on the other axis. That one stubs the *management*
prefixes a hybrid gateway does not own; this one stubs the *data-plane* paths a
control plane does not serve. No deployment mounts both, because no deployment
is missing both halves.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from gateway.api.deps import get_config
from gateway.core.config import GatewayConfig

router = APIRouter(tags=["hosted-mode"])

_DISABLED_DETAIL = (
    "This endpoint is not available on a hosted control plane. "
    "Send inference requests to the data-plane gateway"
)

# Every method a client might reach one of these paths with, not just the one the
# real route takes: the point is that the path is not served here, and a client
# that guessed the verb wrong should read the explanation rather than a 405 that
# suggests the path exists. ``HEAD`` is spelled out because FastAPI does not
# derive it from ``GET`` when the methods are given explicitly, and probing
# tooling reaches for it.
_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

ConfigDep = Annotated[GatewayConfig, Depends(get_config)]


def _raise_disabled(config: GatewayConfig) -> None:
    """Refuse with the data-plane address when the deployment knows it.

    ``data_plane_url`` is optional, and a control plane running without it is
    the case where this message earns its keep: the caller is told the request
    is on the wrong host either way, and gets the right host whenever the
    operator has configured one. Naming this host would be actively wrong, so
    the sentence ends there when there is nothing to name.
    """
    address = config.data_plane_url
    detail = f"{_DISABLED_DETAIL} at {address}." if address else f"{_DISABLED_DETAIL}."
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.api_route("/v1/chat/{path:path}", methods=_METHODS)
@router.api_route("/v1/chat", methods=_METHODS)
async def chat_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


# ``/v1/messages`` and its ``count_tokens`` sibling. The token count bills
# nothing, and it is stubbed anyway: it is half of the Anthropic-shaped client
# contract, and a client that can count tokens against a host that will not
# complete them has been pointed somewhere confusing.
@router.api_route("/v1/messages/{path:path}", methods=_METHODS)
@router.api_route("/v1/messages", methods=_METHODS)
async def messages_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


@router.api_route("/v1/responses/{path:path}", methods=_METHODS)
@router.api_route("/v1/responses", methods=_METHODS)
async def responses_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


@router.api_route("/v1/embeddings", methods=_METHODS)
async def embeddings_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


@router.api_route("/v1/images/{path:path}", methods=_METHODS)
@router.api_route("/v1/images", methods=_METHODS)
async def images_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


@router.api_route("/v1/audio/{path:path}", methods=_METHODS)
@router.api_route("/v1/audio", methods=_METHODS)
async def audio_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


@router.api_route("/v1/rerank", methods=_METHODS)
async def rerank_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


@router.api_route("/v1/moderations", methods=_METHODS)
async def moderations_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


# ``/v1/search`` and ``/v1/search/{tool}``, the built-in web search. Not
# ``/v1/search-tools``, which is the management surface that configures which
# providers exist and stays mounted: a different prefix, and no path here
# matches it.
@router.api_route("/v1/search/{path:path}", methods=_METHODS)
@router.api_route("/v1/search", methods=_METHODS)
async def search_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


@router.api_route("/v1/batches/{path:path}", methods=_METHODS)
@router.api_route("/v1/batches", methods=_METHODS)
async def batches_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)


# Files are the one member of this set that runs no inference and reserves no
# budget. They are stubbed with it because they are storage *for* inference:
# batch input and output, and file inputs to a completion. With every consumer
# of an uploaded file gone from this deployment, an upload here is a payload
# with nothing to read it, on the host whose whole point is not holding
# customer request data.
@router.api_route("/v1/files/{path:path}", methods=_METHODS)
@router.api_route("/v1/files", methods=_METHODS)
async def files_disabled(config: ConfigDep) -> None:
    _raise_disabled(config)
