# APP7 — Audit Verification, Deterministic Replay and Remote Read-Only Operator

APP7 adds stronger audit inspection and a separately threat-modeled remote operator mode. It does not
add merge, deployment, training, activation, canonicalization or rollback authority.

## Audit verification levels

APP7 deliberately separates two verification claims.

### 1. Export digest and structure verification

`verify_audit_export()` checks:

- supported audit schema;
- `audit_sha256` against canonical JSON content excluding the digest field itself;
- journal event/export counts;
- exported last-event identity against the exported anchor sequence/hash;
- basic SHA-256 anchor shape;
- `merge_authorized: false`;
- `production_actions_authorized: false`.

This verifies that the exported JSON is internally consistent and has not been modified after its
`audit_sha256` was computed. It does **not** prove which journal produced the JSON. The result therefore
sets `source_journal_authenticated: false`.

### 2. Local journal verification + deterministic replay

`App7TaskService.verify_current_audit()` creates the current audit and compares it with the real local
`TaskEventStore`:

- audit anchor sequence must equal the latest task journal record sequence;
- audit anchor hash must equal the latest task journal record hash;
- deterministic replayed stage must equal the audit stage;
- deterministic replayed outcome must equal the audit outcome;
- the underlying `TaskEventStore` has already validated the global append-only SHA-256 hash chain when
  it loaded the journal.

`replay_task()` walks the task's recorded events without executing external actions. It validates the
allowed APP3 stage-transition graph and recomputes a replay digest over task event headers and derived
state.

Replay never reruns:

- the model/provider;
- GitHub mutations;
- CI workflows;
- validators against external repositories;
- review mutations;
- deployment/release;
- training/activation/canonicalization;
- rollback.

It is evidence replay, not execution replay.

## Read-only audit endpoints

```text
GET /api/tasks/audit/<task_id>
GET /api/tasks/audit-verify/<task_id>
GET /api/tasks/replay/<task_id>
```

These endpoints do not widen task state.

## Remote operator threat model

APP7 remote mode exists for viewing project/task evidence from another device without turning the ST
Music Agent into a remotely writable control plane.

### Assets to protect

- task journal and engineering evidence;
- repository/project evidence visible through the operator console;
- GitHub/provider credentials held by trusted adapters;
- local write session token;
- protected-branch / PR / production authority boundaries.

### Primary threats

- accidental public exposure of the local console;
- unauthorized remote reads;
- remote mutation through inherited POST endpoints;
- bearer-token capture on plaintext transport;
- leaking the local write-session token to a remote browser;
- using audit/review metadata as implicit merge or production authority.

### Controls

Remote mode is enabled only with `--remote-read-only` and a bearer token supplied by environment
variable name. The token must be at least 24 characters. The application stores only its SHA-256
digest for request comparison and uses constant-time digest comparison.

In remote mode:

- `/` and `/api/remote-mode` are the only unauthenticated surfaces; they expose the login shell and
  capability metadata only;
- all evidence/data endpoints require `Authorization: Bearer ...`;
- `/api/session` returns no write-session token;
- all non-GET requests return `405 remote_read_only` before inherited mutation handlers run;
- `TaskExecutionConfig.enabled` must be false;
- merge/auto-merge remains absent;
- review-thread mutation remains absent;
- production lifecycle actions remain absent.

The browser keeps the bearer token in `sessionStorage`, not persistent `localStorage`.

## Network boundary

The built-in `ThreadingHTTPServer` does not implement TLS. APP7 therefore fails closed for non-loopback
binding unless remote read-only mode is active **and** the operator explicitly supplies
`--remote-secure-transport-attested`.

That flag is a human assertion, not transport detection. It should be used only when an actual secure
boundary already exists, such as:

- SSH port forwarding;
- an authenticated private VPN/tunnel;
- a TLS reverse proxy with appropriate access controls.

The preferred deployment remains loopback binding with a secure tunnel terminating locally. Direct
public-internet exposure of the built-in HTTP listener is outside the APP7 threat model and should not
be used.

## Authority boundary

Neither successful audit verification nor successful journal replay means:

- musical correctness;
- merge approval;
- release readiness;
- production activation approval;
- rollback authorization.

APP7 adds observability and verification, not self-authority.
