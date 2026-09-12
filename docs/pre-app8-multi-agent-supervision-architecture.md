# Pre-APP8 — Multi-Agent Supervision Architecture

Status: design only; no APP8 runtime capability is enabled by this document.
Date: 2026-09-12
Base: APP7 / main `18f3010415026b51df20093c201c29650f334196`

Legend:

- 🌐 implemented and verified in the current repository;
- 🕸️ proposed / not implemented;
- 🔒 intentionally outside autonomous agent authority.

## Why APP8 is justified

The repository already contains strong single-agent execution confinement, deterministic portfolio planning,
verified execution outcomes, advisory experience learning, lifecycle orchestration, operational drift/rollback
state, APP3–APP7 task evidence, exact-SHA CI/validators, audit export and deterministic replay.

The missing layer is not another lifecycle state machine. The missing layer is a runtime supervision plane
that can decompose one bounded engineering objective into multiple evidence-bound sub-tasks, assign them to
specialized agents/models, enforce dependency ordering, compare independent results, detect disagreement,
measure reliability, and stop or escalate without acquiring merge/production authority.

Current `DirectAgentRunner` executes one routed model for one task. `ToolLoopRunner` safely constrains one
agent/tool loop. `CrossProjectPlanner` produces deterministic project candidates but explicitly does not
authorize execution. `ExecutionOutcomeStore` and `ExperienceStore` record verified outcomes after the fact.
These are strong prerequisites, but they are not a multi-agent supervisor.

## Existing foundation

```text
🌐 ModelRouter
   -> capability-based model selection

🌐 DirectAgentRunner / ToolLoopRunner
   -> one bounded agent execution
   -> run budgets
   -> tool registry
   -> journal evidence

🌐 CrossProjectPlanner + Verifier
   -> deterministic project-level plan
   -> execution_authorized = false

🌐 APP2–APP7 guarded task system
   -> feature-branch confinement
   -> exact commit SHA
   -> exact-SHA CI / validators
   -> exact review acknowledgement
   -> PR binding
   -> validator health/freshness
   -> audit export / replay

🌐 ExecutionOutcomeStore / ExperienceStore
   -> verified historical outcomes
   -> non-binding recommendations

🌐 A1–A26 lifecycle core
   -> training / activation / canonical / rollback boundaries
```

## Proposed APP8 scope

APP8 should be a **Bounded Multi-Agent Supervisor**, not an autonomous production controller.

```text
Operator objective
      ↓
🕸️ Objective Contract
      ↓
🕸️ Dependency DAG Planner
      ↓
🕸️ Independent Plan Verifier
      ↓
🕸️ Supervisor Scheduler
      ├── 🕸️ Research / Evidence Agent
      ├── 🕸️ Implementation Agent
      ├── 🕸️ Test / Validation Agent
      └── 🕸️ Critic / Verification Agent
      ↓
🕸️ Evidence-bound subtask results
      ↓
🕸️ Disagreement / anomaly detector
      ↓
🕸️ Supervisor decision
      ├── continue safe reversible work
      ├── retry as immutable child task
      ├── request independent verification
      ├── abstain / REVIEW_REQUIRED
      └── escalate to human boundary
      ↓
🌐 Existing APP3–APP7 exact-SHA / CI / review / audit pipeline
```

## APP8 components

### 🕸️ APP8.1 Objective Contract

A top-level objective must be converted into a bounded, immutable contract containing:

- objective id and fingerprint;
- target project/repository set;
- allowed change classes;
- explicitly forbidden actions;
- success evidence requirements;
- maximum agent count;
- total model/tool/time budget;
- human gates;
- stop conditions.

The objective contract cannot grant merge, deployment, production activation, training, canonicalization or
rollback authority.

### 🕸️ APP8.2 Dependency DAG

Create an acyclic graph of sub-tasks. Each node has:

- stable node id;
- role type;
- immutable instruction fingerprint;
- parent objective id;
- dependencies;
- repository / branch scope;
- input evidence refs;
- expected output evidence;
- budget;
- mutation class (`read_only`, `reversible_feature_branch`, or `human_gated`);
- completion / abstention criteria.

A node may run only after its dependencies have produced the exact required evidence.

### 🕸️ APP8.3 Specialized Agent Roles

Roles are capabilities, not unrestricted identities.

**Evidence Agent**
- read-only;
- gathers repository/project evidence;
- cannot mutate code.

**Implementation Agent**
- may use only existing feature-branch-safe write tools;
- branch remains host-bound;
- cannot open/approve/merge PRs autonomously.

**Validation Agent**
- evaluates exact task HEAD / artifacts;
- independent from implementation result where practical;
- cannot rewrite implementation evidence.

**Critic Agent**
- compares plan, implementation evidence, validator results and constraints;
- emits `PASS`, `REVIEW_REQUIRED`, `FAIL`, or `ABSTAIN` with evidence refs;
- cannot perform corrective mutations itself unless a new bounded child task is created.

### 🕸️ APP8.4 Supervisor Scheduler

The supervisor is deterministic host logic, not a privileged model.

It may:

- schedule ready DAG nodes;
- select a compatible model through `ModelRouter`;
- enforce per-node and global run budgets;
- stop execution on failed invariants;
- create immutable retry/revision requests;
- request a second independent verification;
- surface unresolved dependencies to the operator.

It may not:

- widen its own tool permissions;
- choose a protected branch;
- bypass existing APP review/freshness gates;
- infer `PASS` from agent prose;
- merge or deploy.

### 🕸️ APP8.5 Independent Critic / Disagreement Gate

For state-widening decisions, the same model response should not be both producer and sole verifier.

Minimum rule:

```text
implementation evidence
      +
exact CI / validator evidence
      +
independent critic recomputation
      ↓
consensus only if deterministic invariants agree
```

Disagreement must produce `REVIEW_REQUIRED` or `ABSTAIN`, never optimistic auto-resolution.

### 🕸️ APP8.6 Reliability Metrics

APP8 should measure agents separately from product correctness.

Per role/model/project:

- task success rate;
- validator failure rate;
- abstention rate;
- retry count;
- stale-evidence attempts;
- policy-denied tool calls;
- disagreement rate;
- human override rate;
- exact-SHA mismatch rate;
- mean model turns/tool calls;
- budget exhaustion rate;
- regression escape rate where later evidence exists.

Metrics are advisory and cannot automatically grant broader privileges.

### 🕸️ APP8.7 Cross-project dependency coordination

The current portfolio planner ranks four projects but does not execute a dependency graph. APP8 may represent
explicit cross-project edges, for example:

```text
Score Restore evidence
   -> Score Editor import/render verification
   -> Guitar TAB capability check
   -> optional Score Following research fixture
```

A cross-project dependency must bind to exact source refs/SHAs and must not convert research or reviewable
output into production authority.

### 🕸️ APP8.8 Long-running supervision state

Long jobs need resumable host state distinct from model memory:

- objective state;
- DAG node state;
- exact evidence refs;
- heartbeat / last-progress timestamp;
- retry lineage;
- blocked reason;
- human-gate reason;
- budget snapshot;
- final supervisor disposition.

State should use the existing append-only/hash-chained evidence pattern.

### 🕸️ APP8.9 Operator UX

APP8 UI should show the task graph rather than a long chat transcript.

Minimum operator view:

- objective;
- DAG nodes and dependencies;
- agent role/model used per node;
- current state (`READY`, `RUNNING`, `PASS`, `FAIL`, `ABSTAIN`, `BLOCKED`, `REVIEW_REQUIRED`);
- exact evidence refs;
- budget use;
- disagreement / critic status;
- human action required;
- audit export.

Remote APP7 mode remains read-only.

## Recommended implementation sequence

Do not implement all APP8 scope in one PR.

```text
🕸️ APP8A — Supervisor contracts + DAG + deterministic scheduler (read-only simulation first)
      ↓
🕸️ APP8B — Reliability metrics + independent critic / disagreement gate
      ↓
🕸️ APP8C — Reversible feature-branch multi-agent execution using existing APP2–APP7 gates
      ↓
🕸️ APP8D — Cross-project dependency coordination
      ↓
🕸️ APP8E — Operator graph UI + resumable supervision/audit
```

### APP8A acceptance boundary

APP8A should initially **not write code to repositories**. It should prove that:

1. objective contracts are canonical and fingerprinted;
2. DAG cycles and unknown dependencies are rejected;
3. only dependency-ready nodes can be scheduled;
4. role capabilities are fixed by host policy;
5. model routing is capability-bound;
6. global/node budgets fail closed;
7. state can be replayed deterministically;
8. no scheduler output authorizes merge/production actions.

Only after this is green should APP8C reuse existing feature-branch mutations.

## Explicit authority boundary

The following remain 🔒 outside APP8 autonomous authority:

- protected-branch writes;
- PR approval;
- merge / auto-merge;
- review-thread mutation as an authority shortcut;
- release/deployment;
- training execution unless separately host-authorized by the existing lifecycle contract;
- production model activation;
- canonicalization;
- destructive rollback execution;
- privilege/tool-policy self-modification;
- secret/credential mutation.

## Full architecture position

```text
🌐 A1–A26 Guarded Core
        ↓
🌐 APP1–APP7 Guarded Operator / Execution / Evidence / Audit
        ↓
🕸️ APP8 Bounded Multi-Agent Supervisor
        ├── 🕸️ objective contract
        ├── 🕸️ dependency DAG
        ├── 🕸️ specialist roles
        ├── 🕸️ deterministic scheduler
        ├── 🕸️ independent critic
        ├── 🕸️ reliability metrics
        ├── 🕸️ cross-project coordination
        └── 🕸️ resumable supervision UI/state
        ↓
🔒 Human / host production authority
```

## Decision

The recommended next executable engineering step is **APP8A only**. APP8A should be a non-mutating supervisor
simulation and contract layer. This gives the architecture a measurable multi-agent foundation without exposing
new repository or production authority.