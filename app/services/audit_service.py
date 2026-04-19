from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog


async def add_audit(session: AsyncSession, actor: str, action: str, detail: str) -> AuditLog:
    obj = AuditLog(actor=actor, action=action, detail=detail)
    session.add(obj)
    await session.flush()
    return obj
