# APP4 — Exact Review, Retry/Amend Lineage and PR Review Evidence

APP4 extends APP3 without widening mutation, merge or production authority.

## Exact diff review

APP4 reads a bounded GitHub compare for the exact APP3 base SHA and task HEAD SHA. The operator view
shows each changed path, status, additions/deletions, deterministic attention level and a bounded patch.

The host computes a SHA-256 digest from exact commit identity and per-file patch digests/statistics. The
journal persists only bounded review evidence and the digest; it does not persist hidden model
reasoning, provider payloads, API keys or raw credentials.

A review is marked incomplete when GitHub does not expose a textual patch or when the configured
per-file/total display limits would truncate it. Incomplete review evidence cannot be acknowledged and
therefore cannot open a PR through APP4.

## Human review acknowledgement

PR creation now requires all APP3 requirements plus one extra human boundary:

```text
VERIFIED_SUCCESS
  -> exact diff review loaded for the same task HEAD
  -> review is complete
  -> human explicitly acknowledges the exact review_digest
  -> feature branch is rechecked at the same HEAD
  -> human explicitly opens PR
```

The acknowledgement is append-only and bound to both `review_digest` and exact `head_sha`. If the
branch moves, the acknowledgement becomes stale and PR creation is rejected.

Review acknowledgement is not merge approval and does not authorize deployment, release, training,
activation, canonicalization or rollback.

## Retry and amend

APP4 does not rewrite failed or completed task history. A retry/amend creates a separate deterministic
child task and appends lineage evidence to both parent and child.

- `retry` is accepted only for a `FAILED` parent task.
- `amend` requires an exact parent commit so the correction has concrete evidence to refer to.
- the parent stage/outcome/evidence remains immutable;
- the child receives a new task identity and new bounded feature branch through the existing APP3
  preview/run path;
- lineage records include parent task id, mode, revision number and parent HEAD when available.

This keeps failed attempts visible instead of silently converting them into successful history.

## PR review evidence

After a PR is opened, APP4 stores a `PR_REVIEW_SNAPSHOT` that binds:

- task HEAD SHA;
- acknowledged review digest;
- PR number;
- PR head SHA and base SHA;
- draft/mergeable metadata when available;
- exact-head-match flag.

The operator may explicitly refresh this metadata. If the PR head/base no longer matches the verified
task evidence, refresh fails closed.

## Bounded review limits

Current APP4 limits are intentionally conservative:

- maximum 100 changed files in review projection;
- maximum 16,000 displayed patch characters per file;
- maximum 160,000 displayed patch characters across the review.

Crossing a patch display boundary does not silently approve less evidence; it marks the review
incomplete and blocks acknowledgement.

## Authority boundary retained

APP4 still exposes no model-callable or HTTP merge endpoint. The model cannot select `main`/`master`,
open a PR itself, deploy, train, activate, canonicalize or execute rollback. Protected/destructive and
production actions remain outside APP4 and require their existing host/human boundaries.
