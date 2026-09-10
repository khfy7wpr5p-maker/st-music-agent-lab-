# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A10 guarded agent foundation:

- **A1 — Core contracts:** task, model capability, provider and action-risk contracts.
- **A2 — Model routing:** capability-driven selection across current open-model profiles.
- **A3 — Autonomy policy:** deterministic gating for reversible, protected, destructive and
  credential-sensitive operations.
- **A4 — Execution adapters:** OpenAI-compatible provider execution, OpenHands Agent Server
  boundary, environment credential resolution, guarded tool execution and a first CLI.
- **A5 — Guarded workspace:** repository-confined file operations plus a narrow command
  classifier.
- **A6 — Disposable sandbox:** command execution requires a hardened sandbox backend; the first
  concrete backend uses ephemeral Docker with no network, dropped capabilities and resource
  limits.
- **A7 — Tool-call and evidence boundary:** only registered ST tools can be dispatched; model-
  facing output is redacted and bounded; tool requests/results can be written to a tamper-evident
  append-only run journal.
- **A8 — Provider tool loop + GitHub read surface:** OpenAI-compatible providers can issue
  bounded function calls into an explicit ST registry. Provider messages are canonicalized,
  reasoning state may be replayed internally without being exposed publicly, and GitHub reads
  are bounded with credential-sensitive paths denied.
- **A9 — Policy-aware GitHub mutations:** agents may create non-protected feature branches and
  write bounded non-sensitive files through deterministic policy. Protected-branch writes,
  deletion and pull-request creation remain human-gated; destructive/PR operations are not
  registered as model-callable tools, and merge is not exposed.
- **A10 — Run budgets + host approval broker:** provider loops now enforce cumulative elapsed,
  model-turn, tool-call and model-facing byte budgets. Human approvals are represented by opaque,
  one-shot host tickets that must exactly match one action/target and cannot be generated through
  the model tool registry.

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

Raw OpenHands terminal/file-editor tools remain disabled. External-agent tool requests must cross
the ST-owned registry, action policy and sandbox boundary rather than receive unrestricted host
access.

## Safety boundary

The model never decides its own privilege level. Action risk is evaluated before execution.

- read-only inspection can run autonomously;
- reversible feature-branch writes can run autonomously;
- direct writes to `main`/`master`, destructive operations and external side effects require
  exact matching human approval;
- secret/credential exposure is denied;
- provider and GitHub credentials are resolved from environment variables only inside adapter
  operations, after policy permits execution;
- HTTP transport accepts only absolute HTTP/HTTPS URLs;
- workspace paths cannot traverse or resolve through symlinks outside the repository root;
- commands cannot execute without a configured sandbox backend;
- Docker sandbox images are digest-pinned by default and networking is disabled;
- Git inspection gets a read-only repository mount; validation commands get a writable mount;
- arbitrary shell/Python commands remain outside the allowlist;
- command and tool output is sanitized before model-facing exposure;
- provider tool calls are bounded and replayed through a canonical message shape;
- complete provider-loop traffic is cumulatively bounded by monotonic time, turn count, tool-call
  count and serialized model-facing byte count;
- GitHub read/write file paths reject common credential/key locations;
- GitHub branch names reject protected-ref aliases and unsafe ref forms;
- only feature-branch creation and file writing are model-callable GitHub mutations;
- deletion and PR creation remain host-side human-gated adapter operations; merge is absent;
- host approval tickets are opaque, exact-action/target, one-shot and never registered as model
  tools;
- journal payloads are sanitized before persistence and every event is linked by SHA-256 hash.

Redaction is defense in depth rather than a complete data-loss-prevention system. Hosts should
still avoid placing unnecessary secrets in agent-visible workspaces or tool arguments.

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
