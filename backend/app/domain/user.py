"""
Domain layer – User entity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4
import hashlib
import secrets


@dataclass
class User:
    id: UUID
    email: str
    hashed_password: str
    is_active: bool
    created_at: datetime

    @staticmethod
    def create(email: str, plain_password: str) -> "User":
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256(f"{salt}{plain_password}".encode()).hexdigest()
        return User(
            id=uuid4(),
            email=email.lower().strip(),
            hashed_password=f"{salt}:{hashed}",
            is_active=True,
            created_at=datetime.utcnow(),
        )

    def verify_password(self, plain_password: str) -> bool:
        try:
            salt, hashed = self.hashed_password.split(":", 1)
            expected = hashlib.sha256(f"{salt}{plain_password}".encode()).hexdigest()
            return secrets.compare_digest(expected, hashed)
        except ValueError:
            return False
