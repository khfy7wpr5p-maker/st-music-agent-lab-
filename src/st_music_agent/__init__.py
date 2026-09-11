"""ST Music Agent core package."""

from .catalog import DEFAULT_MODELS
from .contracts import ActionRequest, AgentTask, ModelProfile, RiskLevel, TaskKind
from .music_evidence import (
    MUSIC_EVIDENCE_SCHEMA_VERSION,
    EvidenceAuthority,
    EvidenceSource,
    MusicEvidenceError,
    MusicEvidenceSnapshot,
    MusicProject,
)
from .music_factory import build_default_music_domain_toolset
from .policy import AutonomyDecision, AutonomyPolicy
from .router import ModelRouter

__all__ = [
    "DEFAULT_MODELS",
    "MUSIC_EVIDENCE_SCHEMA_VERSION",
    "ActionRequest",
    "AgentTask",
    "AutonomyDecision",
    "AutonomyPolicy",
    "EvidenceAuthority",
    "EvidenceSource",
    "ModelProfile",
    "ModelRouter",
    "MusicEvidenceError",
    "MusicEvidenceSnapshot",
    "MusicProject",
    "RiskLevel",
    "TaskKind",
    "build_default_music_domain_toolset",
]
