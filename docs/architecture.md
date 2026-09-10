# ST Music Agent Lab — Architecture Map

Status: A1-A6 sandboxed execution foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer.
It coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Design decision

Do not fork a large agent framework into this repository. Keep the ST core small and stable,
then attach model providers, OpenHands, GitHub and music-domain capabilities through adapters.
External agent frameworks must not bypass ST-owned policy and sandbox boundaries.

## A1-A3 — Core, routing and policy

- `contracts.py`: stable task, model, provider and action-risk contracts.
- `catalog.py` / `router.py`: capability-driven model selection.
- `policy.py` / `tools.py`: deterministic execution gates independent from the LLM.

Initial model routing uses GLM-5.1 for primary agentic engineering, Qwen3.8 as a secondary
long-context profile and Kimi-K2.5 for multimodal/score-image work.

## A4 — Execution adapters

- `providers/openai_compatible.py`: provider-neutral chat-completions adapter.
- `execution.py`: routed provider-backed execution.
- `cli.py`: first command-line entrypoint.
- `credentials.py`: secrets resolved only at adapter boundaries.
- `transport.py`: HTTP/HTTPS-only JSON transport with sanitized errors.
- `openhands.py`: public OpenHands Agent Server REST adapter.

OpenHands conversations still receive no unrestricted terminal/editor tools.

## A5 — Guarded workspace

`workspace.py` confines file reads/writes/deletions to a fixed repository root and rejects
absolute paths, traversal and symlink escapes. Writes inherit branch policy and destructive
file deletion requires an exact approval.

`commands.py` classifies a narrow set of Git inspection and pytest/Ruff validation commands.
Arbitrary shell/Python commands and Git options such as `--ext-diff`, `--textconv`, `--output`
and `--no-index` are rejected.

## A6 — Disposable Docker sandbox

A6 removes the loose `process_execution_enabled=True` convention. `GuardedCommandRunner` now
requires a `SandboxBackend`; without one, process execution is disabled.

`sandbox.py` provides the first concrete backend: `DockerSandboxBackend`.

Default Docker security contract:

- image references are pinned to an exact `sha256` digest;
- container is ephemeral (`--rm`) and named so timeout cleanup can force-remove it;
- networking is disabled;
- all Linux capabilities are dropped;
- `no-new-privileges` is enabled;
- PID, CPU and memory limits are applied;
- container root filesystem is read-only;
- `/tmp` is a bounded `noexec,nosuid` tmpfs;
- image `ENTRYPOINT` is cleared so the classified ST command is authoritative;
- only the configured repository root is bind-mounted;
- read-only Git inspection mounts the repository read-only;
- validation operations receive a writable repository mount;
- Docker resource strings and image references are validated against option-injection forms.

This matches the architectural direction of OpenHands ephemeral Docker/Kubernetes workspaces,
while keeping ST policy authoritative over which commands may reach the sandbox.

## Current flow

```text
AgentTask -> ModelRouter -> ModelClient -> provider

ActionRequest -> AutonomyPolicy -> GuardedActionExecutor

File operation:
relative path -> GuardedWorkspace -> policy -> confined filesystem operation

Command operation:
argv -> command allowlist -> risk classification -> policy
     -> SandboxBackend -> ephemeral Docker container -> repository mount

OpenHands:
ST adapter -> Agent Server -> reasoning conversation
                 |
                 +-- unrestricted Terminal/FileEditor tools remain disabled
```

## A7 continuation

1. Add structured tool-call request/result contracts for a model-driven agent loop.
2. Add an append-only run journal with resumable execution state.
3. Add bounded/redacted command-output handling before exposing sandbox output to models.
4. Add GitHub-specific adapters for repository inspection, branches, PRs and CI.
5. Add an explicit OpenHands-to-ST tool bridge instead of enabling raw OpenHands terminal access.
6. Add music-domain tools and evidence contracts for Score Restore, MusicXML/TAB, Score Editor
   and score-following repositories.

## Architectural invariants

1. Model choice is replaceable.
2. Models cannot grant themselves privileges.
3. Tools declare risk before execution.
4. Protected/destructive actions cannot silently escalate.
5. Credentials are resolved only at adapter boundaries.
6. File operations cannot escape the repository root.
7. Host process execution is not an agent capability.
8. Executable repository code runs only through an ST-approved sandbox backend.
9. Read-only operations do not receive a writable repository mount.
10. External agent frameworks cannot silently bypass ST policy or isolation.
11. Music-specific intelligence remains above generic execution infrastructure.
12. Tests define safety and adapter behavior before capabilities are widened.
