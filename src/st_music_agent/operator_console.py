from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .music_evidence import MusicProject
from .music_factory import build_default_music_domain_toolset
from .portfolio_planning import PortfolioPlanningService

OPERATOR_CONSOLE_SCHEMA_VERSION = "1.0.0"
OPERATOR_CONSOLE_MODE = "read_only_operator_console"


class OperatorConsoleError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectDescriptor:
    project: MusicProject
    name: str
    repository: str

    def as_dict(self) -> dict[str, str]:
        return {
            "project": self.project.value,
            "name": self.name,
            "repository": self.repository,
        }


PROJECTS = (
    ProjectDescriptor(
        MusicProject.SCORE_RESTORE,
        "Score Restore",
        "khfy7wpr5p-maker/st-score-restore-engine",
    ),
    ProjectDescriptor(
        MusicProject.MUSICXML_GUITAR_TAB,
        "MusicXML → Guitar TAB",
        "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine",
    ),
    ProjectDescriptor(
        MusicProject.SCORE_EDITOR,
        "Score Editor",
        "khfy7wpr5p-maker/st-score-editor-core",
    ),
    ProjectDescriptor(
        MusicProject.REAL_TIME_SCORE_FOLLOWING,
        "Real-Time Score Following",
        "khfy7wpr5p-maker/st-real-time-score-following-lab",
    ),
)


class OperatorConsoleService:
    """Read-only application façade over the verified ST music evidence plane.

    This service deliberately does not expose mutation, training, deployment, canonicalization,
    or rollback execution. It gives a real UI a bounded view of current project evidence and the
    deterministic cross-project plan produced by the A14 verifier pipeline.
    """

    def __init__(
        self,
        *,
        music_tools: Any | None = None,
        token_env: str | None = "GITHUB_TOKEN",
        api_base: str = "https://api.github.com",
    ) -> None:
        self.music_tools = music_tools or build_default_music_domain_toolset(
            token_env=token_env,
            api_base=api_base,
        )
        self.planning = PortfolioPlanningService(self.music_tools)

    def health(self) -> dict[str, Any]:
        return {
            "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
            "status": "ok",
            "mode": OPERATOR_CONSOLE_MODE,
            "project_count": len(PROJECTS),
            "execution_authorized": False,
            "mutation_enabled": False,
            "human_approval_required_for_production_actions": True,
        }

    def list_projects(self, ref: str = "main") -> dict[str, Any]:
        self._validate_ref(ref)
        projects: list[dict[str, Any]] = []
        for descriptor in PROJECTS:
            item = descriptor.as_dict()
            try:
                snapshot = self._collect(descriptor.project, ref)
            except Exception as exc:  # noqa: BLE001 - errors are isolated per project card.
                item.update(
                    {
                        "availability": "error",
                        "error": self._safe_error(exc),
                        "snapshot": None,
                    }
                )
            else:
                item.update(
                    {
                        "availability": "ok",
                        "error": None,
                        "snapshot": snapshot,
                    }
                )
            projects.append(item)
        return {
            "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
            "ref": ref,
            "mode": OPERATOR_CONSOLE_MODE,
            "projects": projects,
        }

    def project_snapshot(self, project: str, ref: str = "main") -> dict[str, Any]:
        self._validate_ref(ref)
        descriptor = self._descriptor(project)
        snapshot = self._collect(descriptor.project, ref)
        return {
            "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
            "ref": ref,
            "descriptor": descriptor.as_dict(),
            "snapshot": snapshot,
            "execution_authorized": False,
        }

    def verified_plan(self, ref: str = "main") -> dict[str, Any]:
        self._validate_ref(ref)
        result = self.planning.plan_and_verify(ref)
        return {
            "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
            "ref": ref,
            "mode": OPERATOR_CONSOLE_MODE,
            "execution_authorized": False,
            **result,
        }

    def action_capabilities(self) -> dict[str, Any]:
        return {
            "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
            "read": {
                "project_status": True,
                "project_evidence": True,
                "verified_portfolio_plan": True,
            },
            "write": {
                "feature_branch_task_execution": False,
                "protected_branch_mutation": False,
                "training": False,
                "deployment": False,
                "canonicalization": False,
                "rollback_execution": False,
            },
            "next_application_boundary": (
                "connect guarded feature-branch task execution behind the existing policy and "
                "approval layer"
            ),
        }

    def _collect(self, project: MusicProject, ref: str) -> dict[str, Any]:
        collectors: dict[MusicProject, Callable[[str], Any]] = {
            MusicProject.SCORE_RESTORE: self.music_tools.score_restore.collect,
            MusicProject.MUSICXML_GUITAR_TAB: self.music_tools.musicxml_tab.collect,
            MusicProject.SCORE_EDITOR: self.music_tools.score_editor.collect,
            MusicProject.REAL_TIME_SCORE_FOLLOWING: self.music_tools.score_following.collect,
        }
        return collectors[project](ref).as_dict()

    @staticmethod
    def _descriptor(project: str) -> ProjectDescriptor:
        for descriptor in PROJECTS:
            if descriptor.project.value == project:
                return descriptor
        raise OperatorConsoleError(f"unknown project: {project}")

    @staticmethod
    def _validate_ref(ref: str) -> None:
        if not isinstance(ref, str) or not ref.strip():
            raise OperatorConsoleError("ref must be non-empty text")
        if len(ref) > 160 or any(char in ref for char in "\r\n\x00"):
            raise OperatorConsoleError("ref has an invalid format")

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        text = " ".join(str(exc).split()) or exc.__class__.__name__
        return text[:300]
