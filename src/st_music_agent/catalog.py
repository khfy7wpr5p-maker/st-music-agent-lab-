from .contracts import ModelProfile, TaskKind


DEFAULT_MODELS: tuple[ModelProfile, ...] = (
    ModelProfile(
        name="Qwen3-Coder-Next",
        provider="qwen",
        task_kinds=frozenset({TaskKind.CODE, TaskKind.RESEARCH}),
        context_window_tokens=256_000,
        supports_tools=True,
        supports_vision=False,
        preference=100,
    ),
    ModelProfile(
        name="GLM-4.7",
        provider="zai",
        task_kinds=frozenset(
            {TaskKind.CODE, TaskKind.PLANNING, TaskKind.RESEARCH, TaskKind.GENERAL}
        ),
        context_window_tokens=200_000,
        supports_tools=True,
        supports_vision=False,
        preference=105,
    ),
    ModelProfile(
        name="Kimi-K2.5",
        provider="moonshot",
        task_kinds=frozenset(
            {
                TaskKind.CODE,
                TaskKind.PLANNING,
                TaskKind.SCORE_VISION,
                TaskKind.RESEARCH,
                TaskKind.GENERAL,
            }
        ),
        context_window_tokens=256_000,
        supports_tools=True,
        supports_vision=True,
        preference=95,
    ),
)
