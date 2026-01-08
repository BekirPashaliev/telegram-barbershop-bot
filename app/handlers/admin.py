from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Config
from app.database.requests import add_master, get_today_appointments, list_masters
from app.keyboards.builders import admin_menu_kb, main_menu_kb

from app.database.requests import add_service

from app.database.requests import audit


router = Router(name="admin")


class AddMasterStates(StatesGroup):
    name = State()
    description = State()

class AddServiceStates(StatesGroup):
    name = State()
    duration = State()
    price = State()
    description = State()


def _is_admin(message: Message, config: Config) -> bool:
    return message.from_user and message.from_user.id in config.admin_ids


@router.message(Command("admin"))
async def admin_entry(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return
    await state.clear()
    await message.answer("Админ-меню:", reply_markup=admin_menu_kb())


@router.message(F.text == "⬅️ В меню")
async def back_to_main(message: Message) -> None:
    await message.answer("Ок.", reply_markup=main_menu_kb())


@router.message(F.text == "📋 Записи сегодня")
async def today_appointments(message: Message, config: Config, session: AsyncSession) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return

    today = dt.datetime.now(tz=config.tz).date()
    appts = await get_today_appointments(session, tz=config.tz, today=today)

    if not appts:
        await message.answer("На сегодня записей нет.")
        return

    lines = [f"Записи на сегодня ({today.strftime('%d.%m.%Y')}):"]
    for a in appts:
        who = f"@{a.user.username}" if a.user and a.user.username else f"user_id={a.user_id}"
        lines.append(
            f"• {a.starts_at.astimezone(config.tz).strftime('%H:%M')} — "
            f"{a.master.name if a.master else a.master_id} — "
            f"{a.service.name if a.service else a.service_id} — {who}"
        )

    await message.answer("\n".join(lines))


@router.message(F.text == "➕ Добавить мастера")
async def add_master_start(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return
    await state.set_state(AddMasterStates.name)
    await message.answer("Введи имя мастера:")


@router.message(AddMasterStates.name, F.text)
async def add_master_name(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Введи ещё раз:")
        return
    await state.update_data(name=name)
    await state.set_state(AddMasterStates.description)
    await message.answer("Введи описание (или '-' чтобы пропустить):")


@router.message(AddMasterStates.description, F.text)
async def add_master_finish(message: Message, config: Config, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return

    desc = message.text.strip()
    if desc == "-":
        desc = None

    data = await state.get_data()
    name = data["name"]

    m = await add_master(session, name=name, description=desc)
    await audit(session, actor_user_id=message.from_user.id, action="add_master", entity="Master", entity_id=m.id,
                meta={"name": m.name})
    await state.clear()
    await message.answer(f"✅ Мастер добавлен: {m.name}", reply_markup=admin_menu_kb())


@router.message(F.text == "➕ Добавить услугу")
async def add_service_start(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return
    await state.set_state(AddServiceStates.name)
    await message.answer("Название услуги (например: Стрижка, Борода):")


@router.message(AddServiceStates.name, F.text)
async def add_service_name(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Слишком коротко. Введи ещё раз:")
        return
    await state.update_data(name=name)
    await state.set_state(AddServiceStates.duration)
    await message.answer("Длительность в минутах (например 30/60/90):")


@router.message(AddServiceStates.duration, F.text)
async def add_service_duration(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return
    try:
        minutes = int(message.text.strip())
        if minutes <= 0 or minutes > 8 * 60:
            raise ValueError
    except ValueError:
        await message.answer("Нужно число минут, например 60.")
        return

    await state.update_data(duration_minutes=minutes)
    await state.set_state(AddServiceStates.price)
    await message.answer("Цена (целое число рублей, например 1500):")


@router.message(AddServiceStates.price, F.text)
async def add_service_price(message: Message, config: Config, state: FSMContext) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return
    try:
        rub = int(message.text.strip())
        if rub < 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно целое число рублей, например 1500.")
        return

    await state.update_data(price_cents=rub * 100)
    await state.set_state(AddServiceStates.description)
    await message.answer("Описание (или '-' чтобы пропустить):")


@router.message(AddServiceStates.description, F.text)
async def add_service_finish(message: Message, config: Config, state: FSMContext, session: AsyncSession) -> None:
    if not _is_admin(message, config):
        await message.answer("⛔️ Доступ запрещён.")
        return

    desc = message.text.strip()
    if desc == "-":
        desc = None

    data = await state.get_data()
    s = await add_service(
        session=session,
        name=data["name"],
        description=desc,
        duration_minutes=data["duration_minutes"],
        price_cents=data["price_cents"],
    )
    await audit(session, actor_user_id=message.from_user.id, action="add_service", entity="Service", entity_id=s.id,
                meta={"name": data["name"]})
    await state.clear()
    await message.answer("✅ Услуга добавлена.", reply_markup=admin_menu_kb())
