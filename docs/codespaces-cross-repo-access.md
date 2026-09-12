# Codespaces cross-repository access

ST Music Agent Lab performs guarded feature-branch work in four target repositories. A Codespaces token created only for this repository cannot create branches in those repositories unless the additional access is explicitly authorized when the codespace is created.

The repository therefore requests the following bounded permissions through `.devcontainer/devcontainer.json`:

| Repository | Requested permissions | Purpose |
| --- | --- | --- |
| `khfy7wpr5p-maker/st-score-editor-core` | `contents: write`, `actions: read`, `pull_requests: write` | feature-branch commits, CI evidence, human-gated PR opening |
| `khfy7wpr5p-maker/st-score-restore-engine` | `contents: write`, `actions: read`, `pull_requests: write` | feature-branch commits, CI evidence, human-gated PR opening |
| `khfy7wpr5p-maker/musicxml-to-guitar-tab-engine` | `contents: write`, `actions: read`, `pull_requests: write` | feature-branch commits, CI evidence, human-gated PR opening |
| `khfy7wpr5p-maker/st-real-time-score-following-lab` | `contents: write`, `actions: read`, `pull_requests: write` | feature-branch commits, CI evidence, human-gated PR opening |

No wildcard repository grant and no `write-all` permission is requested. Merge, deployment, release, training, production activation, canonicalization, rollback, and secret mutation remain outside the ST Music Agent runtime authority.

## Important: create a new codespace

GitHub applies additional repository permissions only to new codespaces created after the configuration is committed. Rebuilding an existing codespace does not widen its token.

After this configuration reaches `main`:

1. Stop the current codespace after saving any local work.
2. Create a new codespace from the latest `main` branch of `khfy7wpr5p-maker/st-music-agent-lab-`.
3. Review GitHub's additional repository permission prompt.
4. Authorize the four listed ST repositories and only the requested permissions.
5. In the new codespace, verify the token before running the agent.

A reversible branch probe for Score Editor is:

```bash
BASE_SHA=$(gh api repos/khfy7wpr5p-maker/st-score-editor-core/git/ref/heads/main --jq '.object.sha')

gh api --method POST \
  repos/khfy7wpr5p-maker/st-score-editor-core/git/refs \
  -f ref='refs/heads/st-agent-token-probe' \
  -f sha="$BASE_SHA"

gh api --method DELETE \
  repos/khfy7wpr5p-maker/st-score-editor-core/git/refs/heads/st-agent-token-probe
```

The probe must create and then delete only the temporary branch. It must not modify `main`.

## Why `pull_requests: write` is requested

The application keeps PR creation human-gated. The permission is present so that the operator's explicit `PR aç` action can work after a task has passed the existing evidence and review gates. The model itself does not gain autonomous merge or PR-approval authority.
