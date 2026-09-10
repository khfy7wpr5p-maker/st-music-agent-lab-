# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence agents across ST projects.

## Current stage

A1-A3 foundation is implemented on the development branch:

- **A1 — Core contracts:** task, model capability, provider and action-risk contracts.
- **A2 — Model routing:** capability-driven selection across current open-model profiles.
- **A3 — Autonomy policy:** routine reversible work can proceed autonomously; protected, destructive, external or credential-sensitive actions are gated.

## Initial model strategy

The architecture deliberately does not depend on one model.

- **GLM-5.1** — primary long-horizon agentic engineering profile.
- **Qwen3.8** — open secondary model and longer-context fallback.
- **Kimi-K2.5** — multimodal profile for future score-image and notation inspection.

These are catalog entries rather than hard dependencies and can be replaced as models improve.

## Framework strategy

OpenHands Software Agent SDK is the preferred first execution-backend candidate for A4+ because it is modular and model-agnostic. OpenManus, mini-SWE-agent and Qwen-Agent/Qwen Code remain architectural references; ST-specific behavior stays in this repository.

## Safety boundary

The model never decides its own privilege level. Action risk is evaluated by deterministic policy code before execution. The initial policy:

- automatically permits read-only inspection;
- automatically permits reversible writes on non-protected feature branches;
- requires human approval for direct writes to `main`/`master`, destructive operations and external side effects;
- denies requests that require secrets or credentials to be exposed to the agent core.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

See [`docs/architecture.md`](docs/architecture.md) for the architecture map and [`docs/model-selection.md`](docs/model-selection.md) for the research record and model/framework decision.
