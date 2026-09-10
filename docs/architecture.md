# ST Music Agent Lab — Architecture Map

Status: A1-A9 guarded agent foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. It
coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Design decision

Do not fork a large agent framework into this repository. Keep the ST core small and stable,
then attach model providers, OpenHands, GitHub and music-domain capabilities through adapters.
External frameworks must not bypass ST-owned policy, tool and sandbox boundaries.

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

Raw OpenHands terminal/editor tools are not exposed.

## A5 — Guarded workspace

`workspace.py` confines file reads/writes/deletions to a fixed repository root and rejects
absolute paths, traversal and symlink escapes. Writes inherit branch policy and destructive
file deletion requires exact approval.

`commands.py` accepts a narrow set of Git inspection and pytest/Ruff validation commands.
Arbitrary shell/Python commands and Git escape/side-effect options are rejected.

## A6 — Disposable Docker sandbox

`GuardedCommandRunner` requires a `SandboxBackend`. `sandbox.py` provides a hardened
`DockerSandboxBackend` with:

- exact digest-pinned images;
- ephemeral named containers with timeout cleanup;
- networking disabled;
- all Linux capabilities dropped and `no-new-privileges` enabled;
- PID, CPU and memory limits;
- read-only container root plus bounded `noexec,nosuid` `/tmp`;
- cleared image `ENTRYPOINT`;
- only the configured repository bind-mounted;
- read-only mounts for Git inspection and writable mounts only for approved validation work.

## A7 — Structured tools, bounded output and evidence

`output.py` sanitizes and bounds model-facing output. `agent_tools.py` defines explicit tool
requests/results and a registry: only registered ST-owned handlers execute. `journal.py`
provides an append-only JSONL run journal with sanitized payloads and a SHA-256 previous-hash
chain, detecting tampering before resume.

## A8 — Provider tool loop and read-only GitHub surface

`providers/openai_compatible.py` can send OpenAI-compatible `tools` plus `tool_choice=auto`.
`tool_loop.py` canonicalizes assistant function calls and maps them into the A7 registry.

Key rules:

- only assistant-role provider messages are accepted;
- unknown provider fields are not replayed;
- optional `reasoning_content` may be retained only in internal provider history and is removed
  from public results/journal evidence;
- duplicate IDs, non-function calls and malformed or oversized arguments fail closed;
- model-turn and tool-call budgets prevent partial execution past a limit;
- provider JSON schema is descriptive, not authorization; host handlers revalidate arguments.

`github_read.py` provides explicit read-only tools for repository metadata, bounded UTF-8 file
reads, branch metadata, PR metadata and workflow-run status. Common credential/key paths are
denied before network access and remote payloads are projected to bounded fields.

## A9 — Policy-aware GitHub mutations

`github_write.py` adds the first remote mutation layer, but does not turn GitHub into an
unrestricted model capability.

### Model-callable mutation surface

Only these handlers may be registered into `ToolRegistry`:

- `github.create_branch` — create a new branch from an exact full commit SHA;
- `github.write_file` — create/update one bounded non-sensitive UTF-8 file on a branch.

Both are classified as `REVERSIBLE_WRITE`. Feature-branch operations may auto-execute under the
existing deterministic autonomy policy. A write targeting `main` or `master` is stopped before
credential resolution or network access unless an exact host-side approval is supplied.

### Human-gated host operations

`GitHubMutationClient` also implements, but the model toolset does not register:

- `delete_file` — `DESTRUCTIVE`, therefore exact human approval required;
- `open_pull_request` — `EXTERNAL_SIDE_EFFECT`, therefore exact human approval required.

No GitHub merge operation is implemented or model-exposed in A9.

### Mutation safety rules

- GitHub token is resolved from an environment variable only inside an operation that policy has
  already permitted;
- full 40/64-character hexadecimal commit/blob IDs are required where relevant;
- branch names reject `HEAD`, `refs/*`, `heads/*`, `..`, empty path segments, hidden segments and
  `.lock`-style ref forms;
- file paths reject traversal, backslashes, empty segments and common credential/key locations;
- file content, commit messages and PR bodies are bounded;
- remote responses are projected to minimal fields before returning to higher orchestration;
- model arguments cannot carry or synthesize `ActionApproval`; approval remains host-side only.

## Current flow

```text
AgentTask -> ModelRouter -> OpenAICompatibleClient
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
   read-only A8                    A9 model surface only
          |                         |               |
          |                  create branch     write file
          |                         |               |
          +---------------+---------+---------------+
                          |
                          v
                    ActionRequest
                          |
                          v
                    AutonomyPolicy
                    /      |       \
                 auto     gate      deny
                  |        |
                  v        +--> exact host approval only
         GitHub / guarded local tools

Host-only A9 paths:
delete file -> DESTRUCTIVE -> approval gate
open PR     -> EXTERNAL_SIDE_EFFECT -> approval gate
merge       -> not implemented/exposed

Executable local code -> GuardedCommandRunner -> SandboxBackend -> disposable Docker

Tool request/result -> sanitized RunJournal -> SHA-256 hash chain

OpenHands adapter -> Agent Server
                    |
                    +-- raw Terminal/FileEditor remain disabled
```

## A10 continuation

1. Add run-level elapsed-time, cumulative model-turn, tool-call and model-facing byte budgets.
2. Add an explicit approval-broker contract so human-gated actions can pause/resume without
   allowing model-generated approval artifacts.
3. Add OpenHands-to-ST tool bridging that exposes only ST registry tools rather than raw terminal
   or editor access.
4. Add fake/local GitHub API integration fixtures to validate complete read/write policy flows.
5. Begin music-domain tool/evidence contracts for Score Restore, MusicXML/TAB, Score Editor and
   real-time score following.

## Architectural invariants

1. Model choice is replaceable.
2. Models cannot grant themselves privileges or approvals.
3. Tools declare risk before execution.
4. Unknown tool names do not execute.
5. Protected/destructive/external actions cannot silently escalate.
6. Credentials are resolved only at adapter boundaries after policy permits execution.
7. File operations cannot escape configured repository/workspace boundaries.
8. Host process execution is not a model capability.
9. Executable repository code runs only through an ST-approved sandbox backend.
10. Read-only operations do not receive a writable local repository mount.
11. Model-facing output is bounded and redacted.
12. Persistent run evidence is sanitized and hash chained.
13. Provider schemas are not treated as host authorization.
14. GitHub model mutations are limited to reversible feature-branch operations.
15. Protected branch aliases and credential-sensitive paths fail closed before network access.
16. Delete/PR/merge authority is never silently inherited by a model toolset.
17. External agent frameworks cannot bypass ST policy or isolation.
18. Music-specific intelligence remains above generic execution infrastructure.
19. Tests define safety behavior before capability is widened.
