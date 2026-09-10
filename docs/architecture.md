# ST Music Agent Lab — Architecture Map

Status: A1-A7 guarded agent foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. It
coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Design decision

Do not fork a large agent framework into this repository. Keep the ST core small and stable,
then attach model providers, OpenHands, GitHub and music-domain capabilities through adapters.
External agent frameworks must not bypass ST-owned policy, tool and sandbox boundaries.

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

`GuardedCommandRunner` requires a `SandboxBackend`; without one, process execution is disabled.
`sandbox.py` provides the first concrete backend: `DockerSandboxBackend`.

Default Docker security contract:

- exact digest-pinned image reference;
- ephemeral named container with timeout cleanup;
- networking disabled;
- all Linux capabilities dropped;
- `no-new-privileges` enabled;
- PID, CPU and memory limits;
- read-only container root and bounded `noexec,nosuid` `/tmp`;
- image `ENTRYPOINT` cleared;
- only the configured repository root bind-mounted;
- read-only Git inspection gets a read-only mount;
- validation operations get a writable repository mount;
- Docker resource and image strings validated against option-injection forms.

## A7 — Structured tool calls, bounded output and run evidence

A7 creates the boundary a model must cross before it can drive ST-owned tools.

### Model-facing output

`output.py` defines `OutputSanitizer` and `OutputPolicy`.

- ANSI control sequences are stripped;
- configured sensitive values are replaced;
- common bearer/API/token patterns are redacted;
- sensitive mapping keys such as `api_key`, `token`, `password` and `secret` are redacted;
- output streams are bounded before they are exposed to higher orchestration;
- unsupported non-JSON-like values fail instead of being converted with `repr`.

`GuardedCommandRunner` now sanitizes the `SandboxResult` before returning its `ActionResult`.
The sandbox transport still captures raw process output internally, so this is a model-facing
and persistence boundary rather than a claim that raw bytes never exist in process memory.

### Explicit tool registry

`agent_tools.py` defines structured `ToolCallRequest`, `ToolCallResult`, `ToolCallStatus` and
`ToolRegistry` contracts.

- only explicitly registered ST-owned tool names execute;
- unknown names are rejected;
- duplicate registration is rejected;
- handler output is sanitized before exposure;
- handler exceptions return a sanitized error string without a traceback;
- the dispatcher performs no dynamic imports, shell evaluation or arbitrary command fallback.

Tool handlers remain responsible for using policy-aware primitives such as `GuardedWorkspace`
and `GuardedCommandRunner`; registering a handler does not grant it additional privileges.

### Tamper-evident run journal

`journal.py` implements an append-only JSONL `RunJournal`.

Each event contains a sequence number, run ID, UTC timestamp, sanitized payload, previous event
hash and SHA-256 event hash. Existing journals are verified before resuming; altered payloads,
broken hash links, non-contiguous sequences or mismatched run IDs fail closed.

The journal uses a process-local lock plus flush/fsync. It is not advertised as a multi-process
transaction log; a future storage backend can provide stronger distributed durability if needed.

## Current flow

```text
AgentTask -> ModelRouter -> ModelClient -> provider

Model tool request
       |
       v
ToolCallRequest -> ToolRegistry --unknown--> REJECTED
       | registered
       v
ST-owned handler -> ActionRequest -> AutonomyPolicy
       |                              |
       |                              +--> gate / deny
       v
GuardedWorkspace or GuardedCommandRunner
       |
       v
SandboxBackend -> Docker isolation -> sanitized SandboxResult
       |
       v
ToolCallResult -> model

Tool request/result -> sanitized RunJournal -> SHA-256 hash chain

OpenHands:
ST adapter -> Agent Server -> reasoning conversation
                 |
                 +-- raw Terminal/FileEditor tools remain disabled
```

## A8 continuation

1. Add GitHub-specific ST tool handlers for repository inspection, branch/PR status and CI.
2. Add a bounded model-driven tool loop that parses provider tool requests into
   `ToolCallRequest` and feeds structured results back to the model.
3. Keep write/merge/destructive GitHub actions behind existing action-risk policy.
4. Add explicit OpenHands-to-ST tool bridging rather than raw OpenHands terminal access.
5. Add music-domain tools and evidence contracts for Score Restore, MusicXML/TAB, Score Editor
   and score-following repositories.
6. Add run-level budgets for model turns, tool calls, output bytes and elapsed execution.

## Architectural invariants

1. Model choice is replaceable.
2. Models cannot grant themselves privileges.
3. Tools declare risk before execution.
4. Unknown tool names do not execute.
5. Protected/destructive actions cannot silently escalate.
6. Credentials are resolved only at adapter boundaries.
7. File operations cannot escape the repository root.
8. Host process execution is not an agent capability.
9. Executable repository code runs only through an ST-approved sandbox backend.
10. Read-only operations do not receive a writable repository mount.
11. Model-facing command output is bounded and redacted.
12. Persistent run evidence is sanitized and hash chained.
13. External agent frameworks cannot silently bypass ST policy or isolation.
14. Music-specific intelligence remains above generic execution infrastructure.
15. Tests define safety and adapter behavior before capabilities are widened.
