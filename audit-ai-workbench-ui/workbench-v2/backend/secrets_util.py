"""Lightweight secret helpers for local API keys."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
from pathlib import Path

from .db import DATA_DIR


def _secret_file() -> Path:
    path = DATA_DIR / ".workbench_secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def machine_secret() -> bytes:
    env = os.environ.get("WORKBENCH_SECRET", "").strip()
    if env:
        return hashlib.sha256(env.encode("utf-8")).digest()
    secret_path = _secret_file()
    if secret_path.exists():
        return secret_path.read_bytes()
    value = os.urandom(32)
    secret_path.write_bytes(value)
    try:
        os.chmod(secret_path, 0o600)
    except OSError:
        pass
    return value


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    key = machine_secret()
    data = plain.encode("utf-8")
    mixed = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return "enc:" + base64.urlsafe_b64encode(mixed).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if not value.startswith("enc:"):
        return value
    try:
        key = machine_secret()
        mixed = base64.urlsafe_b64decode(value[4:].encode("ascii"))
        data = bytes(b ^ key[i % len(key)] for i, b in enumerate(mixed))
        return data.decode("utf-8")
    except (UnicodeDecodeError, ValueError, binascii.Error):
        return ""


def secret_decryptable(value: str | None) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if not value.startswith("enc:"):
        return True
    return bool(decrypt_secret(value))


def mask_secret(value: str) -> str:
    plain = decrypt_secret(value) if isinstance(value, str) and value.startswith("enc:") else (value or "")
    if not plain:
        return ""
    if len(plain) <= 8:
        return "*" * len(plain)
    return plain[:3] + "*" * (len(plain) - 6) + plain[-3:]
