from __future__ import annotations

import re
import subprocess
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_IMAGE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@~-]*$")
_PINNED_IMAGE_REF = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._/:~-]*@sha256:[0-9a-fA-F]{64}$"
)
_SIZE_VALUE = re.compile(r"^[1-9][0-9]*[bkmgBKMG]?$")
_CPU_VALUE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


class SandboxConfigurationError(ValueError):
    pass


class SandboxExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str


class SandboxBackend(Protocol):
    def execute(
        self,
        argv: Sequence[str],
        workspace_root: Path,
        timeout_seconds: float,
        *,
        workspace_writable: bool,
    ) -> SandboxResult: ...


@dataclass(frozen=True, slots=True)
class DockerSandboxConfig:
    image: str
    memory: str = "1g"
    cpus: str = "1.0"
    pids_limit: int = 128
    tmpfs_size: str = "64m"
    require_digest: bool = True

    def __post_init__(self) -> None:
        if not _IMAGE_REF.fullmatch(self.image):
            raise SandboxConfigurationError("sandbox image reference contains invalid characters")
        if self.require_digest and not _PINNED_IMAGE_REF.fullmatch(self.image):
            raise SandboxConfigurationError("sandbox image must be pinned by an exact sha256 digest")
        if not _SIZE_VALUE.fullmatch(self.memory):
            raise SandboxConfigurationError("memory must be a positive Docker size such as 512m or 1g")
        if not _SIZE_VALUE.fullmatch(self.tmpfs_size):
            raise SandboxConfigurationError("tmpfs_size must be a positive Docker size")
        if not _CPU_VALUE.fullmatch(self.cpus) or float(self.cpus) <= 0:
            raise SandboxConfigurationError("cpus must be a positive numeric value")
        if not 16 <= self.pids_limit <= 4096:
            raise SandboxConfigurationError("pids_limit must be between 16 and 4096")


@dataclass(slots=True)
class DockerSandboxBackend:
    config: DockerSandboxConfig
    docker_binary: str = "docker"

    def execute(
        self,
        argv: Sequence[str],
        workspace_root: Path,
        timeout_seconds: float,
        *,
        workspace_writable: bool,
    ) -> SandboxResult:
        args = tuple(argv)
        if not args:
            raise SandboxConfigurationError("sandbox command must not be empty")
        if timeout_seconds <= 0:
            raise SandboxConfigurationError("timeout_seconds must be positive")
        root = workspace_root.resolve()
        if not root.is_dir():
            raise SandboxConfigurationError(f"workspace root is not a directory: {root}")
        if "," in str(root) or "\n" in str(root):
            raise SandboxConfigurationError("workspace path contains unsupported mount characters")

        container_name = f"st-music-agent-{uuid.uuid4().hex[:12]}"
        docker_args = self._build_run_args(
            container_name,
            root,
            args,
            workspace_writable=workspace_writable,
        )

        try:
            completed = subprocess.run(
                docker_args,
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise SandboxExecutionError("Docker executable is unavailable") from exc
        except subprocess.TimeoutExpired as exc:
            self._force_remove(container_name)
            raise SandboxExecutionError("sandbox command timed out") from exc

        return SandboxResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _build_run_args(
        self,
        container_name: str,
        workspace_root: Path,
        argv: Sequence[str],
        *,
        workspace_writable: bool,
    ) -> tuple[str, ...]:
        mount_mode = "" if workspace_writable else ",readonly"
        mount = f"type=bind,source={workspace_root},target=/workspace{mount_mode}"
        return (
            self.docker_binary,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--pids-limit",
            str(self.config.pids_limit),
            "--memory",
            self.config.memory,
            "--cpus",
            self.config.cpus,
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={self.config.tmpfs_size}",
            "--mount",
            mount,
            "--workdir",
            "/workspace",
            "--entrypoint=",
            self.config.image,
            *argv,
        )

    def _force_remove(self, container_name: str) -> None:
        try:
            subprocess.run(
                (self.docker_binary, "rm", "-f", container_name),
                capture_output=True,
                check=False,
                text=True,
                timeout=10.0,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return
