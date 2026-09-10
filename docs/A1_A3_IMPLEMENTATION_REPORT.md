# A1–A3 Implementation Report

Date: 2026-09-10
Branch: `architecture/openmanus-agent-foundation-v0`

## Result

A1, the bounded A2 adapter foundation, and A3 are implemented on the architecture branch without enabling production authority, default-branch mutation, automatic merge, secrets, private/student data, or unrestricted OpenManus tools.

## A1 — Minimal Python foundation

Implemented:

- typed `TaskSpec` and `AuthorityMode`;
- typed action/capability model;
- framework-independent `PolicyEngine`;
- hard denials that remain denied even if a task attempts to self-grant them;
- non-default-branch enforcement for repository mutation actions;
- writable-path boundaries;
- `RunState` and structured `RunLedger`;
- ledger explicitly stores action/evidence summaries rather than hidden reasoning.

## A2 — OpenManus adapter foundation

Pinned upstream identity:

- repository: `FoundationAgents/OpenManus`;
- revision: `3309bf4e416fb1c74b008f3e86494439a31bad53`.

Implemented:

- replaceable planning-backend protocol;
- `TaskSpec` -> bounded prompt translation;
- exposed-action filtering;
- every proposed action is independently re-evaluated by `PolicyEngine`;
- fixture backend proves a planner cannot make `force_push` admissible by proposing it.

Live upstream `Manus` execution remains intentionally disabled. At the pinned revision, upstream `Manus` includes executable Python and file-editing tools in its default tool collection. Enabling raw `Manus` now would bypass the ST-owned execution boundary. A later mediated ST tool bridge must replace those unrestricted tools before live activation.

This is a deliberate safety boundary, not an implementation failure.

## A3 — Bounded sandbox executor

Implemented:

- explicit TaskSpec command grant;
- bounded test-command prefixes for Python unittest/pytest and Node test runner;
- `shell=False` execution;
- timeout budget;
- retry-attempt budget;
- sanitized environment;
- stdout/stderr capture;
- output-size limit;
- caller-provided secret redaction;
- arbitrary `python -c` rejection;
- non-granted command rejection.

Current A3 does not claim container/VM isolation or hostile untrusted-code containment. It is a bounded subprocess test runner for lab fixtures. Strong OS/container isolation is a later hardening requirement before untrusted repository execution.

## Validation

Local verification command:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Observed result before repository write:

```text
Ran 12 tests
OK
```

Coverage includes:

1. bounded sandbox permission in READ_ONLY mode;
2. ungranted action denial;
3. default-branch write denial;
4. hard denial cannot be self-granted;
5. path-bound write admission/denial;
6. structured run-ledger finalization;
7. OpenManus adapter policy mediation;
8. Python unittest fixture execution;
9. arbitrary Python command rejection;
10. non-granted command rejection;
11. retry-budget enforcement;
12. secret redaction.

## Authority after A3

Still disabled:

- raw OpenManus runtime execution;
- GitHub read adapter (A4);
- branch/commit/PR automation (A5);
- automatic merge;
- production deployment;
- private/student data;
- teacher approval;
- training-data admission or model promotion.

## Next boundary

A4 should add a read-only GitHub adapter and a fixture diagnosis flow. It must reuse `TaskSpec`, `PolicyEngine`, `RunLedger`, and the bounded sandbox rather than giving the agent direct GitHub credentials or tool authority.
