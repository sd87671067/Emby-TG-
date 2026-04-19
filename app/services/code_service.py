from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import InviteCode
from ..utils import now_utc, random_code


async def create_codes(session: AsyncSession, *, expire_days: int, count: int, length: int) -> list[InviteCode]:
    items: list[InviteCode] = []
    for _ in range(count):
        code = random_code(length)
        item = InviteCode(code=code, expire_days=expire_days)
        session.add(item)
        items.append(item)
    await session.flush()
    return items


async def list_available_codes(session: AsyncSession) -> list[InviteCode]:
    result = await session.scalars(select(InviteCode).where(InviteCode.is_used.is_(False)).order_by(InviteCode.id.desc()))
    return list(result.all())


async def validate_code(session: AsyncSession, code: str) -> InviteCode | None:
    return await session.scalar(select(InviteCode).where(InviteCode.code == code).where(InviteCode.is_used.is_(False)))


async def use_code(session: AsyncSession, code: str, username: str, tg_user_id: int | None) -> InviteCode | None:
    invite = await validate_code(session, code)
    if not invite:
        return None
    invite.is_used = True
    invite.used_by_username = username
    invite.used_by_tg_user_id = tg_user_id
    invite.used_at = now_utc()
    await session.flush()
    return invite


async def clear_codes(session: AsyncSession) -> int:
    rows = await list_available_codes(session)
    count = len(rows)
    await session.execute(delete(InviteCode).where(InviteCode.is_used.is_(False)))
    await session.flush()
    return count
