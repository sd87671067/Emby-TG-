from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..config import Settings
from ..emby import EmbyClient
from ..models import ManagedUser
from ..services.audit_service import add_audit
from ..services.code_service import clear_codes, create_codes, list_available_codes
from ..services.user_service import (
    delete_user_everywhere,
    get_local_user_by_username,
    import_local_users_to_emby,
    sync_emby_users_to_local,
    update_user_expire_days,
)
from ..utils import chunk_lines, days_until, fmt_expire, now_utc
from .shared import admin_main_keyboard

logger = logging.getLogger("app.admin_bot")


class AdminStates(StatesGroup):
    waiting_generate = State()
    waiting_delete_username = State()
    waiting_modify_username = State()
    waiting_modify_days = State()


def _build_user_page(rows: list[str], page: int, total_pages: int) -> InlineKeyboardMarkup | None:
    if total_pages <= 1:
        return None
    buttons = []
    row = []
    if page > 1:
        row.append(InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"users_page:{page-1}"))
    if page < total_pages:
        row.append(InlineKeyboardButton(text="下一页 ➡️", callback_data=f"users_page:{page+1}"))
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_bot(
    *,
    settings: Settings,
    session_factory: async_sessionmaker,
    emby_client: EmbyClient,
) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    router = Router()
    dp.include_router(router)

    async def ensure_admin(message: Message) -> bool:
        return message.from_user and message.from_user.id in settings.admin_chat_id_list

    async def send_home(message: Message, text: str = "欢迎使用管理员机器人。") -> None:
        await message.answer(text, reply_markup=admin_main_keyboard())

    async def send_users_page(message: Message, page: int = 1) -> None:
        async with session_factory() as session:
            users = list((await session.scalars(select(ManagedUser).where(ManagedUser.is_deleted.is_(False)))).all())
        now = now_utc()
        rows: list[tuple[int, str]] = []
        for user in users:
            delta_days = days_until(user.expire_at)
            if delta_days < 0:
                status = f"🔴 已过期 {abs(delta_days)} 天"
            else:
                status = f"🟢 剩余 {delta_days} 天"
            rows.append((int((user.expire_at - now).total_seconds()), f"{user.username} | 到期时间：{fmt_expire(user.expire_at)} | {status}"))
        rows.sort(key=lambda x: x[0])
        lines = [x[1] for x in rows]
        if not lines:
            await message.answer("当前没有有效账号。", reply_markup=admin_main_keyboard())
            return
        page_size = 10
        total_pages = (len(lines) + page_size - 1) // page_size
        page = max(1, min(page, total_pages))
        chunk = lines[(page - 1) * page_size : page * page_size]
        markup = _build_user_page(lines, page, total_pages)
        await message.answer("\n".join(chunk), reply_markup=markup or admin_main_keyboard())

    @router.callback_query(F.data.startswith("users_page:"))
    async def users_page_callback(callback: CallbackQuery) -> None:
        page = int(callback.data.split(":", 1)[1])
        async with session_factory() as session:
            users = list((await session.scalars(select(ManagedUser).where(ManagedUser.is_deleted.is_(False)))).all())
        now = now_utc()
        rows: list[tuple[int, str]] = []
        for user in users:
            delta_days = days_until(user.expire_at)
            if delta_days < 0:
                status = f"🔴 已过期 {abs(delta_days)} 天"
            else:
                status = f"🟢 剩余 {delta_days} 天"
            rows.append((int((user.expire_at - now).total_seconds()), f"{user.username} | 到期时间：{fmt_expire(user.expire_at)} | {status}"))
        rows.sort(key=lambda x: x[0])
        lines = [x[1] for x in rows]
        page_size = 10
        total_pages = max(1, (len(lines) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        chunk = lines[(page - 1) * page_size : page * page_size]
        markup = _build_user_page(lines, page, total_pages)
        await callback.message.edit_text("\n".join(chunk), reply_markup=markup)
        await callback.answer()

    @router.message(Command("start"))
    async def start(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        await send_home(message, "欢迎使用管理员机器人。")

    @router.message(F.text == "🧩 生成注册码/续期码")
    async def ask_generate(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.set_state(AdminStates.waiting_generate)
        await message.answer("请输入：<b>天数 空格 数量</b>\n例如：30 5")

    @router.message(AdminStates.waiting_generate)
    async def do_generate(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        text = (message.text or "").strip()
        parts = text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await message.answer("格式错误，请输入：<b>天数 空格 数量</b>")
            return
        days = int(parts[0])
        count = int(parts[1])
        async with session_factory() as session:
            codes = await create_codes(session, expire_days=days, count=count, length=settings.REGISTER_CODE_LENGTH)
            await add_audit(session, "admin_bot", "create_codes", f"days={days}, count={count}")
            await session.commit()
        lines = [f"{item.code} | {item.expire_days} 天" for item in codes]
        await message.answer("生成成功：\n" + "\n".join(lines), reply_markup=admin_main_keyboard())
        await state.clear()

    @router.message(F.text == "📦 查询注册码库存")
    async def query_codes(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        async with session_factory() as session:
            codes = await list_available_codes(session)
        if not codes:
            await message.answer("当前没有可用注册码库存。", reply_markup=admin_main_keyboard())
            return
        lines = [f"{item.code} | {item.expire_days} 天" for item in codes]
        for i, chunk in enumerate(chunk_lines(lines, max_chars=3200)):
            if i == 0:
                await message.answer(chunk, reply_markup=admin_main_keyboard())
            else:
                await message.answer(chunk)

    @router.message(F.text == "🗑️ 删除注册码库存")
    async def clear_all_codes(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        async with session_factory() as session:
            count = await clear_codes(session)
            await add_audit(session, "admin_bot", "clear_codes", f"count={count}")
            await session.commit()
        await message.answer(f"注册码库存已清空，共删除 <b>{count}</b> 条。", reply_markup=admin_main_keyboard())

    @router.message(F.text == "👥 查询有效账号")
    async def query_active_users(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        await send_users_page(message, page=1)

    @router.message(F.text == "🔄 同步Emby到本地")
    async def do_sync_emby_to_local(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        try:
            async with session_factory() as session:
                result = await sync_emby_users_to_local(session, settings=settings, emby_client=emby_client)
                await add_audit(session, "admin_bot", "sync_emby_users_to_local", str(result))
                await session.commit()
        except Exception as exc:
            await message.answer(f"同步失败：{exc}", reply_markup=admin_main_keyboard())
            return
        await message.answer(
            "同步完成（Emby -> 本地）。\n"
            f"新增本地账号：<b>{result['created']}</b>\n"
            f"更新本地账号：<b>{result['updated']}</b>\n"
            f"删除本地多余账号：<b>{result['deleted']}</b>\n"
            f"忽略账号：<b>{result['ignored']}</b>\n"
            f"本地默认密码：<b>{result['local_password']}</b>",
            reply_markup=admin_main_keyboard(),
        )
        extras = list(result.get("deleted_usernames") or [])
        if extras:
            for chunk in chunk_lines([f"- {name}" for name in extras], max_chars=3200):
                await message.answer(f"以下本地多余账号已删除：\n{chunk}")

    @router.message(F.text == "⬆️ 同步本地到Emby")
    async def do_sync_local_to_emby(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        async with session_factory() as session:
            result = await import_local_users_to_emby(session, settings=settings, emby_client=emby_client)
            await add_audit(session, "admin_bot", "import_local_users_to_emby", str(result))
            await session.commit()
        text = (
            "导入完成（本地 -> Emby）\n"
            f"导入成功数量：<b>{result['imported_count']}</b>\n"
            f"跳过数量：<b>{result['skipped_count']}</b>"
        )
        await message.answer(text, reply_markup=admin_main_keyboard())
        imported_names = result.get("imported_names") or []
        skipped_names = result.get("skipped_names") or []
        if imported_names:
            await message.answer("导入成功的账号名：\n" + "\n".join(f"- {x}" for x in imported_names))
        if skipped_names:
            await message.answer("跳过的账号名：\n" + "\n".join(f"- {x}" for x in skipped_names))

    @router.message(F.text == "❌ 删除用户信息")
    async def ask_delete_user(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.set_state(AdminStates.waiting_delete_username)
        await message.answer("请输入要删除的用户名。")

    @router.message(AdminStates.waiting_delete_username)
    async def do_delete_user(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        username = (message.text or "").strip()
        async with session_factory() as session:
            exists = await get_local_user_by_username(session, username)
            if not exists:
                await message.answer("本地未找到该用户。", reply_markup=admin_main_keyboard())
                await state.clear()
                return
            ok, msg = await delete_user_everywhere(session, username=username, emby_client=emby_client)
            await add_audit(session, "admin_bot", "delete_user_everywhere", f"{username} -> {ok}:{msg}")
            await session.commit()
        await message.answer(msg, reply_markup=admin_main_keyboard())
        await state.clear()

    @router.message(F.text == "⏳ 修改用户时间")
    async def ask_modify_user(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.set_state(AdminStates.waiting_modify_username)
        await message.answer("请输入用户名。")

    @router.message(AdminStates.waiting_modify_username)
    async def input_modify_user(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        username = (message.text or "").strip()
        async with session_factory() as session:
            user = await get_local_user_by_username(session, username)
        if not user:
            await message.answer("未找到该用户。", reply_markup=admin_main_keyboard())
            await state.clear()
            return
        await state.update_data(modify_username=username)
        await state.set_state(AdminStates.waiting_modify_days)
        await message.answer(
            f"当前用户：<b>{username}</b>\n"
            f"当前到期时间：<b>{fmt_expire(user.expire_at)}</b>\n"
            "请输入要增加/减少的天数，例如：10 或 -5"
        )

    @router.message(AdminStates.waiting_modify_days)
    async def input_modify_days(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        text = (message.text or "").strip()
        try:
            delta_days = int(text)
        except ValueError:
            await message.answer("请输入整数，例如 10 或 -5")
            return
        data = await state.get_data()
        username = data["modify_username"]
        async with session_factory() as session:
            user = await update_user_expire_days(session, username=username, delta_days=delta_days)
            await add_audit(session, "admin_bot", "update_user_expire_days", f"{username}, delta={delta_days}")
            await session.commit()
        await message.answer(
            f"修改成功。\n账号：<b>{user.username}</b>\n新的到期时间：<b>{fmt_expire(user.expire_at)}</b>",
            reply_markup=admin_main_keyboard(),
        )
        await state.clear()

    @router.message(F.text == "📱 查询用户登录信息")
    async def query_login_info(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        rows = await emby_client.get_login_device_rows()
        if not rows:
            await message.answer("当前没有在线登录设备。", reply_markup=admin_main_keyboard())
            return
        lines = []
        for row in rows:
            flag = "▶️播放中" if row["playing"] else "🟢在线"
            lines.append(f"{row['username']} | {row['device_name']} | {row['ip']} | {row['client']} | {flag}")
        for i, chunk in enumerate(chunk_lines(lines, max_chars=3200)):
            if i == 0:
                await message.answer(chunk, reply_markup=admin_main_keyboard())
            else:
                await message.answer(chunk)

    @router.message(F.text == "▶️ 在线播放人数")
    async def query_now_playing(message: Message, state: FSMContext) -> None:
        if not await ensure_admin(message):
            return
        await state.clear()
        count = await emby_client.get_now_playing_count()
        await message.answer(f"当前 Emby 在线播放人数：<b>{count}</b>", reply_markup=admin_main_keyboard())

    @router.message()
    async def fallback(message: Message) -> None:
        if not await ensure_admin(message):
            return
        await send_home(message, "请点击下方管理员菜单。")

    async def post_init() -> None:
        await bot.set_my_commands([BotCommand(command="start", description="打开主菜单")])
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        except Exception as exc:
            logger.warning("设置管理员机器人菜单按钮失败: %s", exc)

    async def on_startup(*_args, **_kwargs):
        await post_init()

    dp.startup.register(on_startup)
    return bot, dp
