from __future__ import annotations

from .github_read import GitHubReadClient, GitHubReadConfig
from .music_adapters import (
    MusicDomainToolset,
    MusicXmlTabEvidenceAdapter,
    ScoreRestoreEvidenceAdapter,
)

_SCORE_RESTORE_REPOSITORY = "khfy7wpr5p-maker/st-score-restore-engine"
_MUSICXML_TAB_REPOSITORY = "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine"


def build_default_music_domain_toolset(
    *,
    token_env: str | None = None,
    api_base: str = "https://api.github.com",
) -> MusicDomainToolset:
    """Build read-only evidence adapters for the current ST music repositories.

    The returned toolset performs no mutation. A GitHub token is optional for public reads and,
    when configured, is resolved only by the existing GitHub read adapter at request time.
    """

    score_restore = GitHubReadClient(
        GitHubReadConfig(
            repository=_SCORE_RESTORE_REPOSITORY,
            token_env=token_env,
            api_base=api_base,
        )
    )
    musicxml_tab = GitHubReadClient(
        GitHubReadConfig(
            repository=_MUSICXML_TAB_REPOSITORY,
            token_env=token_env,
            api_base=api_base,
        )
    )
    return MusicDomainToolset(
        score_restore=ScoreRestoreEvidenceAdapter(score_restore),
        musicxml_tab=MusicXmlTabEvidenceAdapter(musicxml_tab),
    )
