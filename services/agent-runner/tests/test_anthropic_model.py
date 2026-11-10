"""The real model client: it must build as in the container, and fail fast when the API is unreachable."""

import pytest

from agent_runner.integrations.anthropic_model import AnthropicModel
from agent_runner.interfaces import ModelUnavailable


def test_builds_like_in_the_container(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    model = AnthropicModel()
    assert model._client.timeout.connect == 15.0 and model._client.max_retries == 2


async def test_unreachable_api_is_a_clear_error_not_a_hang(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    model = AnthropicModel()
    model._client = model._client.with_options(base_url="http://127.0.0.1:9", max_retries=0)  # nothing listens
    with pytest.raises(ModelUnavailable, match="cannot reach the model API"):
        await model.next("system", [{"role": "user", "content": "hi"}], [])
