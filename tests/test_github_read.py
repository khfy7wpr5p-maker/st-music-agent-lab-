import base64
import unittest

from st_music_agent_lab.github_read import GitHubReadAdapter, GitHubReadError, GitHubRestReadBackend
from st_music_agent_lab.models import Action, AuthorityMode, TaskSpec


class FakeBackend:
    def __init__(self):
        self.json_calls = []
        self.text_calls = []

    def get_json(self, path):
        self.json_calls.append(path)
        if path.endswith("/pulls/7"):
            return {
                "number": 7,
                "state": "open",
                "head": {"sha": "a" * 40},
                "base": {"ref": "main"},
            }
        if "/actions/runs?" in path:
            return {
                "workflow_runs": [
                    {"name": "foundation", "status": "completed", "conclusion": "success"},
                    {"name": "compatibility", "status": "completed", "conclusion": "failure"},
                ]
            }
        if "/contents/README.md" in path:
            return {
                "path": "README.md",
                "sha": "b" * 40,
                "size": 5,
                "encoding": "base64",
                "content": base64.b64encode(b"hello").decode("ascii"),
            }
        if "/branches/" in path:
            return {"name": "main", "commit": {"sha": "c" * 40}}
        if "/commits/" in path:
            return {"sha": "c" * 40}
        return {"full_name": "owner/repo", "default_branch": "main"}

    def get_text(self, path, *, accept):
        self.text_calls.append((path, accept))
        return "diff --git a/a.py b/a.py\n+changed\n"


def make_task(*capabilities):
    return TaskSpec(
        task_id="A4-fixture",
        objective="Inspect a failing pull request without mutation",
        target_repository="owner/repo",
        mode=AuthorityMode.READ_ONLY,
        capabilities=frozenset(capabilities),
    )


class GitHubReadAdapterTests(unittest.TestCase):
    def test_repository_file_and_branch_reads_are_policy_gated(self):
        backend = FakeBackend()
        adapter = GitHubReadAdapter(make_task(Action.READ_REPOSITORY), backend)

        self.assertEqual(adapter.repository().payload["full_name"], "owner/repo")
        self.assertEqual(adapter.file("README.md").payload["content"], "hello")
        self.assertEqual(adapter.branch("main").payload["name"], "main")
        self.assertEqual(adapter.commit("c" * 40).payload["sha"], "c" * 40)

    def test_missing_read_capability_is_denied(self):
        adapter = GitHubReadAdapter(make_task(Action.PRODUCE_REPORTS), FakeBackend())
        with self.assertRaises(PermissionError):
            adapter.repository()

    def test_pull_request_diff_uses_get_only_backend_surface(self):
        backend = FakeBackend()
        adapter = GitHubReadAdapter(make_task(Action.INSPECT_PULL_REQUESTS), backend)
        evidence = adapter.pull_request_diff(7)
        self.assertIn("diff --git", evidence.payload["diff"])
        self.assertEqual(backend.text_calls[0][1], "application/vnd.github.diff")
        self.assertFalse(hasattr(backend, "post"))
        self.assertFalse(hasattr(backend, "patch"))

    def test_diagnostic_reports_failed_workflow_with_evidence_locators(self):
        adapter = GitHubReadAdapter(
            make_task(Action.INSPECT_PULL_REQUESTS, Action.INSPECT_CI),
            FakeBackend(),
        )
        diagnostic = adapter.diagnose_pull_request(7)

        self.assertEqual(diagnostic.state, "OPEN")
        self.assertEqual(diagnostic.ci_state, "FAILED")
        self.assertEqual(diagnostic.failing_runs, ("compatibility",))
        self.assertEqual(diagnostic.head_sha, "a" * 40)
        self.assertEqual(len(diagnostic.evidence_locators), 2)

    def test_workflow_lookup_rejects_non_sha(self):
        adapter = GitHubReadAdapter(make_task(Action.INSPECT_CI), FakeBackend())
        with self.assertRaises(ValueError):
            adapter.workflow_runs_for_commit("main")

    def test_file_path_traversal_is_rejected(self):
        adapter = GitHubReadAdapter(make_task(Action.READ_REPOSITORY), FakeBackend())
        with self.assertRaises(ValueError):
            adapter.file("../secret")

    def test_evidence_digest_is_deterministic(self):
        adapter = GitHubReadAdapter(make_task(Action.READ_REPOSITORY), FakeBackend())
        first = adapter.repository()
        second = adapter.repository()
        self.assertEqual(first.digest, second.digest)


class GitHubRestReadBackendTests(unittest.TestCase):
    def test_repository_scope_is_required(self):
        with self.assertRaises(ValueError):
            GitHubRestReadBackend("not-a-repository")

    def test_backend_rejects_path_outside_configured_repository_before_network(self):
        backend = GitHubRestReadBackend("owner/repo")
        with self.assertRaises(GitHubReadError):
            backend.get_json("/repos/other/repo")


if __name__ == "__main__":
    unittest.main()
