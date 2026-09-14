from __future__ import annotations

import pytest

from st_music_agent.persistent_provider import PersistentProviderSettings


def test_persistent_provider_uses_generic_qwen_environment_contract() -> None:
    settings = PersistentProviderSettings.from_env(
        {
            "ST_QWEN_BASE_URL": "https://qwen.example.test/v1/",
            "ST_QWEN_MODEL": "qwen3:4b",
        }
    )

    assert settings.base_url == "https://qwen.example.test/v1"
    assert settings.model == "qwen3:4b"
    assert settings.api_key_env == "ST_QWEN_API_KEY"
    assert settings.health_url() == "https://qwen.example.test/health"
    assert settings.cli_args() == (
        "--provider-base-url",
        "https://qwen.example.test/v1",
        "--provider-model",
        "qwen3:4b",
        "--provider-api-key-env",
        "ST_QWEN_API_KEY",
    )


def test_persistent_provider_can_use_custom_secret_name() -> None:
    settings = PersistentProviderSettings.from_env(
        {
            "ST_QWEN_BASE_URL": "http://10.0.0.5:8000/v1",
            "ST_QWEN_API_KEY_ENV": "PRIVATE_QWEN_TOKEN",
        }
    )

    assert settings.api_key_env == "PRIVATE_QWEN_TOKEN"
    assert settings.health_url() == "http://10.0.0.5:8000/health"


@pytest.mark.parametrize("value", ["", "qwen.internal/v1", "file:///tmp/qwen"])
def test_persistent_provider_rejects_invalid_base_url(value: str) -> None:
    with pytest.raises(ValueError):
        PersistentProviderSettings.from_env({"ST_QWEN_BASE_URL": value})
