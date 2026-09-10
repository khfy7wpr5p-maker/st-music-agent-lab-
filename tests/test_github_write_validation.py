from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from st_music_agent.github_write import GitHubMutationClient, GitHubMutationConfig
from st_music_agent.transport import JsonRequest, JsonResponse


@dataclass
class RecordingTransport:
    requests: list[JsonRequest] = field(default_factory=list)

    def request(self, request: JsonRequest) -> JsonResponse:
        self.requests.append(request)
        raise AssertionError("validation must fail before network access")


def client(transport: RecordingTransport) -> GitHubMutationClient:
    return GitHubMutationClient(
        GitHubMutationConfig(repository="owner/repo", token_env="ST_GITHUB_TOKEN"),
        transport=transport,
    )


@pytest.mark.parametrize(
    "branch",
    (
        "HEAD",
        "head",
        "refs/heads/main",
        "heads/main",
        "feature//nested",
        "feature/../main",
        ".hidden",
        "feature/.hidden",
        "feature/bad.lock",
    ),
)
def test_branch_alias_and_invalid_ref_forms_fail_before_network(branch: str) -> None:
    transport = RecordingTransport()

    with pytest.raises(ValueError, match="branch name is invalid"):
        client(transport).create_branch(branch, "a" * 40)

    assert transport.requests == []


@pytest.mark.parametrize(
    "path",
    (
        "src\\escape.py",
        "src//double.py",
        "../escape.py",
        "src/../escape.py",
    ),
)
def test_invalid_write_paths_fail_before_network(path: str) -> None:
    transport = RecordingTransport()

    with pytest.raises(ValueError, match="GitHub file path is invalid"):
        client(transport).write_file(
            path=path,
            content="safe",
            commit_message="test validation",
            branch="feature/a9",
        )

    assert transport.requests == []
