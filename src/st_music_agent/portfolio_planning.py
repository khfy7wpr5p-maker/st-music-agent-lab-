from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .agent_tools import ToolRegistry
from .music_adapters_extended import FullMusicDomainToolset
from .music_evidence import MUSIC_EVIDENCE_SCHEMA_VERSION, MusicProject

PORTFOLIO_PLAN_SCHEMA_VERSION = "1.0.0"
PORTFOLIO_POLICY_VERSION = "2026-09-11.v1"


class PortfolioPlanningError(RuntimeError):
    pass


class PlanVerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class PlanCandidate:
    rank: int
    project: MusicProject
    category: str
    action: str
    rationale: str
    constraints: tuple[str, ...]
    evidence_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "project": self.project.value,
            "category": self.category,
            "action": self.action,
            "rationale": self.rationale,
            "constraints": list(self.constraints),
            "evidence_hash": self.evidence_hash,
        }


@dataclass(frozen=True, slots=True)
class CrossProjectPlan:
    plan_id: str
    policy_version: str
    evidence_set_hash: str
    candidates: tuple[PlanCandidate, ...]
    execution_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PORTFOLIO_PLAN_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "policy_version": self.policy_version,
            "evidence_set_hash": self.evidence_set_hash,
            "execution_authorized": self.execution_authorized,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class PlanVerificationReport:
    status: PlanVerificationStatus
    plan_id: str
    recomputed_plan_id: str | None
    issues: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "plan_id": self.plan_id,
            "recomputed_plan_id": self.recomputed_plan_id,
            "issues": list(self.issues),
        }


class CrossProjectPlanner:
    """Deterministic planner over the four authoritative music snapshots.

    The default policy deliberately closes bounded validation/integration uncertainty before
    widening product capability or starting new research. It is a transparent policy, not a
    claim that one universal project priority exists.
    """

    _PROJECT_ORDER = (
        MusicProject.SCORE_RESTORE,
        MusicProject.MUSICXML_GUITAR_TAB,
        MusicProject.SCORE_EDITOR,
        MusicProject.REAL_TIME_SCORE_FOLLOWING,
    )

    def plan(self, snapshots: Mapping[str, Mapping[str, Any]]) -> CrossProjectPlan:
        normalized = self._normalize_snapshots(snapshots)
        candidates = tuple(
            self._candidate(project, normalized[project.value], rank)
            for rank, project in enumerate(self._PROJECT_ORDER, start=1)
        )
        evidence_set_hash = self._hash_value(
            {project.value: normalized[project.value] for project in self._PROJECT_ORDER}
        )
        plan_base = {
            "schema_version": PORTFOLIO_PLAN_SCHEMA_VERSION,
            "policy_version": PORTFOLIO_POLICY_VERSION,
            "evidence_set_hash": evidence_set_hash,
            "execution_authorized": False,
            "candidates": [candidate.as_dict() for candidate in candidates],
        }
        return CrossProjectPlan(
            plan_id=self._hash_value(plan_base),
            policy_version=PORTFOLIO_POLICY_VERSION,
            evidence_set_hash=evidence_set_hash,
            candidates=candidates,
            execution_authorized=False,
        )

    def _normalize_snapshots(
        self,
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Mapping[str, Any]]:
        expected = {project.value for project in self._PROJECT_ORDER}
        if set(snapshots) != expected:
            missing = sorted(expected - set(snapshots))
            extra = sorted(set(snapshots) - expected)
            raise PortfolioPlanningError(
                f"portfolio snapshot set mismatch; missing={missing}, extra={extra}"
            )
        normalized: dict[str, Mapping[str, Any]] = {}
        for project in self._PROJECT_ORDER:
            snapshot = snapshots[project.value]
            self._validate_snapshot(project, snapshot)
            normalized[project.value] = snapshot
        return normalized

    @staticmethod
    def _validate_snapshot(project: MusicProject, snapshot: Mapping[str, Any]) -> None:
        if snapshot.get("schema_version") != MUSIC_EVIDENCE_SCHEMA_VERSION:
            raise PortfolioPlanningError(f"unsupported evidence schema for {project.value}")
        if snapshot.get("project") != project.value:
            raise PortfolioPlanningError(f"project identity mismatch for {project.value}")
        claims = snapshot.get("claims")
        if not isinstance(claims, Mapping):
            raise PortfolioPlanningError(f"claims missing for {project.value}")
        next_boundary = snapshot.get("next_safe_boundary")
        if not isinstance(next_boundary, str) or not next_boundary.strip():
            raise PortfolioPlanningError(f"next safe boundary missing for {project.value}")
        sources = snapshot.get("sources")
        if not isinstance(sources, list) or not sources:
            raise PortfolioPlanningError(f"source provenance missing for {project.value}")
        required_source_fields = {"repository", "ref", "path", "blob_sha"}
        for source in sources:
            if not isinstance(source, Mapping) or set(source) != required_source_fields:
                raise PortfolioPlanningError(f"invalid source provenance for {project.value}")
            if any(not isinstance(source[field], str) or not source[field].strip() for field in required_source_fields):
                raise PortfolioPlanningError(f"empty source provenance for {project.value}")

    def _candidate(
        self,
        project: MusicProject,
        snapshot: Mapping[str, Any],
        rank: int,
    ) -> PlanCandidate:
        claims = snapshot["claims"]
        if not isinstance(claims, Mapping):
            raise PortfolioPlanningError(f"claims missing for {project.value}")
        action = str(snapshot["next_safe_boundary"])
        evidence_hash = self._hash_value(snapshot)

        if project is MusicProject.SCORE_RESTORE:
            self._require_claim(claims, "candidate_checkpoint_frozen", True, project)
            self._require_claim(claims, "production_inference_authorized", False, project)
            self._require_claim(claims, "stage12_entry_authorized", False, project)
            return PlanCandidate(
                rank=rank,
                project=project,
                category="validated_candidate_integration",
                action=action,
                rationale=(
                    "Close the frozen-candidate non-training integration uncertainty before "
                    "widening production authority or starting lower-priority expansion."
                ),
                constraints=(
                    "production inference remains unauthorized",
                    "Stage 12 remains unauthorized",
                    "no held-out retuning or automatic promotion",
                ),
                evidence_hash=evidence_hash,
            )

        if project is MusicProject.MUSICXML_GUITAR_TAB:
            self._require_claim(claims, "review_required_is_global_lock", False, project)
            self._require_claim(claims, "canonical_tab_requires_pass", True, project)
            self._require_claim(claims, "export_requires_pass", True, project)
            return PlanCandidate(
                rank=rank,
                project=project,
                category="human_review_integration",
                action=action,
                rationale=(
                    "Connect the bounded teacher-review path while preserving existing score/TAB "
                    "availability and PASS-only canonical export."
                ),
                constraints=(
                    "REVIEW_REQUIRED must not become a global lock",
                    "canonical TAB and export remain PASS-only",
                    "BLOCKED behavior must remain safety-disabling",
                ),
                evidence_hash=evidence_hash,
            )

        if project is MusicProject.SCORE_EDITOR:
            self._require_claim(claims, "manual_device_validation_required", True, project)
            self._require_claim(claims, "standalone_release_gate_passed", False, project)
            self._require_claim(claims, "seslitab_cutover_authorized", False, project)
            return PlanCandidate(
                rank=rank,
                project=project,
                category="bounded_product_feature",
                action=action,
                rationale=(
                    "Continue the declared editor feature boundary without converting feature "
                    "completion into release or SesliTab cutover authority."
                ),
                constraints=(
                    "manual device/browser validation remains required",
                    "standalone release gate remains closed",
                    "SesliTab V4 cutover remains unauthorized",
                ),
                evidence_hash=evidence_hash,
            )

        self._require_claim(claims, "research_evidence_is_production_authority", False, project)
        self._require_claim(claims, "research_evidence_is_pedagogical_authority", False, project)
        self._require_claim(claims, "acoustic_mono_mixture_authority", False, project)
        return PlanCandidate(
            rank=rank,
            project=project,
            category="research_expansion",
            action=action,
            rationale=(
                "Advance the next declared research stage only after nearer-term validated "
                "integration/product boundaries, without overstating research authority."
            ),
            constraints=(
                "research evidence is not production authority",
                "research evidence is not pedagogical authority",
                "channel-separated evidence is not acoustic-mixture authority",
            ),
            evidence_hash=evidence_hash,
        )

    @staticmethod
    def _require_claim(
        claims: Mapping[str, Any],
        key: str,
        expected: Any,
        project: MusicProject,
    ) -> None:
        if key not in claims or claims.get(key) != expected:
            raise PortfolioPlanningError(
                f"required planning claim changed for {project.value}: {key}"
            )

    @staticmethod
    def _hash_value(value: Any) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class CrossProjectVerifier:
    """Recomputes the plan from evidence and rejects any semantic drift."""

    def __init__(self, planner: CrossProjectPlanner | None = None) -> None:
        self.planner = planner or CrossProjectPlanner()

    def verify(
        self,
        plan: CrossProjectPlan,
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> PlanVerificationReport:
        issues: list[str] = []
        recomputed: CrossProjectPlan | None = None
        try:
            recomputed = self.planner.plan(snapshots)
        except PortfolioPlanningError as exc:
            issues.append(f"recomputation failed: {exc}")

        if plan.execution_authorized:
            issues.append("portfolio planning must never authorize execution")
        if plan.policy_version != PORTFOLIO_POLICY_VERSION:
            issues.append("plan policy version does not match verifier policy")
        if recomputed is not None and plan.as_dict() != recomputed.as_dict():
            issues.append("plan differs from deterministic recomputation")

        return PlanVerificationReport(
            status=(
                PlanVerificationStatus.PASS if not issues else PlanVerificationStatus.FAIL
            ),
            plan_id=plan.plan_id,
            recomputed_plan_id=recomputed.plan_id if recomputed is not None else None,
            issues=tuple(issues),
        )


class PortfolioPlanningService:
    """Collects fresh snapshots, plans, and verifies in one read-only operation."""

    def __init__(
        self,
        music_tools: FullMusicDomainToolset,
        planner: CrossProjectPlanner | None = None,
        verifier: CrossProjectVerifier | None = None,
    ) -> None:
        self.music_tools = music_tools
        self.planner = planner or CrossProjectPlanner()
        self.verifier = verifier or CrossProjectVerifier(self.planner)

    def plan_and_verify(self, ref: str = "main") -> dict[str, Any]:
        snapshots = self._collect(ref)
        plan = self.planner.plan(snapshots)
        verification = self.verifier.verify(plan, snapshots)
        if verification.status is not PlanVerificationStatus.PASS:
            raise PortfolioPlanningError("internally generated portfolio plan failed verification")
        return {
            "plan": plan.as_dict(),
            "verification": verification.as_dict(),
            "snapshots": snapshots,
        }

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "music.portfolio.plan",
            self._tool_plan,
            description=(
                "Collect all four authoritative music snapshots and return a deterministic, "
                "independently verified read-only portfolio plan."
            ),
            parameters={
                "type": "object",
                "properties": {"ref": {"type": "string", "default": "main"}},
                "additionalProperties": False,
            },
        )

    def _tool_plan(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        extras = set(arguments) - {"ref"}
        if extras:
            raise ValueError("tool arguments contain unsupported fields")
        ref = arguments.get("ref", "main")
        if not isinstance(ref, str) or not ref.strip():
            raise TypeError("ref must be non-empty text")
        return self.plan_and_verify(ref)

    def _collect(self, ref: str) -> dict[str, Mapping[str, Any]]:
        return {
            MusicProject.SCORE_RESTORE.value: self.music_tools.score_restore.collect(ref).as_dict(),
            MusicProject.MUSICXML_GUITAR_TAB.value: self.music_tools.musicxml_tab.collect(ref).as_dict(),
            MusicProject.SCORE_EDITOR.value: self.music_tools.score_editor.collect(ref).as_dict(),
            MusicProject.REAL_TIME_SCORE_FOLLOWING.value: self.music_tools.score_following.collect(ref).as_dict(),
        }
