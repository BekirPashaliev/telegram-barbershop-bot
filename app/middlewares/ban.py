from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery


class BanMiddleware(BaseMiddleware):
    def __init__(self, banned_ids: set[int]):
        self._banned = banned_ids

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is not None and user_id in self._banned:
            if isinstance(event, Message):
                await event.answer("⛔️ Вы заблокированы.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔️ Вы заблокированы.", show_alert=True)
            return

        return await handler(event, data)
