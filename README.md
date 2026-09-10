# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A4 execution foundation:

- **A1 — Core contracts:** task, model capability, provider and action-risk contracts.
- **A2 — Model routing:** capability-driven selection across current open-model profiles.
- **A3 — Autonomy policy:** deterministic gating for reversible, protected, destructive and
  credential-sensitive operations.
- **A4 — Execution adapters:** OpenAI-compatible provider execution, OpenHands Agent Server
  boundary, environment credential resolution, guarded tool execution and a first CLI.

## Initial model strategy

The architecture deliberately does not depend on one model.

- **GLM-5.1** — primary long-horizon agentic engineering profile.
- **Qwen3.8** — open secondary model and longer-context fallback.
- **Kimi-K2.5** — multimodal profile for score-image and notation inspection.

These are catalog entries rather than hard dependencies and can be replaced as models improve.

## Framework strategy

OpenHands Software Agent SDK / Agent Server is the preferred external software-agent execution
substrate. OpenManus, mini-SWE-agent and Qwen-Agent/Qwen Code remain architectural references;
ST-specific routing, policy and music behavior stay in this repository.

A4 intentionally does **not** enable OpenHands terminal or file-editor tools yet. Those tools can
change a repository and therefore belong behind the A5 sandbox and action-policy bridge instead
of bypassing ST's deterministic safety boundary.

## Safety boundary

The model never decides its own privilege level. Action risk is evaluated before execution.

- read-only inspection can run autonomously;
- reversible feature-branch writes can run autonomously;
- direct writes to `main`/`master`, destructive operations and external side effects require
  matching human approval;
- secret/credential exposure is denied;
- provider credentials are resolved from environment variables only at adapter boundaries;
- the dependency-free HTTP transport accepts only absolute HTTP/HTTPS URLs.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

## First direct model run

The CLI works with an OpenAI-compatible provider or self-hosted endpoint. The secret itself is
not passed as a command-line value; only the environment-variable name is configured.

```bash
export ST_AGENT_API_KEY='...'

st-music-agent \
  --profile GLM-5.1 \
  --kind code \
  --base-url https://your-provider.example/v1 \
  --model your-provider-model-id \
  --api-key-env ST_AGENT_API_KEY \
  'Inspect this repository and propose the smallest safe fix.'
```

See [`docs/architecture.md`](docs/architecture.md) for the architecture map and
[`docs/model-selection.md`](docs/model-selection.md) for the research record.
