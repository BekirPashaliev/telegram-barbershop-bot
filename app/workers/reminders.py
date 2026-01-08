from __future__ import annotations

import asyncio
import datetime as dt
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from redis.asyncio import Redis
from sqlalchemy import and_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import load_config
from app.database.models import Appointment

logger = logging.getLogger(__name__)

LOCK_KEY = "reminders:lock"


async def _tick(session: AsyncSession, bot: Bot, tz: dt.tzinfo) -> None:
    """Send reminders and mark flags (runs inside a DB transaction)."""
    try:
        now = dt.datetime.now(dt.timezone.utc)

        async def send_and_mark(appt: Appointment, kind: str) -> None:
            local = appt.starts_at.astimezone(tz)
            master_name = appt.master.name if appt.master else str(appt.master_id)
            service_name = appt.service.name if appt.service else str(appt.service_id)

            text = (
                f"⏰ Напоминание: у вас запись {local.strftime('%d.%m %H:%M')}\n"
                f"Мастер: {master_name}\n"
                f"Услуга: {service_name}"
            )
            try:
                await bot.send_message(appt.user_id, text)
            except Exception as e:
                logger.warning("Failed to send reminder to %s: %s", appt.user_id, e)
                return

            if kind == "24h":
                appt.reminded_24h = True
            else:
                appt.reminded_1h = True

        w = dt.timedelta(minutes=5)

        t24 = now + dt.timedelta(hours=24)
        q24 = await session.execute(
            select(Appointment)
            .options(selectinload(Appointment.master), selectinload(Appointment.service))
            .where(
                and_(
                    Appointment.status == "active",
                    Appointment.reminded_24h.is_(False),
                    Appointment.starts_at >= t24,
                    Appointment.starts_at < t24 + w,
                )
            )
        )
        for appt in q24.scalars().all():
            await send_and_mark(appt, "24h")

        t1 = now + dt.timedelta(hours=1)
        q1 = await session.execute(
            select(Appointment)
            .options(selectinload(Appointment.master), selectinload(Appointment.service))
            .where(
                and_(
                    Appointment.status == "active",
                    Appointment.reminded_1h.is_(False),
                    Appointment.starts_at >= t1,
                    Appointment.starts_at < t1 + w,
                )
            )
        )
        for appt in q1.scalars().all():
            await send_and_mark(appt, "1h")

    except ProgrammingError as e:
        # DB is not migrated yet
        logger.warning("DB schema not ready yet, retry later: %s", e)
        return


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    config = load_config()

    if not config.redis_url:
        raise RuntimeError("REDIS_URL is required for reminders worker (distributed lock).")

    engine = create_async_engine(config.database_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    r = Redis.from_url(config.redis_url, decode_responses=True)

    try:
        while True:
            try:
                got = await r.set(LOCK_KEY, "1", nx=True, ex=30)
                if got:
                    async with Session() as session:
                        async with session.begin():
                            await _tick(session, bot, config.tz)
            except Exception as e:
                logger.exception("Reminders loop error: %s", e)

            await asyncio.sleep(10)
    finally:
        await r.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
