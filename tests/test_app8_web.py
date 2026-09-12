from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from st_music_agent.app8_coordination import CrossProjectPlan, ProjectWorkItem
from st_music_agent.app8_graph_state import App8GraphStore, coordination_graph_id
from st_music_agent.app8_supervision import MutationClass
from st_music_agent.app8_web_app import App8OperatorConsoleApplication
from st_music_agent.music_evidence import MusicProject
from st_music_agent.operator_console import OperatorConsoleService
from st_music_agent.task_execution import TaskExecutionConfig

TOKEN = "r" * 32


class FakeTaskService:
    def __init__(self) -> None:
        self.config = TaskExecutionConfig(enabled=False)

    def recent_tasks(self):
        return []


def plan() -> CrossProjectPlan:
    return CrossProjectPlan(
        plan_id="web-graph",
        items=(
            ProjectWorkItem(
                item_id="01-restore",
                project=MusicProject.SCORE_RESTORE,
                repository="khfy7wpr5p-maker/st-score-restore-engine",
                expected_base_sha="a" * 40,
                instruction="Inspect restore state.",
                dependencies=(),
                required_upstream_evidence=(),
                produces_evidence=("restore_evidence",),
                mutation_class=MutationClass.READ_ONLY,
            ),
            ProjectWorkItem(
                item_id="02-tab",
                project=MusicProject.MUSICXML_GUITAR_TAB,
                repository="khfy7wpr5p-maker/musicxml-to-guitar-tab-engine",
                expected_base_sha="b" * 40,
                instruction="Inspect TAB state.",
                dependencies=("01-restore",),
                required_upstream_evidence=("restore_evidence",),
                produces_evidence=("tab_evidence",),
                mutation_class=MutationClass.READ_ONLY,
            ),
        ),
    )


def app(tmp_path, *, remote: bool = False) -> tuple[App8OperatorConsoleApplication, str]:
    store = App8GraphStore(tmp_path / "graphs.jsonl")
    graph = plan()
    graph_id = store.register_coordination(graph)
    digest = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest() if remote else None
    application = App8OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        FakeTaskService(),
        store,
        session_token="local-session",
        remote_read_only=remote,
        remote_auth_digest=digest,
    )
    return application, graph_id


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_root_exposes_app8e_graph_console(tmp_path) -> None:
    application, _ = app(tmp_path)

    response = application.dispatch("GET", "/")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert "APP8E Supervision Graph Console" in body
    assert "APP8 supervision graphs" in body


def test_local_graph_list_detail_and_verify_are_read_only(tmp_path) -> None:
    application, graph_id = app(tmp_path)

    listing = application.dispatch("GET", "/api/app8/graphs?limit=10")
    detail = application.dispatch("GET", f"/api/app8/graphs/{graph_id}")
    verify = application.dispatch("GET", f"/api/app8/graphs/{graph_id}/verify")
    blocked_post = application.dispatch("POST", "/api/app8/graphs")

    assert listing.status == 200
    listing_payload = json.loads(listing.body)
    assert listing_payload["graphs"][0]["graph_id"] == coordination_graph_id(plan())
    assert listing_payload["graph_mutations_enabled"] is False

    assert detail.status == 200
    detail_payload = json.loads(detail.body)
    assert detail_payload["graph_id"] == graph_id
    assert detail_payload["resume_scope"] == "deterministic_state_reconstruction_only"
    assert detail_payload["repository_mutation_authorized"] is False
    assert detail_payload["merge_authorized"] is False

    assert verify.status == 200
    verify_payload = json.loads(verify.body)
    assert verify_payload["verified"] is True
    assert verify_payload["status"] == "VERIFIED"
    assert verify_payload["production_actions_authorized"] is False

    assert blocked_post.status == 405
    assert json.loads(blocked_post.body)["error"] == "app8_graphs_read_only"


def test_remote_graph_surface_requires_existing_app7_bearer_auth(tmp_path) -> None:
    application, graph_id = app(tmp_path, remote=True)

    denied_list = application.dispatch("GET", "/api/app8/graphs")
    denied_detail = application.dispatch("GET", f"/api/app8/graphs/{graph_id}")
    allowed = application.dispatch("GET", "/api/app8/graphs", headers=auth())
    post = application.dispatch("POST", "/api/app8/graphs", headers=auth())

    assert denied_list.status == 401
    assert denied_detail.status == 401
    assert allowed.status == 200
    assert post.status == 405
    assert json.loads(post.body)["error"] == "app8_graphs_read_only"


def test_graph_id_with_slash_is_rejected(tmp_path) -> None:
    application, _ = app(tmp_path)

    response = application.dispatch("GET", "/api/app8/graphs/coordination:web/extra")

    assert response.status == 404
