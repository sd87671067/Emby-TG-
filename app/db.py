from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings
from .models import Base


settings = get_settings()
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        # 兼容旧库：补一个到期前提醒字段
        cols = await conn.execute(text("PRAGMA table_info(managed_users);"))
        col_names = {row[1] for row in cols.fetchall()}
        if "last_notified_soon_expire_at" not in col_names:
            await conn.execute(text("ALTER TABLE managed_users ADD COLUMN last_notified_soon_expire_at DATETIME NULL;"))
