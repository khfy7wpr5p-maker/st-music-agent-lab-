# ST Music Agent Lab — Architecture Map

Status: A1-A4 execution foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer.
It coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, and capability-driven.

Initial target domains:

- repository inspection, coding, tests, CI and documentation;
- music-score and notation analysis;
- research and architecture planning;
- later adapters for ST Score Restore, Score Editor, MusicXML/TAB and score-following projects.

## Design decision

Do not fork a large agent framework into this repository. Keep the ST core small and stable,
then attach model providers, OpenHands, GitHub and music-domain capabilities through adapters.

## A1 — Core contracts

`contracts.py` defines stable boundaries for task intent, model capability, provider clients and
action risk. Provider SDK details are not allowed to leak into these contracts.

## A2 — Capability-driven model routing

`catalog.py` and `router.py` select models from declared task requirements.

Initial routing intent:

- GLM-5.1: primary long-horizon agentic engineering, planning, research and code;
- Qwen3.8: open secondary model and longer-context fallback;
- Kimi-K2.5: multimodal/score-image specialist and fallback agent model.

The model names are configuration data rather than architectural dependencies.

## A3 — Autonomous execution policy

`policy.py` separates routine autonomous work from actions requiring human approval.
`tools.py` applies that policy immediately before a tool operation executes.

Default behavior:

- read-only inspection: autonomous;
- reversible writes on a feature branch: autonomous;
- direct protected-branch writes: human approval;
- destructive or external side-effect actions: human approval;
- secret/credential exposure requests: denied;
- a human approval must match the exact action name and target;
- a denied secret action cannot be overridden by an approval.

The policy is deterministic and independent from the LLM. A model cannot promote its own
privileges.

## A4 — Execution adapters

A4 adds the first real runtime boundary without coupling ST to a provider SDK.

### Provider execution

`providers/openai_compatible.py` implements the existing `ModelClient` contract against a
standard chat-completions HTTP endpoint. This lets compatible hosted or self-hosted GLM, Qwen,
Kimi and future models be configured without changing the orchestration core.

`execution.py` routes an `AgentTask` to a model profile and executes the configured client.
`cli.py` exposes this path as `st-music-agent`.

### Credential boundary

`credentials.py` stores only environment-variable names in configuration. Secret values are
resolved at the final adapter boundary and are not copied into task, router or policy state.

### Network boundary

`transport.py` is a dependency-free JSON transport. It permits only absolute HTTP/HTTPS URLs
and does not include remote HTTP response bodies in exceptions.

### OpenHands boundary

`openhands.py` talks to the public OpenHands Agent Server REST API using `/api/conversations`.
The current A4 adapter intentionally starts conversations with no OpenHands terminal/editor
tools. This prevents an external agent runtime from bypassing ST's deterministic A3 policy.

OpenHands documents `TerminalTool`, `FileEditorTool` and `TaskTrackerTool` for software-agent
work. Those tools belong in A5 only after their side effects are constrained by sandbox and
approval policy.

## Current flow

```text
AgentTask
   |
   v
ModelRouter ---------> ModelProfile
   |                       |
   v                       v
DirectAgentRunner -> ModelClient adapter -> HTTP provider

External agent path:
ST config -> OpenHands adapter -> OpenHands Agent Server -> reasoning-only conversation (A4)

Tool path:
ActionRequest -> AutonomyPolicy -> GuardedActionExecutor -> operation / gate / deny
```

## A5 continuation

1. Add an isolated workspace/sandbox contract.
2. Add explicitly classified terminal and file-edit operations.
3. Enable OpenHands engineering tools only through the controlled execution boundary.
4. Add run journal, event capture and resumable state.
5. Add GitHub-specific action metadata and PR/CI workflows.
6. Add music-domain tools and structured evidence contracts.

## Architectural invariants

1. Model choice is replaceable.
2. Tools declare risk before execution.
3. Protected/destructive actions cannot be silently escalated.
4. Failure to find a compatible model fails closed.
5. Credentials are resolved only at adapter boundaries.
6. External agent frameworks cannot silently bypass ST action policy.
7. Music-specific intelligence stays above generic execution infrastructure.
8. Tests define routing, safety and adapter behavior before capabilities are widened.
