# APP8C — Guarded Multi-Agent Execution

Status: guarded execution bridge built on APP2–APP7 authority boundaries.

APP8C is the first APP8 stage that may perform a real reversible engineering write, but it does not create a new write authority. The implementation role reuses the existing APP3–APP7 task service and its host-bound feature branch. Evidence, validation, and critic specialists remain exact-commit read-only.

## Role execution profile

```text
Evidence Agent      -> exact-SHA read-only
Implementation Agent-> existing APP3–APP7 reversible feature-branch path
Validation Agent    -> exact-SHA read-only
Critic Agent        -> exact-SHA read-only
```

APP8C does not add a PR-open, PR-approval, review-thread mutation, merge, deployment, training, activation, canonicalization, rollback, credential, or privilege-management tool.

## Exact-commit specialist reads

`ExactCommitReadToolset` verifies that the configured branch resolves to the expected full commit SHA and captures its bounded file tree. The model sees only:

- `task.list_files()`
- `task.read_file(path)`

The model cannot provide a branch or ref. File reads inject the exact commit SHA host-side. If the branch or captured tree no longer matches the expected SHA, setup fails closed. This prevents evidence, validation, or critic agents from silently reviewing a moving target.

`ReadOnlySpecialistRunner` accepts only `EVIDENCE`, `VALIDATION`, or `CRITIC` nodes whose mutation class is `READ_ONLY`. The selected model profile must satisfy the node's existing `AgentTask` capability contract. The model final response must be strict bounded JSON with exactly `verdict` and `summary` fields.

The runner never treats model prose as CI or validator proof. Validation and critic claims remain bound to an explicitly supplied subject artifact SHA-256 and exact commit SHA.

## Implementation bridge

`GuardedImplementationBridge` exposes only the following narrow APP7-style protocol:

```text
preview
run
refresh_evidence
status
verify_current_audit
```

The protocol intentionally contains no `open_pull_request` or merge method.

Before execution it requires:

- `IMPLEMENTATION` role;
- `REVERSIBLE_FEATURE_BRANCH` mutation class;
- exact expected base SHA;
- node repository == task preview repository;
- base branch remains `main` or `master`;
- generated feature branch is non-protected and exactly matches the node binding.

After the existing APP3–APP7 run it requires the run repository, base SHA, feature branch, and exact head SHA to remain bound to the preview. It then performs one evidence refresh. APP8C does not busy-loop or fabricate CI completion.

A producer verification claim can be created only if the underlying task reaches `VERIFIED_SUCCESS` and APP7 `verify_current_audit()` also returns a verified local hash-journal/audit result. Pending, review-required, or failed tasks cannot become producer PASS claims.

APP8C itself never opens the PR. Existing later human/operator review and PR controls remain separate.

## Three-way cycle gate

A verified implementation record, exact-bound validation result, and independent exact-bound critic result can be passed to the APP8B `IndependentDisagreementGate`.

Even an `ACCEPT` result remains verification evidence only:

```text
execution_authorized = false
repository_mutation_authorized = false
merge_authorized = false
production_actions_authorized = false
```

It does not authorize another write, a PR, merge, deployment, or model lifecycle action.

## Graph guard

`validate_execution_graph()` currently allows at most one implementation node in one APP8C graph. Every non-implementation node must remain read-only. This deliberately prevents a multi-writer topology before later stages have evidence that the simpler execution profile is reliable.

## Next boundary

APP8D may coordinate dependencies across the existing ST project repositories, but cross-project planning must remain evidence-driven and may not convert one project's success into another project's write or production authority. APP8E may expose supervision state in the operator UI after those contracts are independently tested.
