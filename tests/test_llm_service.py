import pytest

from loom.models.ticket import LLMClassification
from loom.services.llm_service import LLMService, TransientLLMError


def test_build_strict_json_schema_forces_additional_properties_false():
    schema = LLMService.build_strict_json_schema(LLMClassification)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())
    assert "default" not in schema


async def test_with_backoff_retries_then_succeeds():
    attempts = {"count": 0}

    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TransientLLMError("temporary")
        return "ok"

    result = await LLMService.with_backoff(flaky, max_attempts=5, base_delay=0)
    assert result == "ok"
    assert attempts["count"] == 3


async def test_with_backoff_gives_up_after_max_attempts():
    async def always_fails():
        raise TransientLLMError("still broken")

    with pytest.raises(TransientLLMError):
        await LLMService.with_backoff(always_fails, max_attempts=2, base_delay=0)


async def test_with_backoff_never_retries_auth_errors():
    from loom.services.llm_service import AuthLLMError

    attempts = {"count": 0}

    async def bad_key():
        attempts["count"] += 1
        raise AuthLLMError("invalid key")

    with pytest.raises(AuthLLMError):
        await LLMService.with_backoff(bad_key, max_attempts=5, base_delay=0)
    assert attempts["count"] == 1
