
import pytest
from fastapi import status
from gateway.api.routes._pipeline import classify_provider_error
from any_llm.exceptions import AnyLLMError

def test_classify_image_provider_error_returns_400():
    class ImageError(AnyLLMError):
        pass

    exc = ImageError("image content not supported")
    mapping = classify_provider_error(exc)
    assert mapping is not None
    assert mapping.status_code == status.HTTP_400_BAD_REQUEST
