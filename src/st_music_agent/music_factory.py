from __future__ import annotations

from .github_read import GitHubReadClient, GitHubReadConfig
from .music_adapters import MusicXmlTabEvidenceAdapter, ScoreRestoreEvidenceAdapter
from .music_adapters_extended import (
    FullMusicDomainToolset,
    ScoreEditorEvidenceAdapter,
    ScoreFollowingEvidenceAdapter,
)

_SCORE_RESTORE_REPOSITORY = "khfy7wpr5p-maker/st-score-restore-engine"
_MUSICXML_TAB_REPOSITORY = "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine"
_SCORE_EDITOR_REPOSITORY = "khfy7wpr5p-maker/st-score-editor-core"
_SCORE_FOLLOWING_REPOSITORY = "khfy7wpr5p-maker/st-real-time-score-following-lab"


def _read_client(
    repository: str,
    *,
    token_env: str | None,
    api_base: str,
) -> GitHubReadClient:
    return GitHubReadClient(
        GitHubReadConfig(
            repository=repository,
            token_env=token_env,
            api_base=api_base,
        )
    )


def build_default_music_domain_toolset(
    *,
    token_env: str | None = None,
    api_base: str = "https://api.github.com",
) -> FullMusicDomainToolset:
    """Build read-only evidence adapters for the current ST music repositories.

    The returned toolset performs no mutation. A GitHub token is optional for public reads and is
    required when a configured repository is private. When configured, the token is resolved only
    by the existing GitHub read adapter at request time.
    """

    score_restore = _read_client(
        _SCORE_RESTORE_REPOSITORY,
        token_env=token_env,
        api_base=api_base,
    )
    musicxml_tab = _read_client(
        _MUSICXML_TAB_REPOSITORY,
        token_env=token_env,
        api_base=api_base,
    )
    score_editor = _read_client(
        _SCORE_EDITOR_REPOSITORY,
        token_env=token_env,
        api_base=api_base,
    )
    score_following = _read_client(
        _SCORE_FOLLOWING_REPOSITORY,
        token_env=token_env,
        api_base=api_base,
    )
    return FullMusicDomainToolset(
        score_restore=ScoreRestoreEvidenceAdapter(score_restore),
        musicxml_tab=MusicXmlTabEvidenceAdapter(musicxml_tab),
        score_editor=ScoreEditorEvidenceAdapter(score_editor),
        score_following=ScoreFollowingEvidenceAdapter(score_following),
    )
