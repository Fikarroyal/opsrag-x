"""Authentication primitives: password hashing (PBKDF2-SHA256), signed session tokens (HMAC-SHA256), login throttling.

Standard library only. Tokens are `base64url(payload).base64url(signature)`; payload = {"sub": user_id, "exp": unix_ts}.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "opsragx_session"
_PBKDF2_ROUNDS = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, rounds, salt_b64, digest_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt_b64), int(rounds))
        return hmac.compare_digest(digest, _unb64(digest_b64))
    except (ValueError, TypeError):
        return False


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


_secret_cache: dict[str, bytes] = {}


def get_secret(settings: Settings) -> bytes:
    """SECRET_KEY if configured, otherwise a random key generated once and kept in <data_dir>/.secret_key."""
    if settings.secret_key:
        return settings.secret_key.encode("utf-8")
    path = Path(settings.data_dir) / ".secret_key"
    cached = _secret_cache.get(str(path))
    if cached:
        return cached
    try:
        if path.is_file():
            value = path.read_text().strip().encode("utf-8")
        else:
            value = secrets.token_hex(32).encode("utf-8")
            path.write_text(value.decode("ascii"))
            path.chmod(0o600)
    except OSError:
        logger.warning("cannot persist session secret; sessions will reset on restart (set SECRET_KEY)")
        value = secrets.token_hex(32).encode("utf-8")
    _secret_cache[str(path)] = value
    return value


def make_token(user_id: str, settings: Settings) -> str:
    payload = _b64(
        json.dumps({"sub": user_id, "exp": int(time.time()) + settings.session_ttl_hours * 3600}, separators=(",", ":")).encode()
    )
    sig = _b64(hmac.new(get_secret(settings), payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str | None, settings: Settings) -> str | None:
    """Return the user id for a valid, unexpired token; otherwise None."""
    if not token or token.count(".") != 1:
        return None
    payload, sig = token.split(".")
    expected = _b64(hmac.new(get_secret(settings), payload.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
        if int(data["exp"]) < time.time():
            return None
        return str(data["sub"])
    except (ValueError, KeyError, TypeError):
        return None


class LoginThrottle:
    """Allow at most `limit` failed sign-ins per key (email + client ip) in `window` seconds."""

    def __init__(self, limit: int = 8, window: int = 300) -> None:
        self.limit, self.window = limit, window
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.time() - self.window
        recent = [t for t in self._fails.get(key, []) if t > cutoff]
        self._fails[key] = recent
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
