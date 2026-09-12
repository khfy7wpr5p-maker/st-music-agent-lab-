# APP8E — Persistent operator graph

Status: persistent, read-only APP8 supervision/coordination observability and deterministic resume state.

APP8E closes the current bounded multi-agent supervision architecture by making APP8A–APP8D graph state durable across process restarts without introducing a new execution authority.

## Persistent graph journal

`App8GraphStore` writes an append-only JSONL journal. Every record contains:

- global sequence number
- UTC timestamp
- graph id and graph kind
- record type
- bounded payload
- previous-record SHA-256
- current record SHA-256

The journal is fsync'd after each append and fully validates schema, global sequence, hash chain, graph registration order, and per-graph event sequence when reopened.

Default path:

`~/.st-music-agent/app8-graph-events.jsonl`

Override with `ST_MUSIC_AGENT_APP8_GRAPH_STATE` or the operator CLI flag `--app8-graph-state-file`.

## Supported persistent graphs

### APP8A supervision graphs

A persisted `DependencyGraph` stores the canonical objective and subtask graph plus the exact sequence of `SupervisorEvent` records. On reload APP8E reconstructs the typed contracts and performs `replay_supervision(...)`.

### APP8D coordination graphs

A persisted `CrossProjectPlan` stores project dependency contracts plus exact `CoordinationEvent` records and verified receipts. On reload APP8E reconstructs the typed plan/receipts and performs `replay_coordination(...)`.

All reconstructed fingerprints must match their originally persisted fingerprints.

## Resume semantics

APP8E resume means **deterministic state reconstruction only**.

It can show which graph/node/item is complete, pending, ready, blocked, review-required, or otherwise unresolved after a restart. It does not automatically invoke a model, call a project tool, resume a write, create a branch, or execute the next node.

Any future execution still has to pass through the existing APP8C / APP2–APP7 guarded execution boundaries.

## Graph verification

`verify_graph(graph_id)` binds:

- graph id and kind
- canonical plan fingerprint
- persistent record hashes
- deterministic replay fingerprint
- current journal anchor sequence/hash

into a deterministic verification SHA-256.

Verification scope is local hash-chained graph journal plus deterministic replay. It does not claim an external trust anchor.

## Operator API

APP8E extends the APP7 operator console with GET-only graph endpoints:

- `GET /api/app8/graphs?limit=N`
- `GET /api/app8/graphs/<graph_id>`
- `GET /api/app8/graphs/<graph_id>/verify`

There is no APP8 graph mutation endpoint. Non-GET requests under `/api/app8/graphs` return 405.

Remote read-only mode reuses APP7 bearer authentication. Graph list/detail/verify endpoints require the same authentication before graph data is returned.

## Operator UI

The APP8E console adds a supervision-graph section that can:

- list recent persistent APP8 graphs
- show graph kind and disposition
- show event count
- show plan and replay fingerprints
- verify the local graph journal/replay binding

It does not provide buttons for graph execution, repository mutation, PR opening, merge, deployment, training, activation, canonicalization, or rollback.

## Authority boundary

APP8E does not add authority for:

- repository writes
- protected branch writes
- PR approval or review-thread mutation
- merge or auto-merge
- release/deployment
- training execution
- model activation/canonicalization
- rollback execution
- secret/credential mutation
- privilege changes

Graph summaries, views, and verification payloads explicitly keep execution, repository mutation, PR-open, merge, and production-action authorization false.

## Current APP8 chain

`APP8A Supervisor contracts/simulation`
→ `APP8B Independent critic/reliability`
→ `APP8C Guarded exact-SHA execution`
→ `APP8D Cross-project receipt coordination`
→ `APP8E Persistent operator graph / deterministic resume state`

APP8E is a completion boundary for the current APP8 architecture. Further stages should be driven by demonstrated operator needs rather than automatic authority expansion.
