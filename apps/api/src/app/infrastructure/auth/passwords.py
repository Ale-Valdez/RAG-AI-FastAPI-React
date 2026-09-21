from __future__ import annotations

from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import VerifyMismatchError


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except VerifyMismatchError:
            return False
