from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

ITERATIONS = 310_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, expected: str, salt_hex: str) -> bool:
    digest, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(digest, expected)


def create_token() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = iso(utc_now() + timedelta(days=30))
    return token, token_hash, expires_at


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
