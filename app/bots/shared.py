from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from ..config import Settings


def client_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 注册账号"), KeyboardButton(text="🎟️ 使用注册码/续期码")],
            [KeyboardButton(text="👤 我的账号"), KeyboardButton(text="▶️ 在线播放人数")],
            [KeyboardButton(text="📞 联系管理员")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧩 生成注册码/续期码"), KeyboardButton(text="📦 查询注册码库存")],
            [KeyboardButton(text="🗑️ 删除注册码库存"), KeyboardButton(text="👥 查询有效账号")],
            [KeyboardButton(text="➕ 新增注册账号"), KeyboardButton(text="❌ 删除用户信息")],
            [KeyboardButton(text="⏳ 修改用户时间"), KeyboardButton(text="📱 查询用户登录信息")],
            [KeyboardButton(text="🔄 同步Emby到本地"), KeyboardButton(text="⬆️ 同步本地到Emby")],
            [KeyboardButton(text="▶️ 在线播放人数")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def contact_admin_inline(settings: Settings) -> InlineKeyboardMarkup | None:
    if settings.ADMIN_CONTACT_TG_USERNAME:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="联系管理员", url=f"https://t.me/{settings.ADMIN_CONTACT_TG_USERNAME.lstrip('@')}")]
            ]
        )
    if settings.ADMIN_CONTACT_TG_USER_ID:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="联系管理员", url=f"tg://user?id={settings.ADMIN_CONTACT_TG_USER_ID}")]
            ]
        )
    return None
