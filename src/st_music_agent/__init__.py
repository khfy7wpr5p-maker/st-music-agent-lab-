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
from .learning_evaluation import (
    EVALUATION_POLICY_VERSION,
    EVALUATION_SCHEMA_VERSION,
    BenchmarkCaseResult,
    BenchmarkOutcome,
    BenchmarkRun,
    BenchmarkSeverity,
    LearningEvaluationError,
    LearningEvaluationGate,
    LearningEvaluationPolicy,
    LearningEvaluationReadToolset,
    LearningEvaluationReport,
    PromotionDecision,
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
    "EVALUATION_POLICY_VERSION",
    "EVALUATION_SCHEMA_VERSION",
    "EXPERIENCE_SCHEMA_VERSION",
    "MUSIC_EVIDENCE_SCHEMA_VERSION",
    "PORTFOLIO_PLAN_SCHEMA_VERSION",
    "PORTFOLIO_POLICY_VERSION",
    "ActionRequest",
    "AgentTask",
    "AutonomyDecision",
    "AutonomyPolicy",
    "BenchmarkCaseResult",
    "BenchmarkOutcome",
    "BenchmarkRun",
    "BenchmarkSeverity",
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
    "LearningEvaluationError",
    "LearningEvaluationGate",
    "LearningEvaluationPolicy",
    "LearningEvaluationReadToolset",
    "LearningEvaluationReport",
    "ModelProfile",
    "ModelRouter",
    "MusicEvidenceError",
    "MusicEvidenceSnapshot",
    "MusicProject",
    "PlanVerificationReport",
    "PlanVerificationStatus",
    "PortfolioPlanningService",
    "PromotionDecision",
    "RiskLevel",
    "ScoreEditorEvidenceAdapter",
    "ScoreFollowingEvidenceAdapter",
    "TaskKind",
    "build_default_music_domain_toolset",
]
