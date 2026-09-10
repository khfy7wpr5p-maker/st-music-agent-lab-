# A5 — Lab-only Branch / Commit / PR Writer

Status: IMPLEMENTED on `a5/lab-only-pr-writer` pending CI / review.

## Goal

A5 adds the first mutation surface to ST Music Agent Lab, but confines that surface to one host-trusted repository and non-default task branches. It does not grant general GitHub write authority.

## Implemented surface

`GitHubLabWriteAdapter` can:

1. create an `agent/` task branch from an exact 40-character base commit SHA;
2. create or update a bounded UTF-8 repository file through the GitHub Contents API;
3. create the commit implicitly produced by that contents mutation;
4. open a pull request from the task branch to the exact `TaskSpec.base_ref`;
5. claim a bounded CI repair attempt up to `TaskSpec.retry_budget`.

`GitHubRestLabWriteBackend` exposes only these REST route shapes:

- `POST /git/refs`;
- `PUT /contents/<bounded-path>`;
- `POST /pulls`.

No generic HTTP mutation method is exposed.

## Defense in depth

A mutation must satisfy all of the following:

- `TaskSpec.target_repository` equals the host-trusted lab repository;
- the requested capability is present in `TaskSpec`;
- the `AuthorityMode` permits the action;
- mutation targets an explicit non-default `agent/` branch;
- file paths remain inside `TaskSpec.allowed_paths`;
- file payload is at most 256,000 UTF-8 bytes;
- an optional existing-file SHA must be an exact 40-character blob SHA;
- branch creation uses an exact 40-character base commit SHA;
- CI repair attempts cannot exceed the task retry budget.

A token is merely a transport credential. It does not widen the task or policy authority.

## Intentionally absent

A5 contains no endpoint or adapter method for:

- writing `main` or `master`;
- force-push or ref update;
- merge;
- deleting files;
- patching pull requests;
- rerunning workflows;
- repository/branch protection changes;
- secrets;
- releases or deployments;
- cross-repository mutation.

The merge boundary therefore remains outside the agent.

## Validation

`tests/test_github_write.py` covers:

- bounded branch -> file/commit -> PR flow;
- cross-repository denial;
- default/non-agent branch denial;
- out-of-scope path denial;
- exact expected blob SHA validation;
- hard CI repair budget cap;
- read-only mode denial;
- REST route allowlist enforcement;
- file-size cap.

The existing foundation workflow runs the full Python unit suite on Python 3.12. A5 is complete only after the stacked PR reports a green workflow.

## Next stage

A6 should introduce an independent validator registry. The writer must not decide that its own changes are valid: repository tests, contract validators, diff-risk checks, deterministic reruns, and CI evidence must remain separate authorities.
