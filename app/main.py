from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from .bots.admin_bot import build_admin_bot
from .bots.client_bot import build_client_bot
from .config import get_settings
from .db import SessionLocal, init_db
from .emby import EmbyClient
from .logging_setup import setup_logging
from .services.user_service import delete_user_everywhere, get_expired_users_need_notify
from .utils import fmt_expire


setup_logging()
logger = logging.getLogger("app.main")
settings = get_settings()


async def validate_emby(emby_client: EmbyClient) -> None:
    info = await emby_client.validate()
    logger.info("Emby API Key 校验成功，服务器：%s，版本：%s", info.get("ServerName"), info.get("Version"))


async def validate_bot(bot, title: str) -> None:
    me = await bot.get_me()
    logger.info("%s Token 校验成功，机器人用户名：@%s", title, me.username)


async def expiry_notifier_loop(admin_bot, session_factory, emby_client: EmbyClient) -> None:
    while True:
        try:
            async with session_factory() as session:
                users = await get_expired_users_need_notify(session)
                for user in users:
                    username = user.username
                    expire_text = fmt_expire(user.expire_at)
                    ok, msg = await delete_user_everywhere(session, username=username, emby_client=emby_client)
                    if ok:
                        text = f"{username} 账号过期已删除。\n到期时间：<b>{expire_text}</b>"
                        logger.info("到期账号已自动删除：%s", username)
                    else:
                        text = f"{username} 账号已到期，但自动删除失败：{msg}\n到期时间：<b>{expire_text}</b>"
                        logger.warning("到期账号自动删除失败：%s -> %s", username, msg)

                    for admin_chat_id in settings.admin_chat_id_list:
                        await admin_bot.send_message(admin_chat_id, text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("到期检查任务异常: %s", exc)
        await asyncio.sleep(settings.EXPIRY_CHECK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    emby_client = EmbyClient(settings)
    admin_bot, admin_dp = build_admin_bot(settings=settings, session_factory=SessionLocal, emby_client=emby_client)
    client_bot, client_dp = build_client_bot(settings=settings, session_factory=SessionLocal, emby_client=emby_client)

    await validate_emby(emby_client)
    await validate_bot(admin_bot, "管理员机器人")
    await validate_bot(client_bot, "客户端机器人")

    admin_task = asyncio.create_task(admin_dp.start_polling(admin_bot))
    client_task = asyncio.create_task(client_dp.start_polling(client_bot))
    expiry_task = asyncio.create_task(expiry_notifier_loop(admin_bot, SessionLocal, emby_client))

    app.state.emby_client = emby_client
    app.state.admin_bot = admin_bot
    app.state.client_bot = client_bot

    logger.info("服务启动完成：机器人模式 | Emby=%s", settings.EMBY_BASE_URL)
    try:
        yield
    finally:
        for task in [admin_task, client_task, expiry_task]:
            task.cancel()
        await asyncio.gather(admin_task, client_task, expiry_task, return_exceptions=True)
        await admin_bot.session.close()
        await client_bot.session.close()
        await emby_client.close()
        logger.info("服务已停止。")


app = FastAPI(
    title=settings.APP_NAME,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "app": settings.APP_NAME}
