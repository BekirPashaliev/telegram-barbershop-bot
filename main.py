import asyncio
import logging

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from app.config import load_config
from app.database.session import create_engine_and_sessionmaker
from app.database.requests import ensure_seed_service
from app.handlers.user import router as user_router
from app.handlers.admin import router as admin_router
from app.middlewares.db import DbSessionMiddleware
from app.middlewares.ban import BanMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # For local run: loads .env into process environment.
    load_dotenv()

    config = load_config()
    engine, sessionmaker = create_engine_and_sessionmaker(config.database_url)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = RedisStorage.from_url(config.redis_url) if config.redis_url else MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware(sessionmaker))
    dp.update.middleware(BanMiddleware(config.banned_ids))

    dp.include_router(user_router)
    dp.include_router(admin_router)

    try:
        async with sessionmaker() as session:
            await ensure_seed_service(session)
            await session.commit()

        # Reminders are handled by a separate docker service: app.workers.reminders
        await dp.start_polling(bot, config=config, db_engine=engine)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
