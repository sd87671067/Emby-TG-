from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import Settings


logger = logging.getLogger("app.emby")


class EmbyError(Exception):
    pass


class EmbyClient:
    """只通过 Emby HTTP API 通信，不直接访问 Emby sqlite/db 文件，避免锁库。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.EMBY_BASE_URL.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=20.0,
            headers={
                "X-Emby-Token": settings.EMBY_API_KEY,
                "Content-Type": "application/json",
            },
        )
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        resp = await self._client.request(method, url, **kwargs)
        if resp.status_code >= 400:
            text = resp.text[:500]
            raise EmbyError(f"Emby 请求失败 {resp.status_code}: {text}")
        if not resp.text:
            return None
        return resp.json()

    async def validate(self) -> dict[str, Any]:
        return await self._request("GET", "/System/Info")

    async def get_users(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/Users/Query")
        return data.get("Items", [])

    async def get_user_by_name(self, username: str) -> dict[str, Any] | None:
        users = await self.get_users()
        for user in users:
            if str(user.get("Name", "")).lower() == username.lower():
                return user
        return None

    async def get_user_by_id(self, user_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/Users/{user_id}")

    async def create_user(self, username: str) -> dict[str, Any]:
        body = {"Name": username}
        return await self._request("POST", "/Users/New", json=body)

    async def delete_user(self, user_id: str) -> None:
        await self._request("POST", f"/Users/{user_id}/Delete")

    async def update_user_password(self, user_id: str, new_password: str) -> None:
        body = {"Id": user_id, "NewPw": new_password, "ResetPassword": False}
        await self._request("POST", f"/Users/{user_id}/Password", json=body)

    async def update_user_policy(self, user_id: str, policy: dict[str, Any]) -> None:
        await self._request("POST", f"/Users/{user_id}/Policy", json=policy)

    async def update_user_configuration(self, user_id: str, configuration: dict[str, Any]) -> None:
        await self._request("POST", f"/Users/{user_id}/Configuration", json=configuration)

    async def clone_from_template(self, new_user_id: str, template_username: str) -> None:
        template = await self.get_user_by_name(template_username)
        if not template:
            raise EmbyError(f"模板用户不存在: {template_username}")
        template_full = await self.get_user_by_id(template["Id"])
        policy = template_full.get("Policy") or template.get("Policy")
        config = template_full.get("Configuration") or template.get("Configuration")
        if policy:
            await self.update_user_policy(new_user_id, policy)
        if config:
            await self.update_user_configuration(new_user_id, config)

    async def ensure_user(self, username: str, password: str | None = None) -> dict[str, Any]:
        async with self._lock:
            user = await self.get_user_by_name(username)
            if not user:
                logger.info("开始在 Emby 创建用户: %s", username)
                user = await self.create_user(username)
                logger.info("Emby 用户创建成功: %s", username)
                await self.clone_from_template(user["Id"], self.settings.EMBY_TEMPLATE_USER)
                logger.info("已复制模板用户权限/配置: %s -> %s", self.settings.EMBY_TEMPLATE_USER, username)
            if password is not None:
                await self.update_user_password(user["Id"], password)
                logger.info("已更新 Emby 用户密码: %s", username)
            return user

    async def get_sessions(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/Sessions")

    async def get_now_playing_count(self) -> int:
        sessions = await self.get_sessions()
        return sum(1 for item in sessions if item.get("NowPlayingItem"))

    async def get_login_device_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        sessions = await self.get_sessions()
        for item in sessions:
            rows.append(
                {
                    "username": item.get("UserName") or "-",
                    "device_name": item.get("DeviceName") or "-",
                    "client": item.get("Client") or "-",
                    "device_type": item.get("DeviceType") or "-",
                    "ip": item.get("RemoteEndPoint") or "-",
                    "last_activity": item.get("LastActivityDate") or "-",
                    "playing": bool(item.get("NowPlayingItem")),
                }
            )
        return rows
