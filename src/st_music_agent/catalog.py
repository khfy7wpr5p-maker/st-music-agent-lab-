from .contracts import ModelProfile, TaskKind


DEFAULT_MODELS: tuple[ModelProfile, ...] = (
    ModelProfile(
        name="GLM-5.1",
        provider="zai",
        task_kinds=frozenset(
            {TaskKind.CODE, TaskKind.PLANNING, TaskKind.RESEARCH, TaskKind.GENERAL}
        ),
        context_window_tokens=200_000,
        supports_tools=True,
        supports_vision=False,
        preference=110,
    ),
    ModelProfile(
        name="Qwen3.8",
        provider="qwen",
        task_kinds=frozenset(
            {TaskKind.CODE, TaskKind.PLANNING, TaskKind.RESEARCH, TaskKind.GENERAL}
        ),
        context_window_tokens=262_144,
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
        preference=100,
    ),
)
