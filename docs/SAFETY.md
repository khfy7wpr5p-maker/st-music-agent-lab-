# ST Music Agent Lab — Safety and Authority v0

Status: binding architecture baseline for lab development.

## Core rule

The agent may automate work only inside explicitly granted capabilities. Planning, confidence, or model output never expands authority.

## Default posture

- Default authority: `READ_ONLY`.
- Default repository scope: this lab only.
- Default branch policy: never write directly to the default branch.
- Default merge policy: human approval required.
- Default external-project policy: read-only until separately allowlisted.
- Default production policy: disabled.
- Default private/user-data policy: disabled.

## Allowed without additional authority

When the current task permits them:

- inspect repository metadata and source files;
- read architecture/tests/contracts;
- create bounded plans and reports;
- run approved tests in an isolated sandbox;
- compare deterministic outputs;
- collect non-secret CI evidence;
- abstain when evidence is insufficient.

## Branch-write authority

A task may separately grant branch-write authority. It permits only:

- creation of a non-default task branch;
- bounded file changes inside the task scope;
- commits on that task branch;
- local validation;
- PR creation when requested or admitted by the task contract.

It does not imply merge authority.

## Human-gated operations

The v0 system requires explicit human authority for:

- merging to the default branch;
- changing production/deployment configuration;
- activating credentials, paid services, domains, or live infrastructure;
- licensing changes;
- destructive history changes;
- model promotion or training-data admission;
- teacher approval/publication/share authorization;
- enabling access to private/student/user data;
- broadening cross-repository write scope.

## Forbidden operations

- force-push or rewriting protected history;
- bypassing or weakening CI/tests to make a candidate pass;
- fabricating metrics, tests, evidence, approvals, or provenance;
- committing API keys, tokens, cookies, passwords, credentials, private audio, student data, or secrets;
- silently changing acceptance thresholds after seeing a failing candidate;
- allowing the agent to rewrite validator truth to validate its own change;
- treating web research or LLM output as canonical musical truth;
- using renderer output/geometry as semantic score authority;
- silently converting uncertainty into a guessed correction;
- automatic production deployment in the lab baseline.

## Secret handling

Runtime secrets must come from environment variables or an external secret store. `.env` and equivalent local secret files remain ignored. Logs and reports must redact credentials and private content.

## Evidence handling

Agent outputs are evidence, not authority. Every side-effecting change must retain:

- base identity;
- changed-file list;
- validator/test results;
- unresolved failures;
- final task state.

Historical evidence is append-only. Do not rewrite old failure records to reflect later success.

## Failure semantics

Use explicit run states:

- `SUCCEEDED`: requested work completed and required validators passed;
- `NEEDS_REVIEW`: bounded work exists but a human decision or unresolved ambiguity remains;
- `BLOCKED`: required precondition or validator prevents safe continuation;
- `ABSTAINED`: evidence is insufficient to make a bounded proposal safely.

These are Agent Lab workflow states and do not replace domain-specific PASS/REVIEW_REQUIRED/BLOCKED contracts in target repositories.
