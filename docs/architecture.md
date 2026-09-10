# ST Music Agent Lab — Architecture Map

Status: A1-A5 guarded execution foundation
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

- `providers/openai_compatible.py`: chat-completions provider adapter.
- `execution.py`: task routing plus one provider-backed execution turn.
- `cli.py`: first `st-music-agent` command-line entrypoint.
- `credentials.py`: environment-variable credential boundary.
- `transport.py`: HTTP/HTTPS-only JSON transport with sanitized errors.
- `openhands.py`: public OpenHands Agent Server REST adapter.

The OpenHands adapter still starts reasoning-only conversations with no terminal/editor tools.
This prevents the external runtime from bypassing ST policy.

## A5 — Guarded workspace and process boundary

A5 creates the first ST-owned repository tool surface.

### Confined file operations

`workspace.py` resolves every file operation against a fixed repository root.

- absolute paths are rejected;
- `..` traversal outside the root is rejected;
- existing symlinks that resolve outside the root are rejected;
- read operations are classified as read-only;
- writes are reversible writes and inherit branch policy;
- deletions are destructive and therefore require exact approval.

This gives future agents a file-edit route that is narrower than an unrestricted terminal.

### Process execution

`commands.py` deliberately separates command classification from OS isolation.

The runner is disabled by default. A host must explicitly set `process_execution_enabled=True`
only after placing the process inside an externally isolated workspace such as a disposable
container or VM.

When enabled, the initial allowlist is intentionally narrow:

- selected Git inspection commands (`status`, `diff`, `log`, `show`, `rev-parse`);
- `pytest` / `python -m pytest`;
- `ruff check`.

Git options capable of external diff execution or output-file side effects are rejected.
Arbitrary shell commands and `python -c` are not accepted.

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
ST config -> OpenHands adapter -> OpenHands Agent Server -> reasoning-only conversation

File tool path:
relative path -> GuardedWorkspace -> ActionRequest -> AutonomyPolicy -> read/write/gate

Command path:
argv -> allowlist/classifier -> isolation gate -> ActionRequest -> AutonomyPolicy -> subprocess
```

## A6 continuation

1. Add a concrete disposable sandbox backend (container/remote workspace adapter).
2. Bind command execution enablement to verified sandbox capability rather than a loose caller
   convention.
3. Add structured tool-call requests/results for model-driven agent loops.
4. Add run journal, event capture and resumable state.
5. Add GitHub-specific read/write/PR/CI action adapters.
6. Evaluate whether OpenHands terminal/editor tools can be safely delegated inside that sandbox
   or whether ST-owned tools should remain the authoritative execution surface.
7. Add music-domain tools and structured evidence contracts.

## Architectural invariants

1. Model choice is replaceable.
2. Tools declare risk before execution.
3. Protected/destructive actions cannot be silently escalated.
4. Failure to find a compatible model fails closed.
5. Credentials are resolved only at adapter boundaries.
6. External agent frameworks cannot silently bypass ST action policy.
7. File operations cannot escape the configured repository root.
8. OS process execution is disabled until an external isolation layer explicitly enables it.
9. Music-specific intelligence stays above generic execution infrastructure.
10. Tests define routing, safety and adapter behavior before capabilities are widened.
