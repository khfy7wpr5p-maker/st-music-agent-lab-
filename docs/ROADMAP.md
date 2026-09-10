# ST Music Agent Lab — Roadmap

## Current checkpoint

- A0 — architecture baseline: COMPLETE / PR #1 open
- A1 — minimal Python foundation: COMPLETE
- A2 — OpenManus adapter foundation: COMPLETE
- A3 — bounded sandbox executor: COMPLETE
- A4 — GitHub read-only adapter: COMPLETE / PR #2 open
- A5 — lab-only branch/commit/PR writer: COMPLETE / PR #3 open / fixture PR #4 green
- A6+ — NOT STARTED

No merge, production deployment, secret mutation, or cross-repository write authority is activated.

## A0 — Architecture baseline

Goals:
- define the lab's purpose and non-goals;
- keep OpenManus replaceable behind an adapter;
- define capability, validation, GitHub, and human-approval boundaries;
- define safe future self-improvement rules.

Exit criteria:
- architecture, safety, roadmap, and machine-readable authority contract reviewed;
- no production or cross-repository write authority activated.

## A1 — Minimal Python foundation

Status: COMPLETE.

Implemented:
- `TaskSpec` schema;
- capability enum and policy engine;
- run state/result schema;
- structured run ledger;
- unit tests for allowed/denied actions;
- no network side effects in the core.

Exit evidence: deterministic policy tests pass and direct default-branch mutation is impossible through the core API.

## A2 — OpenManus adapter

Status: COMPLETE as a foundation boundary; raw upstream runtime remains intentionally disabled.

Implemented:
- exact upstream revision identity;
- provider/framework configuration isolated from ST policy;
- `TaskSpec` translated into bounded agent input;
- proposed actions re-evaluated through the ST policy gate;
- unrestricted upstream tools are not exposed by default.

Exit evidence: fixture planning cannot bypass the ST gate.

## A3 — Sandbox executor

Status: COMPLETE.

Implemented:
- temporary workspace boundary;
- explicit command grants and fixed safe command prefixes;
- stdout/stderr capture;
- timeout and retry budgets;
- sanitized environment and caller-provided secret redaction;
- Python/Node test command support;
- `shell=False` execution.

Exit evidence: deterministic fixture tests pass and GitHub Actions validates the foundation on Python 3.12.

## A4 — GitHub read-only adapter

Status: COMPLETE.

Implemented:
- repository/branch/commit/file metadata reads;
- PR reads;
- PR diff reads;
- workflow-run/CI reads by exact head SHA;
- deterministic evidence digests and locators;
- deterministic failing-PR diagnostic summary;
- concrete GitHub REST backend exposes GET only;
- requests are repository-scoped and byte/time bounded;
- no branch, commit, PR, merge, secret, deployment or mutation method exists on the adapter/backend.

Exit evidence: a prepared failing fixture PR is diagnosed as `FAILED`, its failing workflow is named, and the report carries exact read locators. A4 CI passed on Python 3.12.

## A5 — Lab-only branch/PR writer

Status: COMPLETE.

Implemented:
- host-trusted lab-repository confinement;
- `agent/` task branch prefix;
- exact base-SHA branch creation;
- bounded file creation/update through GitHub Contents API;
- one commit receipt per file mutation;
- expected blob SHA for safe existing-file updates;
- pull-request creation to `TaskSpec.base_ref`;
- bounded CI repair-attempt accounting;
- machine-readable `LAB_WRITE_SCOPE_V0.json`;
- no generic GitHub mutation surface.

Hard boundaries:
- no `main` / `master` mutation;
- no force-push/ref update;
- no merge;
- no PR PATCH;
- no workflow rerun;
- no secret/release/deployment mutation;
- no cross-repository write.

Exit evidence:
- PR #3 A5 implementation `foundation/unit-tests`: SUCCESS on Python 3.12;
- fixture branch `agent/a5-fixture-green-pr` changed one file under `fixtures/a5/`;
- fixture PR #4 `foundation/unit-tests`: SUCCESS;
- PR #3 and PR #4 remain open, mergeable, and unmerged.

## A6 — Validator registry

Standardize validation plugins:

- tests/build/type/lint;
- schema/contract checks;
- immutable-source checks;
- deterministic rerun checks;
- forbidden-path/diff-risk checks;
- CI status aggregation.

Exit criteria: an LLM explanation cannot override a failing validator.

## A7 — Public ST domain adapters

Add read/analysis adapters first for public specialist repositories such as:

- ST Score Restore;
- ST OMR Correction;
- MusicXML to Guitar TAB;
- ST Guitar Harmonic Engine;
- ST Score Editor Core;
- ST Score Rendering Layer.

Write authority is opt-in per repository and task, not global.

Exit criteria: one cross-repository diagnostic task completes without mutating the target repository.

## A8 — Controlled cross-repository engineering

Permit branch/PR work on an explicit allowlist:

- one repository at a time;
- exact base SHA;
- bounded paths;
- repository-owned tests and governance remain authoritative;
- no production deployment or automatic merge.

Exit criteria: at least two representative repositories complete green PR workflows with no safety-policy exceptions.

## A9 — Agent benchmark suite

Create fixed tasks measuring:

- task completion rate;
- validator pass rate;
- regression rate;
- unsafe-action rejection rate;
- unnecessary tool calls/retries;
- cost/time metadata when available;
- abstention quality.

Keep benchmark labels and acceptance policy outside agent write authority.

## A10 — Bounded self-improvement

Allow the agent to propose changes to its own prompts, router, adapters, and code only through candidate branches. Compare against the unchanged benchmark and safety suite.

No automatic threshold lowering, benchmark rewriting, or self-merging.

## A11 — Product integration research

Only after the lab is stable:

- evaluate private/product adapters through local configuration;
- define authenticated execution and tenancy boundaries;
- define teacher/product authority handoff;
- define observability and incident recovery;
- decide whether a production `ST Music Agent Core` should be extracted from the lab.

This stage requires a separate production/security decision and is not implied by successful lab experiments.
