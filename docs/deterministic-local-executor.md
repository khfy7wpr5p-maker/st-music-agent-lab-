# Deterministic Local Executor

Status: feature-branch implementation
Date: 2026-09-13

## Goal

The local small model is a bounded planner, not a repository executor. Repository inspection, mutation,
verification and exact commit binding remain host-side and deterministic.

```text
INSPECT (host)
  -> SELECT READ EVIDENCE (small model, JSON only)
  -> READ EXACT FILES (host)
  -> PLAN (small model, JSON only)
  -> VALIDATE PLAN (host)
  -> APPLY (host, exact branch/blob SHA)
  -> READ-BACK VERIFY (host)
  -> CHECKPOINT
  -> COMMIT_BOUND
  -> CI_PENDING
  -> existing APP3-APP7 validators/review/audit
  -> existing APP8 read-only supervision graph
  -> human-gated PR
```

The model receives no write, PR, merge, shell, deploy, release, training, activation,
canonicalization or rollback tool in this mode.

## Planner contract

`SmallModelPlanner` uses two bounded model calls and passes an empty tool list to both.

1. File selection: the model chooses at most three existing safe paths from a bounded repository-tree
   projection.
2. Plan generation: the host reads those files at the exact feature-branch HEAD and gives their complete
   content and blob SHA to the model. The model returns strict JSON only.

The plan contains:

- exact repository;
- exact base SHA;
- exact host-bound feature branch;
- at most three `create` or `update` changes;
- exact expected blob SHA for every update;
- complete replacement content;
- bounded commit message;
- validation targets and a summary.

Unknown fields, protected branches, path traversal, credential-sensitive paths and GitHub
workflow/action control paths fail closed. An update may target only a file whose full content was read
for the planner. A create target must be absent from the inspected tree.

## Host executor contract

`DeterministicExecutor` verifies that the feature branch still equals the plan base SHA before the first
mutation. Before each change it rechecks the exact branch HEAD and repository tree. Updates require the
current blob SHA to equal `expected_blob_sha`; creates require the target path not to exist.

After every successful write the host:

1. verifies the branch HEAD advanced exactly to the mutation result commit SHA;
2. re-reads the changed file from the exact feature branch;
3. compares complete content;
4. compares the returned content/blob SHA when available;
5. records an `EXECUTOR_CHECKPOINT`.

A partial failure is therefore bounded and observable. The model is not called again after mutation
execution starts.

## Task-state integration

`DeterministicApp3TaskService` and `DeterministicApp7TaskService` preserve the existing task state
machine. Existing stage names remain compatible:

```text
PREVIEWED -> BRANCH_CREATED -> AGENT_RUNNING -> AGENT_COMPLETED
          -> COMMIT_BOUND -> CI_PENDING -> ... -> VERIFIED_SUCCESS -> PR_OPENED
```

`AGENT_RUNNING` now means planner/executor task execution rather than a recursive model tool loop.
Additional evidence records include `PLAN_VALIDATED`, `EXECUTOR_CHECKPOINT`, `PLANNER_FAILURE` and
`EXECUTOR_FAILURE`.

A model final message is never success evidence. Success requires a real feature-branch HEAD different
from the base SHA, exact compare evidence and the existing CI/validator/review chain.

`FAILED` remains terminal for the task identity. Re-running the same failed attempt is rejected; a new
attempt/task identity is required.

## APP7 / APP8 authority preservation

The normal `st-music-agent app` entry point routes write-enabled task execution through
`DeterministicApp7TaskService`. APP7 audit/replay/validator behavior remains inherited. APP8 continues to
use its existing read-only graph store and operator endpoints.

This change does not add merge authority, automatic PR opening, deployment, release, training,
activation, canonicalization, rollback, credential mutation or remote write authority.

## CPU-only local smoke

Do not use a long recursive Ollama agent loop. Run one bounded smoke only after deterministic scripted
provider tests are green.

Recommended smoke shape:

1. start the existing local Qwen3 1.7B OpenAI-compatible profile;
2. start `st-music-agent app --enable-writes` on loopback with the local provider settings;
3. choose one disposable task whose safe change is limited to one small documentation/test file;
4. confirm the planner makes only the bounded selection + plan calls;
5. confirm a feature-branch commit is produced and `PLAN_VALIDATED` + `EXECUTOR_CHECKPOINT` evidence is
   present;
6. record exact feature-branch HEAD and changed files;
7. stop after the first result. If it fails, classify that single blocker instead of repeating timeout or
   context experiments.

The previous APP-11J pattern of `WORKING -> long wait -> FAILED -> commit=None` should not be retried as
an operator strategy. A small local model is intentionally not responsible for completing repository
mutation, commit binding or validation through a recursive tool loop.
