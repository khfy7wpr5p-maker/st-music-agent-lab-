# APP8A — Bounded Supervisor Contracts and Simulation

Status: implemented as a non-mutating simulation layer.

APP8A is the first executable part of the bounded multi-agent supervision architecture. It does not call a model, dispatch a tool, mutate a repository, open or approve a PR, merge, deploy, train, activate, canonicalize, or roll back anything. It proves the supervision contracts and scheduling invariants before APP8C is allowed to reuse feature-branch mutation capabilities.

## Implemented components

`src/st_music_agent/app8_supervision.py` provides:

- canonical `ObjectiveContract` fingerprints;
- fixed host `AgentRole` capability policy for evidence, implementation, validation, and critic roles;
- immutable `SubtaskNode` instruction and node fingerprints;
- explicit mutation classes: `read_only`, `reversible_feature_branch`, and `human_gated`;
- validated dependency DAGs with unknown-dependency and cycle rejection;
- explicit dependency-evidence flow declarations;
- protected-branch rejection for reversible-write nodes;
- per-node and global budget envelopes that fail closed;
- capability-bound model selection through the existing `ModelRouter`;
- deterministic one-node-at-a-time scheduler simulation;
- event-derived replay with deterministic replay fingerprints;
- `PASS`, `FAIL`, `ABSTAIN`, and `REVIEW_REQUIRED` result states;
- human-gated nodes that are visible but never autonomously scheduled.

## Model strategy

APP8A does not hard-code provider calls. A node is converted to the existing `AgentTask` contract and routed by `ModelRouter`. The current catalog can therefore select GLM-5.1, Qwen3.8, or Kimi-K2.5 according to declared task capabilities and context/vision needs. Future OpenAI-compatible providers, including a separately configured DeepSeek endpoint, can be added without changing the supervisor authority model.

A routing decision is only a simulation record in APP8A. It does not invoke the selected model.

## Authority boundary

Every objective, graph, schedule decision, and replay keeps these flags false:

```text
execution_authorized = false
repository_mutation_authorized = false
merge_authorized = false
production_actions_authorized = false
```

Critical actions are forcibly present in the objective's forbidden-action set, including protected-branch writes, PR approval, merge/auto-merge, deployment/release, training execution, production activation, canonicalization, rollback execution, privilege self-modification, and secret mutation.

An implementation-role node may declare `reversible_feature_branch` so the future APP8C graph can be modeled accurately, but APP8A still performs no repository mutation.

## Deterministic scheduling and replay

A node becomes `READY` only when all dependencies are `PASS` and their expected evidence references are present. Non-PASS upstream outcomes block descendants. Scheduler order is deterministic by stable node id. At most one simulated node is `RUNNING` at a time in APP8A.

Scheduling reserves the node's entire declared budget against the objective budget. If the next reservation would exceed any global dimension, scheduling fails closed. This is intentionally conservative; APP8B/C may later add measured consumption while preserving the same hard ceiling.

Replay accepts the graph plus an ordered event sequence and reconstructs node state, model identity, evidence, reserved budget, and final supervisor disposition. Out-of-order scheduling, missing PASS evidence, non-contiguous events, and human-gated autonomous scheduling are rejected.

## Tests

`tests/test_app8_supervision.py` covers:

- deterministic objective fingerprints and forced production boundaries;
- unknown dependency and cycle rejection;
- explicit dependency evidence flow;
- fixed role capability policy;
- protected branch write rejection;
- dependency-ordered scheduling;
- capability-based GLM/Qwen routing;
- simulation-only authority flags;
- expected evidence requirements for PASS;
- REVIEW_REQUIRED propagation and descendant blocking;
- human-gated scheduling confinement;
- global budget exhaustion;
- deterministic replay and illegal ordering rejection;
- full four-role simulation to `COMPLETE` without authority widening.

## Next boundary

APP8B may add reliability metrics plus an independent critic/disagreement gate. APP8B must remain non-mutating unless a later, separately reviewed APP8C explicitly reuses the existing APP2–APP7 feature-branch execution gates.
