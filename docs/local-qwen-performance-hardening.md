# Local Qwen Planner Performance Hardening

Status: feature-branch hardening after bounded P7 smoke
Date: 2026-09-13

## Observed smoke boundary

The single P7 local smoke used `qwen3:1.7b` through Ollama on a CPU-only Codespace. The task reached
`PREVIEWED -> BRANCH_CREATED -> AGENT_RUNNING` and then the provider request exceeded the practical
request window. No `PLAN_VALIDATED`, executor checkpoint, repository write, commit, pull request or
merge followed from that attempt.

The Ollama log showed that a roughly 2k-token selection prompt spent most of the request budget in
prompt evaluation. The failure was therefore treated as a local inference/performance boundary, not as
permission to restore the previous recursive model tool loop.

## Hardening applied

The deterministic execution path now uses `CompactSmallModelPlanner`.

Before the first model call, the host ranks the already bounded repository candidates against the task
instruction and sends at most 96 path strings. Full blob SHA and file-size metadata are omitted from
this selection prompt. Explicit path mentions receive the strongest deterministic rank; filename and
path token matches follow. Common project entry files receive only a small fallback preference.

The second planning prompt is also compacted while retaining the same strict host parser contract:

- exact repository;
- exact base SHA;
- exact feature branch;
- maximum three changes;
- create/update only;
- exact blob SHA for updates;
- complete replacement content;
- no write, shell, PR or merge authority for the model.

Host validation remains authoritative. Prompt compaction does not relax branch, path, credential,
control-plane, stale-blob, read-evidence or read-back checks.

## Failure persistence

Provider and transport exceptions now fail the deterministic task closed. A timeout or unexpected
provider exception records `PLANNER_FAILURE`, transitions the task to `FAILED`, and prevents a stale
`AGENT_RUNNING` task from being presented as ongoing work.

The same fail-closed rule is applied to unexpected host executor adapter exceptions.

## Added regression coverage

New tests cover:

- deterministic candidate ranking and the 96-path prompt cap;
- two tool-free planner calls after prompt compaction;
- strict plan parsing after compact prompts;
- provider timeout persistence as `PLANNER_FAILURE` + terminal `FAILED`;
- absence of mutation after provider timeout.

## Authority boundary

This hardening does not authorize automatic PR creation, approval, merge, deployment, release,
training, activation, canonicalization, rollback, credential mutation or direct protected-branch
writes. `main` remains outside autonomous mutation authority.
