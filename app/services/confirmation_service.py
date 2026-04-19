from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConfirmationToken
from ..utils import now_utc, random_code


async def create_confirmation(session: AsyncSession, *, action: str, payload: dict, ttl_seconds: int = 300) -> ConfirmationToken:
    token = random_code(24)
    item = ConfirmationToken(
        token=token,
        action=action,
        payload_json=json.dumps(payload, ensure_ascii=False),
        expires_at=now_utc() + timedelta(seconds=ttl_seconds),
        is_used=False,
    )
    session.add(item)
    await session.flush()
    return item


async def use_confirmation(session: AsyncSession, token: str, action: str) -> dict | None:
    item = await session.scalar(select(ConfirmationToken).where(ConfirmationToken.token == token).where(ConfirmationToken.action == action))
    if not item or item.is_used or item.expires_at <= now_utc():
        return None
    item.is_used = True
    await session.flush()
    return json.loads(item.payload_json)
