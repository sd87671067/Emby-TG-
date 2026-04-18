from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, MenuButtonCommands, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..config import Settings
from ..emby import EmbyClient, EmbyError
from ..services.audit_service import add_audit
from ..services.code_service import use_code, validate_code
from ..services.user_service import (
    create_registered_user,
    get_local_user_by_username,
    get_or_repair_local_user_by_tg_user_id,
)
from ..utils import fmt_expire, is_valid_username
from .shared import client_main_keyboard, contact_admin_inline


logger = logging.getLogger("app.client_bot")


class ClientStates(StatesGroup):
    waiting_code = State()
    waiting_account_password = State()


def build_client_bot(
    *,
    settings: Settings,
    session_factory: async_sessionmaker,
    emby_client: EmbyClient,
) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.CLIENT_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    router = Router()
    dp.include_router(router)

    async def send_home(message: Message, text: str = "欢迎使用客户端机器人。") -> None:
        await message.answer(text, reply_markup=client_main_keyboard())

    async def send_my_account(message: Message) -> None:
        async with session_factory() as session:
            user = await get_or_repair_local_user_by_tg_user_id(session, message.from_user.id)
        if not user:
            await message.answer("你还没有注册账号。", reply_markup=client_main_keyboard())
            return
        await message.answer(
            f"账号：<b>{user.username}</b>\n"
            f"到期时间：<b>{fmt_expire(user.expire_at)}</b>\n"
            f"服务地址：<b>{settings.EMBY_SERVER_PUBLIC_URL}</b>",
            reply_markup=client_main_keyboard(),
        )

    @router.message(Command("start"))
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await send_home(message, "欢迎使用 Emby 客户端机器人。\n请点击下方按钮。")

    @router.message(F.text == "我的账号")
    async def my_account(message: Message, state: FSMContext) -> None:
        await state.clear()
        await send_my_account(message)

    @router.message(F.text == "在线播放人数")
    async def now_playing(message: Message, state: FSMContext) -> None:
        await state.clear()
        count = await emby_client.get_now_playing_count()
        await message.answer(f"当前 Emby 在线播放人数：<b>{count}</b>", reply_markup=client_main_keyboard())

    @router.message(F.text == "联系管理员")
    async def contact_admin(message: Message, state: FSMContext) -> None:
        await state.clear()
        markup = contact_admin_inline(settings)
        if markup:
            await message.answer("点击下面按钮联系管理员。", reply_markup=markup)
        else:
            await message.answer("管理员尚未配置联系方式。", reply_markup=client_main_keyboard())

    @router.message(F.text == "注册账号")
    async def ask_code(message: Message, state: FSMContext) -> None:
        async with session_factory() as session:
            user = await get_or_repair_local_user_by_tg_user_id(session, message.from_user.id)
        if user:
            await message.answer("你已经注册过账号了，可直接点“我的账号”查询。", reply_markup=client_main_keyboard())
            return
        await state.set_state(ClientStates.waiting_code)
        await message.answer("请输入注册码。验证成功后，才会进入下一步。")

    @router.message(ClientStates.waiting_code)
    async def input_code(message: Message, state: FSMContext) -> None:
        code = (message.text or "").strip()
        async with session_factory() as session:
            invite = await validate_code(session, code)
        if not invite:
            await message.answer("注册码无效或已被使用，请重新输入，或点击其他菜单返回主界面。")
            return
        await state.update_data(invite_code=code, invite_expire_days=invite.expire_days)
        await state.set_state(ClientStates.waiting_account_password)
        await message.answer(
            f"注册码验证成功，有效期 <b>{invite.expire_days}</b> 天。\n"
            "请输入：<b>账号 空格 密码</b>\n"
            "账号只能英文+数字。\n"
            "密码可为空；如果要留空，直接只输入账号即可。"
        )

    @router.message(ClientStates.waiting_account_password)
    async def input_account_password(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("输入不能为空，请重新输入。")
            return
        parts = text.split(maxsplit=1)
        username = parts[0].strip()
        password = parts[1] if len(parts) > 1 else ""

        if not is_valid_username(username):
            await message.answer("账号名只能使用英文和数字，请重新输入。")
            return

        async with session_factory() as session:
            exists_name = await get_local_user_by_username(session, username)
            if exists_name:
                await message.answer("该账号名已存在，请换一个。")
                return

            exists_tg = await get_or_repair_local_user_by_tg_user_id(session, message.from_user.id)
            if exists_tg:
                await message.answer("你的 Telegram 已绑定账号，不能重复注册。", reply_markup=client_main_keyboard())
                await state.clear()
                return

            data = await state.get_data()
            code = data["invite_code"]
            invite = await use_code(session, code, username, message.from_user.id)
            if not invite:
                await message.answer("注册码无效或已被使用，请返回主界面重新开始。", reply_markup=client_main_keyboard())
                await state.clear()
                return

            try:
                user = await create_registered_user(
                    session,
                    settings=settings,
                    emby_client=emby_client,
                    username=username,
                    password=password,
                    tg_user_id=message.from_user.id,
                    expire_days=invite.expire_days,
                    source="register",
                )
                await add_audit(session, "client_bot", "register_user", f"{username}, days={invite.expire_days}")
                await session.commit()
            except EmbyError as exc:
                await session.rollback()
                invite.is_used = False
                invite.used_by_username = None
                invite.used_by_tg_user_id = None
                invite.used_at = None
                await session.commit()
                await message.answer(f"注册失败，Emby 返回错误：{exc}", reply_markup=client_main_keyboard())
                await state.clear()
                return
            except Exception as exc:
                await session.rollback()
                invite.is_used = False
                invite.used_by_username = None
                invite.used_by_tg_user_id = None
                invite.used_at = None
                await session.commit()
                await message.answer(f"注册失败：{exc}", reply_markup=client_main_keyboard())
                await state.clear()
                return

        await message.answer(
            "注册成功。\n"
            f"账号：<b>{user.username}</b>\n"
            f"到期时间：<b>{fmt_expire(user.expire_at)}</b>\n"
            f"服务地址：<b>{settings.EMBY_SERVER_PUBLIC_URL}</b>",
            reply_markup=client_main_keyboard(),
        )
        await state.clear()

    @router.message()
    async def fallback(message: Message) -> None:
        await send_home(message, "请点击下方菜单按钮。")

    async def post_init() -> None:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="打开主菜单"),
            ]
        )
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        except Exception as exc:
            logger.warning("设置客户端机器人菜单按钮失败: %s", exc)

    async def on_startup(*_args, **_kwargs):
        await post_init()

    dp.startup.register(on_startup)
    return bot, dp
