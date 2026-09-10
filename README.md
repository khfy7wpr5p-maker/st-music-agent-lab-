# ST Music Agent Lab

Isolated research and engineering lab for a policy-gated AI agent that can inspect, test, validate, and later coordinate bounded development work across ST music software.

## Current status

**A0 — Architecture baseline / active development.**

No production deployment, automatic merge, private-data access, or unrestricted cross-repository write authority is enabled.

## Core architecture

```text
Human task
  -> TaskSpec
  -> Planner / Router
  -> OpenManus Adapter
  -> ST Capability + Policy Gate
  -> Execution Coordinator
       -> GitHub Adapter
       -> Sandbox Runner
       -> Research Adapter
       -> Domain Adapter Registry
  -> Independent Validator Registry
  -> Run Ledger
  -> Branch / Commit / PR
  -> CI
  -> MERGE_READY
  -> Human merge gate
```

OpenManus is intentionally a **replaceable external agent-framework adapter**. ST-owned policy, task, validation, audit, and authority contracts remain outside the framework.

## Initial public domain targets

The lab is designed to integrate gradually with specialist ST repositories rather than reimplement their logic:

- ST Score Restore Engine;
- ST OMR Correction Engine;
- MusicXML to Guitar TAB Engine;
- ST Guitar Harmonic Engine;
- ST Score Editor Core;
- ST Score Rendering Layer.

Private/product repositories can be connected later through local allowlisted configuration without committing private repository configuration or credentials here.

## Non-goals

The Agent Lab is not:

- a canonical score authority;
- an OMR engine;
- a restoration engine;
- a TAB solver;
- a score renderer;
- a teacher-approval authority;
- a production deployment authority;
- an autonomous self-merging system.

## Safety baseline

- default authority is read-only;
- default-branch writes and force-push are forbidden;
- merge requires a human gate by default;
- validators cannot be overridden by an LLM explanation;
- uncertainty may produce `NEEDS_REVIEW`, `BLOCKED`, or `ABSTAINED` rather than a fabricated success;
- API keys, tokens, credentials, private/student data, and local runtime state must not be committed;
- self-improvement, when added, must use candidate branches plus fixed external benchmarks and safety regression tests.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system map, layers, domain boundaries, GitHub flow, and self-improvement design;
- [`docs/SAFETY.md`](docs/SAFETY.md) — allowed, gated, and forbidden operations;
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — A0–A11 development sequence;
- [`contracts/AGENT_AUTHORITY_V0.json`](contracts/AGENT_AUTHORITY_V0.json) — machine-readable authority baseline.

## Next development target

**A1 — Minimal Python foundation:** implement `TaskSpec`, capability/policy evaluation, run-state/result schema, and a structured run ledger with deterministic unit tests. No OpenManus or network side effect should be required to pass A1.
