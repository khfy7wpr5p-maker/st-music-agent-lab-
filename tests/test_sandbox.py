import subprocess
from pathlib import Path

import pytest

from st_music_agent.sandbox import (
    DockerSandboxBackend,
    DockerSandboxConfig,
    SandboxConfigurationError,
)


PINNED_IMAGE = "example/st-music-agent@sha256:" + ("0" * 64)


def test_docker_image_requires_digest_pin() -> None:
    with pytest.raises(SandboxConfigurationError, match="sha256"):
        DockerSandboxConfig(image="example/st-music-agent:latest")


def test_docker_backend_builds_hardened_read_only_run(tmp_path: Path) -> None:
    backend = DockerSandboxBackend(DockerSandboxConfig(image=PINNED_IMAGE))

    args = backend._build_run_args(
        "st-music-agent-test",
        tmp_path.resolve(),
        ("git", "status", "--short"),
        workspace_writable=False,
    )

    assert args[:5] == ("docker", "run", "--rm", "--name", "st-music-agent-test")
    assert args[5:7] == ("--network", "none")
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges:true" in args
    assert "--read-only" in args
    assert "--tmpfs" in args
    assert "--entrypoint=" in args
    assert f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly" in args
    assert args[-4:] == (PINNED_IMAGE, "git", "status", "--short")


def test_docker_backend_builds_writable_validation_mount(tmp_path: Path) -> None:
    backend = DockerSandboxBackend(DockerSandboxConfig(image=PINNED_IMAGE))

    args = backend._build_run_args(
        "st-music-agent-test",
        tmp_path.resolve(),
        ("pytest", "-q"),
        workspace_writable=True,
    )

    assert f"type=bind,source={tmp_path.resolve()},target=/workspace" in args
    assert f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly" not in args
    assert args[-3:] == (PINNED_IMAGE, "pytest", "-q")


def test_docker_backend_executes_without_shell_and_returns_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def fake_run(args: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, dict(kwargs)))
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr("st_music_agent.sandbox.subprocess.run", fake_run)
    backend = DockerSandboxBackend(DockerSandboxConfig(image=PINNED_IMAGE))

    result = backend.execute(
        ("pytest", "-q"),
        tmp_path,
        30.0,
        workspace_writable=True,
    )

    assert result.returncode == 0
    assert result.stdout == "ok"
    docker_args, kwargs = calls[0]
    assert docker_args[0:2] == ("docker", "run")
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is False
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 30.0
    assert "shell" not in kwargs
