import pytest

from st_music_agent.catalog import DEFAULT_MODELS
from st_music_agent.contracts import AgentTask, TaskKind
from st_music_agent.router import ModelRouter, NoCompatibleModelError


def test_code_task_prefers_primary_agentic_engineering_profile() -> None:
    selected = ModelRouter(DEFAULT_MODELS).select(
        AgentTask(instruction="Inspect the repository and fix the failing tests.", kind=TaskKind.CODE)
    )

    assert selected.name == "GLM-5.1"


def test_score_vision_requires_multimodal_model() -> None:
    selected = ModelRouter(DEFAULT_MODELS).select(
        AgentTask(
            instruction="Inspect this score image and localize notation anomalies.",
            kind=TaskKind.SCORE_VISION,
            needs_vision=True,
        )
    )

    assert selected.name == "Kimi-K2.5"
    assert selected.supports_vision is True


def test_long_context_can_fall_back_to_qwen() -> None:
    selected = ModelRouter(DEFAULT_MODELS).select(
        AgentTask(
            instruction="Analyze a repository snapshot larger than the primary model context.",
            kind=TaskKind.CODE,
            minimum_context_tokens=220_000,
        )
    )

    assert selected.name == "Qwen3.8"


def test_impossible_context_requirement_fails_closed() -> None:
    with pytest.raises(NoCompatibleModelError):
        ModelRouter(DEFAULT_MODELS).select(
            AgentTask(
                instruction="Analyze an oversized synthetic repository snapshot.",
                kind=TaskKind.CODE,
                minimum_context_tokens=1_000_000,
            )
        )
