"""ST Music Agent core package."""

from .catalog import DEFAULT_MODELS
from .contracts import ActionRequest, AgentTask, ModelProfile, RiskLevel, TaskKind
from .experience import (
    EXPERIENCE_SCHEMA_VERSION,
    ExperienceAdvisor,
    ExperienceObservation,
    ExperienceOutcome,
    ExperienceReadToolset,
    ExperienceStore,
    LearningDisposition,
)
from .music_adapters_extended import (
    FullMusicDomainToolset,
    ScoreEditorEvidenceAdapter,
    ScoreFollowingEvidenceAdapter,
)
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
from .portfolio_planning import (
    PORTFOLIO_PLAN_SCHEMA_VERSION,
    PORTFOLIO_POLICY_VERSION,
    CrossProjectPlan,
    CrossProjectPlanner,
    CrossProjectVerifier,
    PlanVerificationReport,
    PlanVerificationStatus,
    PortfolioPlanningService,
)
from .router import ModelRouter

__all__ = [
    "DEFAULT_MODELS",
    "EXPERIENCE_SCHEMA_VERSION",
    "MUSIC_EVIDENCE_SCHEMA_VERSION",
    "PORTFOLIO_PLAN_SCHEMA_VERSION",
    "PORTFOLIO_POLICY_VERSION",
    "ActionRequest",
    "AgentTask",
    "AutonomyDecision",
    "AutonomyPolicy",
    "CrossProjectPlan",
    "CrossProjectPlanner",
    "CrossProjectVerifier",
    "EvidenceAuthority",
    "EvidenceSource",
    "ExperienceAdvisor",
    "ExperienceObservation",
    "ExperienceOutcome",
    "ExperienceReadToolset",
    "ExperienceStore",
    "FullMusicDomainToolset",
    "LearningDisposition",
    "ModelProfile",
    "ModelRouter",
    "MusicEvidenceError",
    "MusicEvidenceSnapshot",
    "MusicProject",
    "PlanVerificationReport",
    "PlanVerificationStatus",
    "PortfolioPlanningService",
    "RiskLevel",
    "ScoreEditorEvidenceAdapter",
    "ScoreFollowingEvidenceAdapter",
    "TaskKind",
    "build_default_music_domain_toolset",
]
