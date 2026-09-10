# ST Music Agent Lab — Architecture Map

Status: A1-A10 guarded agent foundation
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

Raw OpenHands terminal/editor tools are not exposed.

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
capability.

Model-callable mutation surface:

- `github.create_branch` from an exact commit SHA;
- `github.write_file` for one bounded non-sensitive UTF-8 file.

These are reversible writes. Feature-branch operations may auto-execute; `main`/`master` targets
are stopped before credential resolution/network access unless an exact host-side approval is
supplied. File deletion is `DESTRUCTIVE`; pull-request creation is an
`EXTERNAL_SIDE_EFFECT`; both exist only as host-side adapter paths and are not registered in the
model toolset. Merge remains absent.

Branch refs reject protected aliases/unsafe forms such as `HEAD`, `refs/*`, `heads/*`, hidden
segments and `.lock` segments. File paths reject traversal, backslashes, empty segments and
credential-sensitive locations.

## A10 — Cumulative run budgets and host approval broker

A10 adds two generic control planes above individual tools.

### Run budget tracker

`run_budget.py` defines `RunBudgetPolicy`, `RunBudgetTracker`, `RunBudgetSnapshot` and a
fail-closed `RunBudgetExceeded` boundary.

Each tool-loop run can now limit cumulatively:

- elapsed monotonic wall-clock time;
- model turns;
- tool calls;
- serialized UTF-8 bytes sent to the model, including replayed conversation history and tool
  definitions on every provider call.

`tool_loop.py` creates a new tracker for each run. Budget is charged before provider/tool work so
an overflow does not partially execute the next batch. Elapsed time is checked again after a
provider response and around tool dispatch. Successful results include a budget snapshot, and
completed-run journal evidence records the aggregate model-turn/tool-call/byte counts.

The existing per-call protocol limits remain separate from cumulative run budgets: maximum tool
argument size, tool-name size and call-ID size still apply before dispatch.

### Host approval broker

`approval_broker.py` defines `HostApprovalBroker` and one-shot `ApprovalTicket` objects.

- ticket IDs are cryptographically random opaque values generated by host code;
- a ticket binds exactly one action name and target;
- pending tickets can be approved or denied only through host methods;
- an approved ticket must match the exact `ActionRequest` when consumed;
- successful consumption emits the existing exact-match `ActionApproval` and permanently marks
  the ticket consumed;
- denied/consumed tickets cannot be reused;
- the broker is not registered as a model tool, so model arguments cannot manufacture approval.

This gives a future UI/server a pause -> human decision -> resume path without weakening A3's
deterministic action policy.

## Current flow

```text
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
          +---------------+------------------+
          |                                  |
  GitHubReadToolset                 GitHubMutationToolset
      read-only                    reversible subset
          |                       /               \
          |                create branch       write file
          +---------------------+------------------+
                                |
                                v
                          ActionRequest
                                |
                                v
                          AutonomyPolicy
                         /      |       \
                      auto     gate      deny
                       |        |
                       |        +--> HostApprovalBroker
                       |              pending -> human -> one-shot approval
                       v
              GitHub / guarded local tools

Host-only mutation paths:
delete file -> DESTRUCTIVE -> human approval
open PR     -> EXTERNAL_SIDE_EFFECT -> human approval
merge       -> not implemented/exposed

Executable local code -> GuardedCommandRunner -> SandboxBackend -> disposable Docker
Tool evidence -> sanitized RunJournal -> SHA-256 hash chain
OpenHands adapter -> Agent Server; raw Terminal/FileEditor remain disabled
```

## A11 continuation

1. Build an explicit OpenHands-to-ST bridge that advertises only `ToolRegistry` definitions and
   maps external tool requests back through ST budgets/policy rather than raw terminal/editor.
2. Add fake/local GitHub API integration fixtures covering complete read -> branch -> write ->
   human-gated PR flows.
3. Add resumable orchestration state linking run journal, budget snapshot and approval tickets
   without persisting provider hidden reasoning.
4. Begin music-domain tool/evidence contracts for Score Restore, MusicXML/TAB, Score Editor and
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
19. External agent frameworks cannot bypass ST policy, budget or isolation.
20. Music-specific intelligence remains above generic execution infrastructure.
21. Tests define safety behavior before capability is widened.
