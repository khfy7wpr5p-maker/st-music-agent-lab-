# APP1–APP2 — Operator Console

The Operator Console is the first end-user-visible ST Music Agent application layer. It uses the
Python standard library for HTTP serving and sits above the existing guarded core rather than
creating a second execution path.

## Start in read / preview mode

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

This mode can read project evidence, build the independently verified portfolio plan, and preview a
bounded engineering task. It cannot create branches or write files.

## Start guarded feature-branch execution

Write mode is opt-in and loopback-only:

```bash
st-music-agent app \
  --enable-writes \
  --provider-base-url https://YOUR_PROVIDER/v1 \
  --provider-model YOUR_MODEL \
  --provider-api-key-env PROVIDER_API_KEY \
  --github-token-env GITHUB_TOKEN
```

The CLI arguments contain environment-variable **names**, not credential values. Provider and GitHub
tokens are resolved only at trusted adapter boundaries and are never returned to the browser.

APP2 refuses write mode when the HTTP server is bound to a non-loopback host.

## Project and planning surface

The console reads bounded evidence for:

- Score Restore;
- MusicXML → Guitar TAB;
- Score Editor;
- Real-Time Score Following.

Each card shows state, summary, warnings and next safe boundary. A failure in one repository is
isolated to that card.

**Doğrulanmış plan oluştur** runs the existing `PortfolioPlanningService`; a plan is shown as
verified only after deterministic independent recomputation passes.

## Guarded task flow

```text
user instruction
  -> task preview
  -> exact project repository + protected base SHA
  -> deterministic st-agent/<project>/<task> feature branch
  -> AutonomyPolicy check
  -> explicit user click: run
  -> host creates exact feature branch
  -> model receives bounded repository read tools
  -> model receives task.write_file bound to that exact feature branch
  -> branch head + workflow evidence collected
  -> explicit user click: open PR
  -> exact one-action human approval
  -> PR only
```

The model never receives `github.create_branch`, `github.open_pull_request`, merge, deploy,
training, activation, canonicalization or rollback tools during APP2 execution.

`task.write_file` has no `branch` argument. The host injects the previewed feature branch, so a model
cannot redirect a write to `main`, `master`, or another branch.

## Repository inspection

APP2 adds a task-only `github.tree` projection. It:

- resolves the requested branch to an exact 40-character commit SHA;
- requests the recursive Git tree;
- fails closed when GitHub reports truncation;
- exposes only blob/file entries;
- filters credential-sensitive paths using the existing read safety checks;
- fails closed above 2,000 safe file entries.

The agent then reads only the files it needs with `github.read_file`.

## HTTP surface

Read routes:

- `GET /`
- `GET /api/health`
- `GET /api/session`
- `GET /api/capabilities`
- `GET /api/projects?ref=main`
- `GET /api/projects/<project>?ref=main`
- `GET /api/plan?ref=main`
- `GET /api/tasks/status/<task-id>`

Task routes:

- `POST /api/tasks/preview`
- `POST /api/tasks/run`
- `POST /api/tasks/open-pr`

Every task POST requires the per-process `X-ST-Session` token and a bounded JSON body. There is no
merge endpoint.

## Safety boundary

APP2 widens only reversible development capability:

- feature-branch creation: policy must be `auto_execute`;
- feature-branch file writes: policy must be `auto_execute`;
- PR opening: policy must remain `require_human` and requires a separate UI click;
- protected-branch mutation: unavailable;
- merge: unavailable;
- delete/destructive operations: unavailable to the model;
- deployment/training/activation/canonicalization/rollback: unavailable.

A successful APP2 run is development evidence, not production authority.
