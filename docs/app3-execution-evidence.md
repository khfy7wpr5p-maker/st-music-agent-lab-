# APP3 — Execution Evidence, CI/Validator and PR Review

APP3 turns guarded APP2 feature-branch work into a durable operator workflow without adding merge or
production authority.

## What is persisted

The host-owned task journal stores only structured public task metadata and bounded execution evidence:

- task id and attempt;
- project and repository;
- base branch/base SHA;
- deterministic feature branch;
- instruction fingerprint, not the raw instruction;
- stage and public outcome;
- exact task HEAD SHA;
- changed file paths and bounded diff statistics;
- CI run ids/status/conclusion for the exact task SHA;
- typed validator results;
- PR number and bounded PR metadata when explicitly opened.

It does not store hidden model reasoning, chain-of-thought, provider payloads, API keys or raw
credentials.

## Journal integrity

Each JSONL record contains the previous record hash and its own SHA-256 hash. New state is appended;
prior evidence is not replaced. The store verifies the chain when it is reopened. Invalid stage
transitions fail closed.

Default path:

```text
~/.st-music-agent/task-events.jsonl
```

Override with:

```bash
st-music-agent app --task-state-file /safe/local/path/task-events.jsonl
```

or `ST_MUSIC_AGENT_TASK_STATE`.

## CI behavior

APP3 does not run a core background polling loop. The browser/host explicitly requests evidence
refresh. GitHub workflow evidence must match the exact task HEAD SHA. A run from another commit is
ignored for verification.

State rules:

- no exact-SHA run yet -> pending;
- any selected run still queued/in progress -> pending;
- all selected runs completed successfully -> CI success;
- any completed selected run not successful -> CI failure;
- GitHub evidence unavailable -> unavailable/review required, never success.

When a project profile does not declare required workflow names, all exact-SHA runs returned for the
task are reviewed. Profiles may name workflows only when those workflows really exist.

## Validator behavior

Each validator result carries:

```text
name
status: PASS | FAIL | UNAVAILABLE
evidence_reference
exact commit SHA
bounded message
```

APP3 generic validators cover exact branch/head binding and bounded compare evidence. A configured
validator with no host adapter returns `UNAVAILABLE`; it does not become `PASS` merely because generic
CI succeeded.

## Verified success

`VERIFIED_SUCCESS` requires:

1. exact repository/feature-branch identity;
2. a final feature-branch HEAD different from the preview base;
3. bounded compare evidence for that exact base/head pair;
4. successful required exact-SHA CI evidence;
5. all configured validators at `PASS`.

This is an engineering task result only. It does not authorize merge, release, deployment, musical
correctness, training, model promotion, activation, canonicalization or rollback.

## PR flow

PR opening is an explicit human/host click and is rejected before `VERIFIED_SUCCESS`. APP3 rechecks
that the feature branch still resolves to the verified HEAD before the mutation. It then reads PR
metadata back and validates the expected head ref/head SHA/base ref before recording `PR_OPENED`.

There is no merge endpoint and the model receives no merge tool.

## Restart/resume

Task status, commit evidence, CI snapshots, validators and PR state survive local app restart because
they are reconstructed from the journal. Raw user instructions are deliberately not persisted. If an
interrupted task still needs model execution, the operator re-previews the same instruction; the
deterministic task identity and instruction fingerprint bind it back to the existing task before
execution resumes.
