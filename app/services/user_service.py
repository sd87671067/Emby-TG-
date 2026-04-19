from __future__ import annotations

import asyncio
from datetime import timedelta

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..emby import EmbyClient, EmbyError
from ..models import ManagedUser
from ..security import decrypt_text, encrypt_text
from ..utils import now_utc


async def get_local_user_by_username(session: AsyncSession, username: str) -> ManagedUser | None:
    return await session.scalar(
        select(ManagedUser).where(ManagedUser.username == username).where(ManagedUser.is_deleted.is_(False))
    )


async def get_local_user_by_username_any(session: AsyncSession, username: str) -> ManagedUser | None:
    return await session.scalar(select(ManagedUser).where(ManagedUser.username == username).order_by(ManagedUser.id.desc()))


async def get_or_repair_local_user_by_tg_user_id(session: AsyncSession, tg_user_id: int) -> ManagedUser | None:
    user = await session.scalar(
        select(ManagedUser)
        .where(ManagedUser.telegram_user_id == tg_user_id)
        .where(ManagedUser.is_deleted.is_(False))
        .order_by(ManagedUser.id.desc())
    )
    return user


async def create_registered_user(
    session: AsyncSession,
    *,
    settings: Settings,
    emby_client: EmbyClient,
    username: str,
    password: str | None,
    tg_user_id: int | None,
    expire_days: int,
    source: str = "register",
) -> ManagedUser:
    expire_at = now_utc() + timedelta(days=expire_days)
    emby_user = await emby_client.ensure_user(username, password=password or "")

    exists_any = await get_local_user_by_username_any(session, username)
    if exists_any:
        exists_any.password_encrypted = encrypt_text(password) if password else None
        exists_any.emby_user_id = emby_user["Id"]
        exists_any.telegram_user_id = tg_user_id
        exists_any.source = source
        exists_any.expire_at = expire_at
        exists_any.is_deleted = False
        exists_any.deleted_at = None
        exists_any.last_notified_expired_at = None
        exists_any.last_notified_soon_expire_at = None
        await session.flush()
        return exists_any

    obj = ManagedUser(
        username=username,
        password_encrypted=encrypt_text(password) if password else None,
        emby_user_id=emby_user["Id"],
        telegram_user_id=tg_user_id,
        source=source,
        expire_at=expire_at,
        is_deleted=False,
    )
    session.add(obj)
    await session.flush()
    return obj


async def renew_user_with_code(session: AsyncSession, *, username: str, tg_user_id: int, code: str) -> ManagedUser:
    from .code_service import use_code

    user = await get_local_user_by_username(session, username)
    if not user:
        raise ValueError("用户不存在")
    invite = await use_code(session, code, username, tg_user_id)
    if not invite:
        raise ValueError("注册码/续期码无效或已被使用")
    base_time = user.expire_at if user.expire_at > now_utc() else now_utc()
    user.expire_at = base_time + timedelta(days=invite.expire_days)
    user.last_notified_soon_expire_at = None
    user.last_notified_expired_at = None
    await session.flush()
    return user


async def delete_user_everywhere(session: AsyncSession, *, username: str, emby_client: EmbyClient) -> tuple[bool, str]:
    user = await get_local_user_by_username(session, username)
    if not user:
        return False, "本地未找到该用户"

    emby_user = None
    if user.emby_user_id:
        try:
            emby_user = await emby_client.get_user_by_id(user.emby_user_id)
        except Exception:
            emby_user = None
    if not emby_user:
        emby_user = await emby_client.get_user_by_name(username)

    if emby_user:
        await emby_client.delete_user(emby_user["Id"])

    user.is_deleted = True
    user.deleted_at = now_utc()
    user.telegram_user_id = None
    await session.flush()
    return True, f"已删除用户：{username}"


async def update_user_expire_days(session: AsyncSession, *, username: str, delta_days: int) -> ManagedUser:
    user = await get_local_user_by_username(session, username)
    if not user:
        raise ValueError("用户不存在")
    user.expire_at = user.expire_at + timedelta(days=delta_days)
    user.last_notified_soon_expire_at = None
    user.last_notified_expired_at = None
    await session.flush()
    return user


async def get_expired_users_need_notify(session: AsyncSession) -> list[ManagedUser]:
    result = await session.scalars(
        select(ManagedUser)
        .where(ManagedUser.is_deleted.is_(False))
        .where(ManagedUser.expire_at <= now_utc())
    )
    return list(result.all())


async def get_soon_expire_users_need_notify(session: AsyncSession, *, days: int) -> list[ManagedUser]:
    end_time = now_utc() + timedelta(days=days)
    result = await session.scalars(
        select(ManagedUser)
        .where(ManagedUser.is_deleted.is_(False))
        .where(ManagedUser.expire_at > now_utc())
        .where(ManagedUser.expire_at <= end_time)
        .where(ManagedUser.last_notified_soon_expire_at.is_(None))
    )
    return list(result.all())


async def mark_soon_expire_notified(session: AsyncSession, username: str) -> None:
    user = await get_local_user_by_username(session, username)
    if user:
        user.last_notified_soon_expire_at = now_utc()
        await session.flush()


async def sync_emby_users_to_local(session: AsyncSession, *, settings: Settings, emby_client: EmbyClient) -> dict[str, object]:
    emby_users = await emby_client.get_users()
    all_local_users = list((await session.scalars(select(ManagedUser).order_by(ManagedUser.id.desc()))).all())
    ignore_set = settings.emby_import_ignore_usernames
    seen_emby_names: set[str] = set()
    default_password_encrypted = encrypt_text(settings.EMBY_SYNC_LOCAL_DEFAULT_PASSWORD)

    local_by_lower: dict[str, ManagedUser] = {}
    for user in all_local_users:
        lower_name = (user.username or "").strip().lower()
        if lower_name and lower_name not in local_by_lower:
            local_by_lower[lower_name] = user

    created = 0
    updated = 0
    deleted = 0
    ignored = 0
    deleted_usernames: list[str] = []

    for item in emby_users:
        username = str(item.get("Name", "")).strip()
        if not username:
            ignored += 1
            continue
        lower_name = username.lower()
        if lower_name in ignore_set:
            ignored += 1
            continue
        seen_emby_names.add(lower_name)
        exists = local_by_lower.get(lower_name)
        if exists:
            exists.username = username
            exists.emby_user_id = item.get("Id")
            exists.password_encrypted = default_password_encrypted
            exists.source = "emby_sync"
            exists.is_deleted = False
            exists.deleted_at = None
            exists.telegram_user_id = exists.telegram_user_id
            if exists.expire_at is None:
                exists.expire_at = now_utc() + timedelta(days=settings.DEFAULT_USER_EXPIRE_DAYS)
            updated += 1
            continue
        obj = ManagedUser(
            username=username,
            password_encrypted=default_password_encrypted,
            emby_user_id=item.get("Id"),
            source="emby_sync",
            expire_at=now_utc() + timedelta(days=settings.DEFAULT_USER_EXPIRE_DAYS),
            is_deleted=False,
        )
        session.add(obj)
        local_by_lower[lower_name] = obj
        created += 1

    for user in all_local_users:
        lower_name = (user.username or "").strip().lower()
        if not lower_name or lower_name in ignore_set:
            continue
        if lower_name not in seen_emby_names:
            deleted_usernames.append(user.username)
            await session.delete(user)
            deleted += 1

    await session.flush()
    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "deleted_usernames": sorted(deleted_usernames),
        "ignored": ignored,
        "local_password": settings.EMBY_SYNC_LOCAL_DEFAULT_PASSWORD,
    }


async def import_local_users_to_emby(session: AsyncSession, *, settings: Settings, emby_client: EmbyClient) -> dict[str, object]:
    users = list((await session.scalars(select(ManagedUser).where(ManagedUser.is_deleted.is_(False)).order_by(ManagedUser.id.asc()))).all())
    imported_names: list[str] = []
    skipped_names: list[str] = []

    emby_users = await emby_client.get_users()
    emby_name_map = {str(u.get('Name', '')).lower(): u for u in emby_users if u.get('Name')}

    for user in users:
        if user.username.lower() in settings.emby_import_ignore_usernames:
            skipped_names.append(user.username)
            continue
        if user.username.lower() in emby_name_map:
            skipped_names.append(user.username)
            continue
        password = decrypt_text(user.password_encrypted) or settings.EMBY_SYNC_LOCAL_DEFAULT_PASSWORD
        try:
            emby_user = await emby_client.ensure_user(user.username, password=password)
            user.emby_user_id = emby_user['Id']
            imported_names.append(user.username)
            await asyncio.sleep(settings.EMBY_PUSH_SYNC_DELAY_SECONDS)
        except EmbyError:
            skipped_names.append(user.username)
            continue

    await session.flush()
    return {
        'imported_count': len(imported_names),
        'skipped_count': len(skipped_names),
        'imported_names': imported_names,
        'skipped_names': skipped_names,
    }


async def notify_admin_register_success(settings: Settings, username: str, expire_text: str) -> None:
    if not settings.ADMIN_BOT_TOKEN or not settings.admin_chat_id_list:
        return
    admin_bot = Bot(token=settings.ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        for admin_chat_id in settings.admin_chat_id_list:
            await admin_bot.send_message(admin_chat_id, f"客户端注册成功\n账号：<b>{username}</b>\n到期时间：<b>{expire_text}</b>")
    finally:
        await admin_bot.session.close()


async def notify_admin_renew_success(settings: Settings, username: str, expire_text: str) -> None:
    if not settings.ADMIN_BOT_TOKEN or not settings.admin_chat_id_list:
        return
    admin_bot = Bot(token=settings.ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        for admin_chat_id in settings.admin_chat_id_list:
            await admin_bot.send_message(admin_chat_id, f"客户端续期成功\n账号：<b>{username}</b>\n新的到期时间：<b>{expire_text}</b>")
    finally:
        await admin_bot.session.close()
