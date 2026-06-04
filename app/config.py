from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


class Settings:
    db_path = Path(os.getenv("XHS_DB_PATH", BASE_DIR / "data" / "xhs_content.db"))
    asset_dir = Path(os.getenv("XHS_ASSET_DIR", BASE_DIR / "data" / "generated"))
    browser_profile = Path(os.getenv("XHS_BROWSER_PROFILE", BASE_DIR / "data" / "browser-profile"))
    default_publish_time = os.getenv("XHS_DEFAULT_PUBLISH_TIME", "20:30")
    timezone = os.getenv("XHS_TIMEZONE", "Asia/Shanghai")
    vertical = "AI/效率工具"
    creator_publish_url = "https://creator.xiaohongshu.com/publish/publish?from=menu&target=article"


settings = Settings()

