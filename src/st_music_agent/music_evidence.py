from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

MUSIC_EVIDENCE_SCHEMA_VERSION = "1.0.0"


class MusicEvidenceError(RuntimeError):
    pass


class MusicProject(str, Enum):
    SCORE_RESTORE = "score_restore"
    MUSICXML_GUITAR_TAB = "musicxml_guitar_tab"


class EvidenceAuthority(str, Enum):
    REPOSITORY_CURRENT_TRUTH = "repository_current_truth"
    EXECUTABLE_CONTRACT = "executable_contract"


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    repository: str
    ref: str
    path: str
    blob_sha: str

    def __post_init__(self) -> None:
        for label, value in (
            ("repository", self.repository),
            ("ref", self.ref),
            ("path", self.path),
            ("blob_sha", self.blob_sha),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be non-empty text")

    def as_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "ref": self.ref,
            "path": self.path,
            "blob_sha": self.blob_sha,
        }


@dataclass(frozen=True, slots=True)
class MusicEvidenceSnapshot:
    project: MusicProject
    authority: EvidenceAuthority
    state: str
    summary: str
    claims: Mapping[str, Any]
    warnings: tuple[str, ...] = ()
    next_safe_boundary: str | None = None
    sources: tuple[EvidenceSource, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.state.strip():
            raise ValueError("state must not be empty")
        if not self.summary.strip():
            raise ValueError("summary must not be empty")
        if not self.sources:
            raise ValueError("at least one evidence source is required")
        if self.next_safe_boundary is not None and not self.next_safe_boundary.strip():
            raise ValueError("next_safe_boundary must be non-empty when provided")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MUSIC_EVIDENCE_SCHEMA_VERSION,
            "project": self.project.value,
            "authority": self.authority.value,
            "state": self.state,
            "summary": self.summary,
            "claims": dict(self.claims),
            "warnings": list(self.warnings),
            "next_safe_boundary": self.next_safe_boundary,
            "sources": [source.as_dict() for source in self.sources],
        }
