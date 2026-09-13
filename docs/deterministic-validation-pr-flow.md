# Deterministic validation-PR flow

This flow closes the CI deadlock for repositories whose GitHub Actions run only on `pull_request`.

## Invariants

- The local model remains planner-only (`MODEL_PLANS_HOST_EXECUTES`).
- The model receives no write, shell, PR, merge, deployment, training, activation, or rollback tools.
- Host-side validators must pass before a pre-verification validation PR can be opened.
- Opening the PR still requires the existing explicit human `github.open_pull_request` approval.
- The validation PR does **not** mean `VERIFIED_SUCCESS` and never authorizes merge or production actions.
- The bound feature-branch HEAD must still equal the exact task commit before PR creation.
- Exact-SHA CI evidence is refreshed after the PR triggers workflows.
- Only successful exact-SHA CI plus passing validators can advance the task to `VERIFIED_SUCCESS`.
- Merge remains outside this application.

## State sequence

Typical PR-triggered-CI repository:

1. `PREVIEWED`
2. `BRANCH_CREATED`
3. `AGENT_RUNNING`
4. `AGENT_COMPLETED`
5. `COMMIT_BOUND`
6. `CI_PENDING`
7. host evidence refresh confirms `ci.state=pending` and all configured validators `PASS`
8. human explicitly opens a validation PR
9. the journal records `PR_OPENED` as evidence while the task stage intentionally stays `CI_PENDING`
10. pull-request workflows run against the bound HEAD
11. evidence refresh reviews exact-SHA CI
12. `CI_REVIEWED`
13. `VALIDATORS_REVIEWED`
14. `VERIFIED_SUCCESS`

The early `PR_OPENED` record is an evidence event rather than a stage transition. This preserves the existing APP3-APP7 stage machine and audit replay while making the PR metadata persistent across restarts.

## Fail-closed behavior

A validation PR is rejected when any of the following is true:

- the task is not at `CI_PENDING` (or already `VERIFIED_SUCCESS`),
- CI evidence is failed or unavailable rather than pending,
- any configured host validator is `FAIL` or `UNAVAILABLE`,
- the feature branch moved away from the bound task HEAD,
- PR read-back does not match the intended head/base refs,
- explicit human approval is not present.

No automatic merge path is introduced.
