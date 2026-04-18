from __future__ import annotations

import re
import secrets
import string
from datetime import datetime, timezone


USERNAME_RE = re.compile(r"^[A-Za-z0-9]+$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def minutes_until(dt: datetime) -> int:
    return int((as_utc(dt) - now_utc()).total_seconds() // 60)


def days_until(dt: datetime) -> int:
    return int((as_utc(dt) - now_utc()).total_seconds() // 86400)


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_RE.fullmatch(username))


def random_code(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def fmt_expire(dt: datetime) -> str:
    return as_utc(dt).astimezone().strftime("%Y-%m-%d %H:%M")


def chunk_lines(lines: list[str], max_chars: int = 3500) -> list[str]:
    chunks: list[str] = []
    buffer: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if buffer and current_len + line_len > max_chars:
            chunks.append("\n".join(buffer))
            buffer = [line]
            current_len = line_len
        else:
            buffer.append(line)
            current_len += line_len
    if buffer:
        chunks.append("\n".join(buffer))
    return chunks


def is_expired(dt: datetime) -> bool:
    return as_utc(dt) <= now_utc()
