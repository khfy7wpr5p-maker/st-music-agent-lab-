# ST Music Agent Lab — Roadmap

## A0 — Architecture baseline

Status: ACTIVE in `architecture/openmanus-agent-foundation-v0`.

Goals:
- define the lab's purpose and non-goals;
- keep OpenManus replaceable behind an adapter;
- define capability, validation, GitHub, and human-approval boundaries;
- define safe future self-improvement rules.

Exit criteria:
- architecture, safety, roadmap, and machine-readable authority contract reviewed;
- no production or cross-repository write authority activated.

## A1 — Minimal Python foundation

Create a small ST-owned package before integrating OpenManus:

- `TaskSpec` schema;
- capability enum and policy engine;
- run state/result schema;
- structured run ledger;
- unit tests for allowed/denied actions;
- no network side effects.

Exit criteria: deterministic policy tests pass and direct default-branch mutation is impossible through the core API.

## A2 — OpenManus adapter

Integrate OpenManus as an external/replaceable backend:

- pin an exact tested upstream revision or package identity;
- isolate provider configuration from ST policy;
- translate ST `TaskSpec` into bounded agent input;
- translate tool/action requests back through the ST policy gate;
- do not expose unrestricted tools by default.

Exit criteria: agent can plan a local fixture task without bypassing the ST gate.

## A3 — Sandbox executor

Add bounded command execution:

- temporary workspace;
- command allowlist / resource limits;
- stdout/stderr capture;
- timeout and retry budget;
- no secret echoing;
- Python/Node test command support.

Exit criteria: fixture repository tests can run and produce a deterministic ledger.

## A4 — GitHub read-only adapter

Add repository inspection capabilities:

- repo/branch/commit/file metadata;
- PR/CI/status reads;
- diff inspection;
- required-check evidence;
- no writes.

Exit criteria: agent can diagnose a prepared failing fixture PR and produce a cited root-cause report.

## A5 — Lab-only branch/PR writer

Allow controlled mutations only in this repository:

- task branch creation;
- bounded file updates;
- commits;
- PR creation;
- CI repair loop with retry cap;
- no merge authority.

Exit criteria: agent completes one fixture change from task to green PR while preserving branch restrictions.

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
