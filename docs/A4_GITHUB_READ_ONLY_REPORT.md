# A4 — GitHub Read-Only Adapter Completion Report

Status: COMPLETE on `a4/github-read-only-adapter`  
Authority: READ_ONLY only

## Goal

Allow ST Music Agent Lab to inspect one explicitly scoped GitHub repository and produce structured evidence for repository state, files, branches, commits, pull requests, diffs and CI without introducing any GitHub mutation authority.

## Implemented surface

`GitHubReadAdapter` is gated by the existing ST `PolicyEngine` and exposes only read operations:

- repository metadata;
- branch metadata;
- commit metadata;
- UTF-8 repository file content;
- pull request metadata;
- pull request unified diff;
- workflow runs for an exact commit SHA;
- deterministic pull-request diagnostic summary.

Every evidence item carries:

- evidence kind;
- target repository;
- exact REST locator;
- payload;
- deterministic SHA-256 digest over canonical JSON.

## Concrete backend

`GitHubRestReadBackend` uses the Python standard library and deliberately exposes only GET methods.

Security properties:

- repository must be exact `owner/name` form;
- every request path must remain under `/repos/<owner>/<repo>`;
- GitHub API host is fixed to `https://api.github.com`;
- HTTP method is fixed to `GET`;
- response bytes are bounded;
- request timeout is bounded;
- optional token is used only as a request header and is never included in evidence;
- there is no POST, PATCH, PUT or DELETE method on the backend.

A caller may still provide no token for public repositories.

## Policy boundary

The adapter does not interpret possession of a GitHub token as authority. Reads are admitted only when the `TaskSpec` grants the corresponding ST capability:

- repository/branch/commit/file -> `READ_REPOSITORY`;
- PR/diff -> `INSPECT_PULL_REQUESTS`;
- workflow runs -> `INSPECT_CI`.

The A4 adapter contains no branch creation, commit, PR update, merge or deployment function. Those remain outside A4.

## Prepared failing-PR fixture

The test fixture models pull request #7 with:

- open PR;
- exact 40-character head SHA;
- one successful workflow: `foundation`;
- one failed workflow: `compatibility`.

Expected deterministic diagnostic:

```text
state = OPEN
ci_state = FAILED
failing_runs = [compatibility]
evidence_locators = [PR locator, workflow-runs locator]
```

This proves that the read adapter can identify a failing CI surface without performing a repair or mutation.

## Tests

A4 tests cover:

- policy-gated repository/file/branch/commit reads;
- denied reads without TaskSpec capability;
- GET-only PR diff surface;
- failing-workflow diagnostic;
- exact-SHA requirement for CI lookup;
- path-traversal rejection;
- deterministic evidence digest;
- repository-scope validation;
- pre-network rejection when a backend path escapes the configured repository.

The existing GitHub Actions `foundation` workflow executes the complete unit-test suite on Python 3.12.

## Explicitly not activated

A4 does not activate:

- GitHub write tokens as an authority grant;
- branch creation;
- file mutation;
- commit creation;
- pull-request creation or update;
- CI repair loops;
- merge;
- cross-repository mutation;
- production deployment;
- raw OpenManus unrestricted tool execution.

Those remain later-stage capabilities and must pass through independent ST policy gates.

## Next boundary

A5 may add a lab-only branch/PR writer, but it must be a separate adapter and a separate capability surface. It must not extend `GitHubRestReadBackend` into a mixed read/write client. Keeping read and mutation adapters physically separate reduces accidental authority expansion.
