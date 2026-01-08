from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _csv_ints(value: str) -> set[int]:
    value = (value or "").strip()
    if not value:
        return set()
    out: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if part:
            out.add(int(part))
    return out


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    banned_ids: set[int]
    database_url: str

    tz: ZoneInfo
    work_start_hour: int
    work_end_hour: int
    slot_minutes: int

    redis_url: str | None


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Put it into .env")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is empty. Put it into .env")

    tz_name = os.getenv("TIMEZONE", "Europe/Moscow").strip()
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as e:
        raise RuntimeError(
            f"TIMEZONE='{tz_name}' is not available. "
            "Install tzdata (pip install tzdata) or set TIMEZONE=UTC."
        ) from e

    admin_ids = _csv_ints(os.getenv("ADMIN_IDS", ""))
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS is empty. Put your Telegram ID into .env")

    banned_ids = _csv_ints(os.getenv("BANNED_IDS", ""))

    work_start_hour = int(os.getenv("WORK_START_HOUR", "10"))
    work_end_hour = int(os.getenv("WORK_END_HOUR", "20"))
    slot_minutes = int(os.getenv("SLOT_MINUTES", "60"))

    if work_start_hour < 0 or work_start_hour > 23:
        raise RuntimeError("WORK_START_HOUR must be 0..23")
    if work_end_hour < 1 or work_end_hour > 24:
        raise RuntimeError("WORK_END_HOUR must be 1..24")
    if work_end_hour <= work_start_hour:
        raise RuntimeError("WORK_END_HOUR must be greater than WORK_START_HOUR")
    if slot_minutes <= 0 or (60 * 24) % slot_minutes != 0:
        raise RuntimeError("SLOT_MINUTES must be positive and divide 1440")

    redis_url = os.getenv("REDIS_URL", "").strip() or None

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        banned_ids=banned_ids,
        database_url=database_url,
        tz=tz,
        work_start_hour=work_start_hour,
        work_end_hour=work_end_hour,
        slot_minutes=slot_minutes,
        redis_url=redis_url,
    )
