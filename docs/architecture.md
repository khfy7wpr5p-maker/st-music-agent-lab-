# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1-APP2 runnable guarded application
Date: 2026-09-11

## Purpose

ST Music Agent Lab is the model-agnostic engineering and music-intelligence control layer for ST
projects. The A1-A26 core owns policy, tools, budgets, approvals, evidence, verification, learning,
training/model lifecycle, canonical-baseline history, drift and rollback-recovery boundaries.
APP1-APP2 provide the real operator application above those boundaries.

## Core map

```text
ST music repositories
  -> source-provenanced evidence
  -> deterministic planner
  -> independent verifier
  -> guarded reversible execution + CI/validators
  -> exact execution evidence
  -> curated data / training contract
  -> immutable model candidate
  -> paired benchmark + promotion review
  -> separately authorized activation/canonicalization
  -> repeated health/stability evidence
  -> append-only Baseline Registry
  -> long-term drift watch
  -> host-reviewed rollback request
  -> separately authorized rollback receipt
  -> repeated recovery evidence
  -> append-only rollback generation
```

Critical production actions never become model self-authority.

## APP1 — Operator Console

APP1 starts with `st-music-agent app` and provides a mobile-friendly local web interface for:

- Score Restore;
- MusicXML → Guitar TAB;
- Score Editor;
- Real-Time Score Following;
- project state, warnings and next safe boundary;
- fresh portfolio planning with deterministic independent verification.

Per-project evidence failures are isolated so one unavailable repository does not crash the whole
console.

## APP2 — Guarded task execution

APP2 adds an explicit task preview/run/PR flow without creating a second mutation architecture.
Write mode is opt-in and loopback-only.

```text
browser instruction
  -> POST /api/tasks/preview
  -> exact repository + protected base SHA
  -> deterministic st-agent/<project>/<task> branch
  -> AutonomyPolicy recomputation
       create branch = AUTO_EXECUTE
       write file   = AUTO_EXECUTE
       open PR      = REQUIRE_HUMAN
  -> explicit user Run click
  -> host creates exact feature branch
  -> ToolLoopRunner
       github.repo_metadata
       github.tree
       github.read_file
       github.branch_info
       github.workflow_runs
       task.write_file
  -> exact branch head + workflow evidence
  -> explicit human Open PR click
  -> no merge endpoint
```

### Branch confinement

The model does not receive `github.create_branch` or `github.open_pull_request`. Its only mutation
tool is `task.write_file`, whose JSON schema has no branch field. The host injects the exact branch
created from the preview. Attempts to supply `branch=main` or any other extra field fail schema/tool
validation.

### Repository discovery

APP2 adds task-scoped `github.tree`:

- branch is resolved to an exact full commit SHA;
- recursive Git tree truncation fails closed;
- only blob paths are returned;
- credential-sensitive paths are filtered;
- more than 2,000 safe files fails closed rather than silently hiding repository state.

### HTTP boundary

Read routes remain available in normal mode. Task POSTs require a random per-process
`X-ST-Session` token and bounded JSON bodies. Feature-branch execution requires `--enable-writes`.
Write mode refuses non-loopback HTTP binding.

Provider/GitHub credentials are configured by environment-variable **name** and resolved only at
trusted adapters. They are not sent to the browser or model output.

## Explicitly unavailable in APP2

- direct `main` / `master` mutation;
- arbitrary branch selection by the model;
- file deletion;
- autonomous PR creation;
- merge;
- release/deployment;
- training execution;
- model activation/canonicalization;
- rollback execution.

PR creation is an external side effect and occurs only from a separate human UI click with an exact
`ActionApproval`. Merge remains outside the application.

## A1-A26 invariants retained

1. Models cannot grant themselves privileges or approvals.
2. Unknown tools never execute.
3. Secret/credential paths fail closed.
4. Reversible writes on non-protected branches may auto-execute only after deterministic policy.
5. Protected/destructive/external actions remain human/host gated.
6. Plans and lifecycle widening are independently recomputed from evidence.
7. Training, activation, canonicalization and rollback remain separate host-authorized boundaries.
8. Baseline history is append-only; failed generations are retained.
9. APP2 development output is not production authority.
10. Tests define the widened application behavior before merge.

## Next application boundary — APP3

APP3 should make task runs durable and inspectable across app restarts: persistent task journal,
explicit CI/validator completion state, run history, and safe retry/resume. It should not widen merge
or production authority.
