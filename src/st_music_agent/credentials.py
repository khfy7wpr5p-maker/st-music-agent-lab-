from __future__ import annotations

import os
from dataclasses import dataclass


class MissingCredentialError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EnvCredential:
    """Resolve a secret only at an adapter boundary.

    The environment variable name is safe to keep in configuration. The resolved
    secret should be used transiently and must not be copied into core task state.
    """

    name: str

    def resolve(self) -> str:
        value = os.environ.get(self.name, "")
        if not value:
            raise MissingCredentialError(f"required credential environment variable is unset: {self.name}")
        return value
