# APP6 — Validator Health, Review Resolution and Audit Export

APP6 hardens the APP5 evidence plane without adding merge or production authority.

## Validator health and freshness

Every explicit evidence refresh still runs exact-SHA CI and the generic/project-specific validator
set. APP6 then records one `VALIDATOR_HEALTH_SNAPSHOT` bound to the exact `VALIDATOR_SNAPSHOT` event
sequence/hash.

Health states are:

- `HEALTHY` — all validators are PASS and bound to the exact task HEAD;
- `DEGRADED` — at least one validator is UNAVAILABLE or evidence is incomplete;
- `UNHEALTHY` — a validator FAILs or commit binding is wrong.

The snapshot has `checked_at`, `expires_at`, source event identity and validator names. The current
freshness window is 900 seconds (15 minutes).

Freshness is an operational gate, not history rewriting. An expired health snapshot does not erase a
previous `VERIFIED_SUCCESS`. It does prevent a new PR-open action until evidence is explicitly
refreshed and returns `FRESH_HEALTHY`.

## Review-thread resolution

APP5 deliberately left thread resolution as `unavailable` because the REST evidence used there does
not expose a trustworthy resolution bit. APP6 adds a narrow GitHub GraphQL read for
`PullRequest.reviewThreads.isResolved` when the configured API is `https://api.github.com` and the
host credential can perform the query.

The adapter is bounded to 100 threads and 20 comments per thread for root-comment identity. If the
GraphQL page would exceed the bound, the overall resolution surface is treated as incomplete. If the
query is unavailable or errors, APP6 keeps resolution explicitly unavailable rather than inferring it
from comment text, review state, age or author.

APP6 remains read-only with respect to review threads: it does not resolve, unresolve, dismiss or
approve anything.

## Audit export

`GET /api/tasks/audit/<task_id>` produces a derived JSON audit bundle. It includes:

- task/project/repository identity;
- base/feature branch and exact commit identities;
- instruction fingerprint, not raw hidden reasoning;
- changed paths;
- CI and validator evidence;
- current validator health/freshness;
- review digest and acknowledgement status;
- PR head/base review evidence;
- bounded PR collaboration summary;
- retry/amend lineage;
- up to 500 journal event headers containing event, sequence, timestamp, record hash and previous hash;
- journal anchor sequence/hash;
- deterministic `audit_sha256` for the exported bundle.

The audit export intentionally omits raw provider chain-of-thought, credentials and raw PR comment
bodies. APP5 already persists comment body hashes/character counts rather than comment text.

## Stage and authority boundaries

APP6 does not add a task stage. It adds the append-only evidence event:

```text
VALIDATOR_HEALTH_SNAPSHOT
```

APP6 does not expose model-callable or HTTP actions for:

- merge or auto-merge;
- direct protected-branch writes;
- PR approval;
- review-thread resolution/dismissal;
- deployment/release;
- training/activation/canonicalization;
- rollback execution.

Audit, review and health evidence are decision support only. They are not production authorization or
music-domain truth beyond the project-specific contracts they explicitly validate.
