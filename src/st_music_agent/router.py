from __future__ import annotations

from collections.abc import Iterable

from .contracts import AgentTask, ModelProfile


class NoCompatibleModelError(LookupError):
    pass


class ModelRouter:
    """Select a model by declared capabilities instead of provider-specific conditionals."""

    def __init__(self, models: Iterable[ModelProfile]) -> None:
        self._models = tuple(models)
        if not self._models:
            raise ValueError("at least one model profile is required")

    def select(self, task: AgentTask) -> ModelProfile:
        candidates = [model for model in self._models if model.supports(task)]
        if not candidates:
            raise NoCompatibleModelError(
                f"no model satisfies kind={task.kind.value!r}, "
                f"vision={task.needs_vision}, tools={task.needs_tools}, "
                f"minimum_context_tokens={task.minimum_context_tokens}"
            )

        return max(
            candidates,
            key=lambda model: (
                model.preference,
                model.context_window_tokens,
                model.name,
            ),
        )
