from __future__ import annotations

import asyncio
import datetime as dt
import logging

from aiogram import Bot
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.database.models import Appointment

log = logging.getLogger("reminders")


async def reminders_loop(bot: Bot, sessionmaker: async_sessionmaker, tz: dt.tzinfo) -> None:
    """
    Every 30s:
      - find appointments starting in ~24h, ~1h that are not reminded yet
      - send message to user_id (private chat id == user_id)
      - mark reminded flag
    """
    while True:
        try:
            now = dt.datetime.now(tz=tz)

            windows = [
                ("reminded_24h", dt.timedelta(hours=24)),
                ("reminded_1h", dt.timedelta(hours=1)),
            ]

            async with sessionmaker() as session:
                for flag, delta in windows:
                    start_from = now + delta - dt.timedelta(minutes=1)
                    start_to = now + delta + dt.timedelta(minutes=1)

                    res = await session.execute(
                        select(Appointment)
                        .options(selectinload(Appointment.master), selectinload(Appointment.service))
                        .where(
                            and_(
                                Appointment.status == "active",
                                getattr(Appointment, flag) == False,  # noqa: E712
                                Appointment.starts_at >= start_from,
                                Appointment.starts_at < start_to,
                            )
                        )
                    )
                    appts = list(res.scalars().all())
                    if not appts:
                        continue

                    for a in appts:
                        text = (
                            "⏰ Напоминание о записи\n\n"
                            f"Когда: {a.starts_at.astimezone(tz).strftime('%d.%m.%Y %H:%M')}\n"
                            f"Мастер: {a.master.name}\n"
                            f"Услуга: {a.service.name}\n"
                        )
                        try:
                            await bot.send_message(chat_id=a.user_id, text=text)
                        except Exception as e:
                            log.warning("Failed to send reminder to %s: %s", a.user_id, e)
                            continue

                        # mark as reminded
                        async with session.begin():
                            await session.execute(
                                update(Appointment)
                                .where(Appointment.id == a.id)
                                .values({flag: True})
                            )

        except Exception as e:
            log.exception("Reminder loop error: %s", e)

        await asyncio.sleep(30)
