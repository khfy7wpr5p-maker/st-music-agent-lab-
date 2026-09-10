# ST Music Agent Lab — Architecture Map

Status: A1-A8 guarded agent foundation
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

`GuardedCommandRunner` sanitizes the `SandboxResult` before returning its `ActionResult`.

### Explicit tool registry

`agent_tools.py` defines structured `ToolCallRequest`, `ToolCallResult`, `ToolCallStatus`,
`ToolDefinition` and `ToolRegistry` contracts.

- only explicitly registered ST-owned tool names execute;
- unknown names are rejected;
- duplicate registration is rejected;
- handler output is sanitized before exposure;
- handler exceptions return a sanitized error string without a traceback;
- provider schemas describe allowed tools but do not grant privileges.

### Tamper-evident run journal

`journal.py` implements an append-only JSONL `RunJournal` with sequence numbers, UTC timestamps,
sanitized payloads and a SHA-256 previous-hash chain. Existing journals are verified before
resume and fail closed on tampering or structural discontinuity.

## A8 — Provider tool loop and read-only GitHub surface

A8 adds a bounded provider-driven function-calling loop without widening action privilege.

### Provider tool loop

`providers/openai_compatible.py` can send OpenAI-compatible `tools` definitions and
`tool_choice=auto`. `tool_loop.py` converts provider tool requests into the A7 registry.

Safety and compatibility rules:

- only provider messages with assistant role are accepted;
- unknown provider message fields are not replayed into later turns;
- tool calls are canonicalized to the function-call shape before replay;
- optional `reasoning_content` may be preserved only in internal provider history for compatible
  multi-turn servers, but it is stripped from public results and is not journaled;
- duplicate tool-call IDs within a turn are rejected;
- non-function tool calls are rejected;
- tool-call IDs, tool names and argument payloads are size bounded;
- malformed/non-object JSON arguments fail before dispatch;
- turn and total tool-call budgets fail closed before partial execution of an overflowing batch;
- the final public assistant message is projected to role/content and sanitized.

The provider schema remains advisory. Host-side tool handlers independently validate arguments.

### Read-only GitHub tools

`github_read.py` exposes an explicit first GitHub toolset:

- `github.repo_metadata`;
- `github.read_file`;
- `github.branch_info`;
- `github.pull_request`;
- `github.workflow_runs`.

There are no model-callable GitHub write, branch creation, commit, PR mutation or merge tools in
A8.

GitHub read responses are projected to bounded fields. File reads are limited to UTF-8 text and
bounded character counts. Common credential-sensitive paths such as `.env*`, `.npmrc`, `.pypirc`,
private-key files and common cloud/SSH credential directories are rejected before network access.
Base64 content is decoded strictly rather than best-effort. Tool handlers reject unexpected
argument fields even if a provider ignores the advertised JSON schema.

## Current flow

```text
AgentTask -> ModelRouter -> OpenAICompatibleClient
                          |
                          v
                   provider response
                          |
                          v
             canonical assistant message
                          |
                    tool_calls?
                     /       \
                   no         yes
                   |           |
                   v           v
          sanitized final   ToolCallRequest
                              |
                              v
                         ToolRegistry
                              |
                    registered handler only
                              |
             +----------------+----------------+
             |                                 |
     GitHubReadToolset                 policy-aware ST tools
      (read-only A8)                           |
             |                         GuardedWorkspace /
             |                         GuardedCommandRunner
             |                                 |
             +----------------+----------------+
                              |
                              v
                        ToolCallResult
                              |
                              v
                     provider next turn

Tool request/result -> sanitized RunJournal -> SHA-256 hash chain

OpenHands:
ST adapter -> Agent Server -> reasoning conversation
                 |
                 +-- raw Terminal/FileEditor tools remain disabled
```

## A9 continuation

1. Add policy-aware GitHub mutation adapters for feature-branch commits and PR creation while
   keeping protected-branch writes, merges and destructive actions human-gated.
2. Add elapsed-time and aggregate model/output budget accounting at run level.
3. Add explicit OpenHands-to-ST tool bridging rather than raw OpenHands terminal access.
4. Add music-domain tools and evidence contracts for Score Restore, MusicXML/TAB, Score Editor
   and score-following repositories.
5. Add integration tests against a disposable/local OpenAI-compatible server and a fake GitHub
   API fixture before enabling broader production use.

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
13. Provider schemas are not treated as host-side authorization.
14. GitHub model tools are read-only until mutation tools are separately policy-wrapped.
15. Credential-sensitive repository paths are denied before model-visible file reads.
16. External agent frameworks cannot silently bypass ST policy or isolation.
17. Music-specific intelligence remains above generic execution infrastructure.
18. Tests define safety and adapter behavior before capabilities are widened.
