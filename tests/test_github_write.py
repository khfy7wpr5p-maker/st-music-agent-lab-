import unittest

from st_music_agent_lab.github_write import (
    GitHubLabWriteAdapter,
    GitHubRestLabWriteBackend,
    GitHubWriteError,
)
from st_music_agent_lab.models import Action, AuthorityMode, TaskSpec


LAB = "khfy7wpr5p-maker/st-music-agent-lab-"
BASE_SHA = "a" * 40
BLOB_SHA = "b" * 40
COMMIT_SHA = "c" * 40


class FakeWriteBackend:
    def __init__(self):
        self.calls = []

    def post_json(self, path, payload):
        self.calls.append(("POST", path, dict(payload)))
        if path.endswith("/git/refs"):
            return {"object": {"sha": payload["sha"]}}
        if path.endswith("/pulls"):
            return {"number": 7, "head": {"sha": COMMIT_SHA}}
        raise AssertionError(path)

    def put_json(self, path, payload):
        self.calls.append(("PUT", path, dict(payload)))
        return {"commit": {"sha": COMMIT_SHA}}


def make_task(**overrides):
    values = dict(
        task_id="a5-test",
        objective="Exercise bounded lab-only GitHub mutation",
        target_repository=LAB,
        base_ref="a4/github-read-only-adapter",
        mode=AuthorityMode.PR_WRITE,
        capabilities=frozenset(
            {
                Action.CREATE_NON_DEFAULT_TASK_BRANCH,
                Action.WRITE_BOUNDED_TASK_FILES,
                Action.COMMIT_TO_TASK_BRANCH,
                Action.OPEN_PULL_REQUEST,
                Action.BOUNDED_CI_REPAIR,
            }
        ),
        allowed_paths=("fixtures/a5",),
        retry_budget=1,
    )
    values.update(overrides)
    return TaskSpec(**values)


class GitHubLabWriteAdapterTests(unittest.TestCase):
    def test_full_branch_file_pr_flow_is_bounded(self):
        backend = FakeWriteBackend()
        writer = GitHubLabWriteAdapter(make_task(), backend, lab_repository=LAB)

        branch = writer.create_task_branch("agent/a5-fixture", base_sha=BASE_SHA)
        mutation = writer.write_file(
            "agent/a5-fixture",
            "fixtures/a5/result.txt",
            "green\n",
            message="A5 fixture: write result",
        )
        pr = writer.open_pull_request(
            "agent/a5-fixture",
            title="A5 fixture green PR",
            body="Bounded fixture.",
        )

        self.assertEqual(branch.commit_sha, BASE_SHA)
        self.assertEqual(mutation.commit_sha, COMMIT_SHA)
        self.assertEqual(pr.pull_request, 7)
        self.assertEqual([call[0] for call in backend.calls], ["POST", "PUT", "POST"])
        self.assertEqual(backend.calls[0][2]["ref"], "refs/heads/agent/a5-fixture")
        self.assertEqual(backend.calls[1][2]["branch"], "agent/a5-fixture")
        self.assertEqual(backend.calls[2][2]["base"], "a4/github-read-only-adapter")

    def test_cross_repository_task_is_rejected_before_backend_use(self):
        backend = FakeWriteBackend()
        with self.assertRaises(PermissionError):
            GitHubLabWriteAdapter(
                make_task(target_repository="other/repository"),
                backend,
                lab_repository=LAB,
            )
        self.assertEqual(backend.calls, [])

    def test_default_or_non_agent_branch_is_rejected(self):
        backend = FakeWriteBackend()
        writer = GitHubLabWriteAdapter(make_task(), backend, lab_repository=LAB)
        for branch in ("main", "master", "feature/freeform", "agent/../escape"):
            with self.subTest(branch=branch):
                with self.assertRaises(PermissionError):
                    writer.create_task_branch(branch, base_sha=BASE_SHA)
        self.assertEqual(backend.calls, [])

    def test_path_outside_taskspec_is_rejected(self):
        backend = FakeWriteBackend()
        writer = GitHubLabWriteAdapter(make_task(), backend, lab_repository=LAB)
        with self.assertRaises(PermissionError):
            writer.write_file(
                "agent/a5-fixture",
                "src/unsafe.py",
                "x = 1\n",
                message="unsafe",
            )
        self.assertEqual(backend.calls, [])

    def test_update_requires_exact_blob_sha_when_supplied(self):
        backend = FakeWriteBackend()
        writer = GitHubLabWriteAdapter(make_task(), backend, lab_repository=LAB)
        with self.assertRaises(ValueError):
            writer.write_file(
                "agent/a5-fixture",
                "fixtures/a5/result.txt",
                "updated\n",
                message="update fixture",
                expected_sha="short",
            )
        self.assertEqual(backend.calls, [])

        writer.write_file(
            "agent/a5-fixture",
            "fixtures/a5/result.txt",
            "updated\n",
            message="update fixture",
            expected_sha=BLOB_SHA,
        )
        self.assertEqual(backend.calls[0][2]["sha"], BLOB_SHA)

    def test_ci_repair_budget_is_hard_capped(self):
        writer = GitHubLabWriteAdapter(make_task(), FakeWriteBackend(), lab_repository=LAB)
        self.assertEqual(writer.claim_ci_repair_attempt(), 1)
        with self.assertRaises(PermissionError):
            writer.claim_ci_repair_attempt()

    def test_read_only_mode_cannot_gain_write_authority(self):
        task = make_task(mode=AuthorityMode.READ_ONLY)
        writer = GitHubLabWriteAdapter(task, FakeWriteBackend(), lab_repository=LAB)
        with self.assertRaises(PermissionError):
            writer.create_task_branch("agent/a5-fixture", base_sha=BASE_SHA)

    def test_rest_backend_exposes_only_a5_routes(self):
        backend = GitHubRestLabWriteBackend(LAB, token="runtime-token")
        root = f"/repos/{LAB}"
        backend._validate_route("POST", f"{root}/git/refs")
        backend._validate_route("POST", f"{root}/pulls")
        backend._validate_route("PUT", f"{root}/contents/fixtures/a5/result.txt")
        for method, path in (
            ("PATCH", f"{root}/git/refs/heads/main"),
            ("DELETE", f"{root}/contents/README.md"),
            ("PUT", f"{root}/actions/secrets/SECRET"),
            ("POST", f"{root}/merges"),
            ("POST", "/repos/other/repository/git/refs"),
        ):
            with self.subTest(method=method, path=path):
                with self.assertRaises(GitHubWriteError):
                    backend._validate_route(method, path)

    def test_file_size_limit_blocks_before_backend_use(self):
        backend = FakeWriteBackend()
        writer = GitHubLabWriteAdapter(make_task(), backend, lab_repository=LAB)
        with self.assertRaises(ValueError):
            writer.write_file(
                "agent/a5-fixture",
                "fixtures/a5/large.txt",
                "x" * 256_001,
                message="large fixture",
            )
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
