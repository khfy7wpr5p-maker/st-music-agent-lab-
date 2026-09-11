# APP1 — Runnable Operator Console

APP1 is the first end-user-visible ST Music Agent application layer. It is intentionally small and
uses only the Python standard library for HTTP serving, so the existing core package remains easy to
run and test.

## Start

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

The default address is `http://127.0.0.1:8765`.

For private repository reads, set a GitHub token in the environment variable named by
`--github-token-env` (default: `GITHUB_TOKEN`). The token value is resolved only by the existing
read adapter and is never rendered into the UI.

## What the console does

The console reads the current bounded evidence for:

- Score Restore;
- MusicXML → Guitar TAB;
- Score Editor;
- Real-Time Score Following.

It renders each project state, summary, warnings and next safe boundary. One repository/evidence
failure is isolated to that project's card so the rest of the console remains usable.

The **Doğrulanmış plan oluştur** action collects all four snapshots again and runs the existing
`PortfolioPlanningService`. The result must pass independent deterministic recomputation before it
is shown as a verified plan.

## HTTP surface

- `GET /` — operator UI;
- `GET /api/health` — application status and safety mode;
- `GET /api/capabilities` — explicit read/write capability summary;
- `GET /api/projects?ref=main` — four project cards with isolated availability;
- `GET /api/projects/<project>?ref=main` — one project snapshot;
- `GET /api/plan?ref=main` — fresh deterministic plan + verifier report.

All non-GET methods currently fail closed with `405`.

## Safety boundary

APP1 is not a fake execution UI. It does not expose a button that claims to run work when no bounded
execution contract is connected. It deliberately keeps:

- `execution_authorized=false`;
- feature-branch task execution disabled;
- protected-branch mutation disabled;
- training/deployment/canonicalization/rollback execution disabled.

The next application boundary is to connect the already-existing guarded feature-branch execution
plane to an explicit task request/preview/approval UI without widening production authority.
