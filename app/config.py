from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Emby TG 管理中心"
    APP_ENV: str = "production"
    APP_PORT: int = 18080
    APP_BASE_URL: str = "http://127.0.0.1:18080"
    APP_TIMEZONE: str = "Asia/Shanghai"
    APP_MASTER_KEY: str = "change-me-32-characters-minimum"
    APP_WEB_ADMIN_USERNAME: str = "admin"
    APP_WEB_ADMIN_PASSWORD: str = "change-me"

    EMBY_BASE_URL: str = "http://127.0.0.1:8096"
    EMBY_API_KEY: str = ""
    EMBY_SERVER_PUBLIC_URL: str = "http://127.0.0.1:8096"
    EMBY_TEMPLATE_USER: str = "testone"
    EMBY_IMPORT_IGNORE_USERNAMES: str = "admin"
    EMBY_SYNC_LOCAL_DEFAULT_PASSWORD: str = "1234"

    ADMIN_BOT_TOKEN: str = ""
    ADMIN_CHAT_IDS: str = ""
    CLIENT_BOT_TOKEN: str = ""

    ADMIN_CONTACT_TG_USERNAME: str = ""
    ADMIN_CONTACT_TG_USER_ID: int | None = None

    DEFAULT_USER_EXPIRE_DAYS: int = 90
    REGISTER_CODE_LENGTH: int = 16
    CODE_BATCH_LIMIT: int = 500
    WEB_EXPIRING_SOON_DAYS: int = 3

    EXPIRY_CHECK_SECONDS: int = 300
    ONLINE_CHECK_SECONDS: int = 60

    DATA_DIR: str = "/data"
    DATABASE_URL: str = "sqlite+aiosqlite:////data/app.db"

    @property
    def admin_chat_id_list(self) -> List[int]:
        result: List[int] = []
        for raw in self.ADMIN_CHAT_IDS.split(","):
            raw = raw.strip()
            if not raw:
                continue
            result.append(int(raw))
        return result

    @property
    def emby_import_ignore_usernames(self) -> set[str]:
        return {x.strip().lower() for x in self.EMBY_IMPORT_IGNORE_USERNAMES.split(",") if x.strip()}

    @property
    def has_public_base_url(self) -> bool:
        return self.APP_BASE_URL.startswith("http://") or self.APP_BASE_URL.startswith("https://")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
