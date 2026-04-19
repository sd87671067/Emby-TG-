from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from .config import get_settings


def _build_fernet() -> Fernet:
    key = get_settings().APP_MASTER_KEY.encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(text: str) -> str:
    if text == "":
        return ""
    return _build_fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(text: str | None) -> str | None:
    if text is None:
        return None
    if text == "":
        return ""
    return _build_fernet().decrypt(text.encode("utf-8")).decode("utf-8")
