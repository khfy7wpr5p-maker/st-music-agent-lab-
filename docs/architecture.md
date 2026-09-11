# ST Music Agent Lab — Architecture Map

Status: A1-A11 guarded agent foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. It
coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Design decision

Keep the ST core small and stable rather than forking a large agent framework. Model providers,
OpenHands, GitHub and future music-domain capabilities attach through explicit adapters. External
frameworks must not bypass ST-owned policy, tool, budget, approval or sandbox boundaries.

## A1-A3 — Core, routing and policy

- `contracts.py`: stable task, model, provider and action-risk contracts.
- `catalog.py` / `router.py`: capability-driven model selection.
- `policy.py` / `tools.py`: deterministic execution gates independent from the LLM.

Initial routing uses GLM-5.1 for primary agentic engineering, Qwen3.8 as a secondary
long-context profile and Kimi-K2.5 for multimodal/score-image work.

## A4 — Execution adapters

- `providers/openai_compatible.py`: provider-neutral chat-completions adapter.
- `execution.py`: routed provider-backed execution.
- `cli.py`: first command-line entrypoint.
- `credentials.py`: secrets resolved only at adapter boundaries.
- `transport.py`: HTTP/HTTPS-only JSON transport with sanitized errors.
- `openhands.py`: public OpenHands Agent Server REST adapter.

## A5 — Guarded workspace

`workspace.py` confines file reads/writes/deletions to a fixed repository root and rejects
absolute paths, traversal and symlink escapes. Writes inherit branch policy and destructive file
deletion requires exact approval. `commands.py` accepts only a narrow Git inspection and
pytest/Ruff validation command set.

## A6 — Disposable Docker sandbox

`GuardedCommandRunner` requires a `SandboxBackend`. `DockerSandboxBackend` uses exact
digest-pinned images, ephemeral containers, disabled networking, dropped Linux capabilities,
`no-new-privileges`, CPU/RAM/PID limits, read-only container root, bounded `noexec,nosuid`
`/tmp`, cleared image entrypoint and tightly scoped repository mounts.

## A7 — Structured tools, bounded output and evidence

`output.py` sanitizes and bounds model-facing output. `agent_tools.py` defines explicit tool
requests/results and a registry: only registered ST-owned handlers execute. `journal.py`
provides an append-only JSONL run journal with sanitized payloads and a SHA-256 previous-hash
chain, detecting tampering before resume.

## A8 — Provider tool loop and read-only GitHub surface

`providers/openai_compatible.py` supports OpenAI-compatible `tools` and `tool_choice=auto`.
`tool_loop.py` canonicalizes assistant function calls and maps them into the A7 registry.
Unknown provider fields are not replayed; provider reasoning state may be retained only inside
provider history and is removed from public output/journal evidence. Duplicate IDs,
non-function calls and malformed/oversized arguments fail closed.

`github_read.py` exposes only bounded read tools for repository metadata, text files, branches,
pull requests and workflow status. Common credential/key paths are denied before network access.

## A9 — Policy-aware GitHub mutations

`github_write.py` adds remote mutation support without turning GitHub into an unrestricted model
capability. Model-callable mutations are limited to `github.create_branch` and
`github.write_file`; both are reversible writes. Feature-branch operations may auto-execute,
while `main`/`master` targets stop before credential resolution/network access unless an exact
host-side approval is supplied. File deletion and PR creation remain host-only gated operations;
merge remains absent.

## A10 — Cumulative run budgets and host approval broker

`run_budget.py` enforces per-run monotonic elapsed time, model-turn count, tool-call count and
serialized model-facing byte limits. `tool_loop.py` charges these budgets before provider/tool
work to prevent partial execution after overflow.

`approval_broker.py` provides opaque one-shot host approval tickets. A ticket binds exactly one
action name and target, can be approved/denied only by host code, and yields the existing
`ActionApproval` only once after exact-match verification. The broker is never a model tool.

## A11 — OpenHands-to-ST restricted bridge

A11 connects OpenHands Agent Server to the ST-owned tool boundary without exposing raw OpenHands
terminal/editor capability.

### OpenHands MCP contract

Current OpenHands SDK uses a flat `mcp_config: dict[str, MCPServer]` server map. Remote MCP
servers may use `streamable-http`, and OpenHands applies `filter_tools_regex` after built-in and
MCP tools are combined. A bridged ST conversation therefore uses:

- `agent.tools = []` — no `TerminalTool`, `FileEditorTool` or arbitrary SDK tool module;
- one fixed MCP server entry named `st_tools`;
- `transport = streamable-http`;
- safe default built-ins only: `FinishTool` and `ThinkTool`;
- an exact anchored allowlist regex containing only `finish`, `think` and names derived from the
  actual ST `ToolRegistry` manifest.

`openhands.py` validates the configured bridge endpoint. Non-loopback HTTP is rejected; remote
bridge URLs must use HTTPS. User-info and fragments are rejected. Optional bearer credentials are
resolved from an environment variable only while the trusted host builds the Agent Server request.

The ST registry is validated before conversation startup. An empty registry fails closed, MCP
incompatible tool names fail closed and registry names `finish`/`think` are rejected to prevent
collision with the safe OpenHands built-ins.

### ST bridge core

`openhands_bridge.py` defines `STToolBridge` as a protocol-neutral core suitable for a host MCP
sidecar:

- tool discovery is projected only from `ToolRegistry.provider_tools()` into MCP-style
  `name` / `description` / `inputSchema` records;
- tool names must match the bounded MCP-compatible ST naming subset;
- input schemas must be object schemas;
- each invocation receives a host-generated opaque call ID and is dispatched only through
  `ToolRegistry`;
- unknown tool names are rejected by the registry rather than dynamically imported/resolved;
- tool arguments must be canonical JSON objects and are bounded by UTF-8 byte size;
- bridge elapsed/tool-call budgets fail closed before extra dispatch;
- results remain subject to A7 registry sanitization and can be projected to MCP `content`,
  `structuredContent` and `isError` fields.

A11 intentionally does **not** start an HTTP MCP server inside the library. The network listener,
TLS termination and deployment lifecycle remain host concerns; the library supplies the
validated OpenHands configuration and ST dispatch core. This keeps network privilege out of the
agent package while establishing the exact interoperability boundary.

## Current flow

```text
Direct provider path:
AgentTask -> ModelRouter -> OpenAICompatibleClient
                          ^
                          |
                 RunBudgetTracker
            time / turns / calls / bytes
                          |
                          v
                  canonical tool calls
                          |
                          v
                       ToolRegistry
                          |
                ST policy-aware tools

OpenHands path:
OpenHands Agent Server
        |
        | tools=[]
        | include defaults: finish / think only
        | one MCP server: st_tools
        | exact filter_tools_regex
        v
Host Streamable-HTTP MCP sidecar
        |
        v
STToolBridge -> ToolRegistry -> AutonomyPolicy -> GitHub / guarded local tools
      |              |
      |              +-> HostApprovalBroker for gated host actions
      +-> bridge call/time budget

Executable local code -> GuardedCommandRunner -> SandboxBackend -> disposable Docker
Tool evidence -> sanitized RunJournal -> SHA-256 hash chain
```

## A12 continuation

1. Implement a deployable Streamable HTTP MCP sidecar around `STToolBridge`, with authenticated
   startup, protocol-version negotiation and no ambient host privileges.
2. Add end-to-end OpenHands Agent Server integration tests against that sidecar, verifying that
   `terminal`/`file_editor` cannot appear or execute.
3. Add fake/local GitHub API integration fixtures covering read -> branch -> write -> human-gated
   PR flows.
4. Add resumable orchestration state linking journal, budget snapshot and approval tickets without
   persisting provider hidden reasoning.
5. Begin music-domain tool/evidence contracts for Score Restore, MusicXML/TAB, Score Editor and
   real-time score following.

## Architectural invariants

1. Model choice is replaceable.
2. Models cannot grant themselves privileges or approvals.
3. Tools declare risk before execution.
4. Unknown tool names do not execute.
5. Protected/destructive/external actions cannot silently escalate.
6. Credentials resolve only after policy permits an adapter operation.
7. File operations cannot escape configured repository/workspace boundaries.
8. Host process execution is not a model capability.
9. Executable repository code runs only through an ST-approved sandbox backend.
10. Read-only local operations do not receive a writable repository mount.
11. Model-facing output is bounded and redacted.
12. Persistent run evidence is sanitized and hash chained.
13. Provider schemas are not host authorization.
14. GitHub model mutations are limited to reversible feature-branch operations.
15. Protected branch aliases and credential-sensitive paths fail closed before network access.
16. Delete/PR/merge authority is never silently inherited by a model toolset.
17. A run cannot silently exceed cumulative time/turn/tool/byte limits.
18. Approval artifacts are host-generated, exact-match and one-shot.
19. OpenHands raw terminal/editor tools are absent from the bridged agent configuration.
20. OpenHands MCP discovery is filtered to the concrete ST registry manifest plus finish/think.
21. External agent frameworks cannot bypass ST policy, budget or isolation.
22. Music-specific intelligence remains above generic execution infrastructure.
23. Tests define safety behavior before capability is widened.
