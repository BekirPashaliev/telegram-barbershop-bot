from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Config
from app.database.requests import (
    SlotSettings,
    add_user,
    get_free_slots,
    get_future_appointments,
    list_masters,
    cancel_appointment,
)
from app.keyboards.builders import (
    confirm_kb,
    main_menu_kb,
    masters_kb,
    my_appointments_kb,
    time_slots_kb,
)

from app.database.requests import list_services
from app.keyboards.builders import services_kb, calendar_14d_kb

from app.database.requests import create_appointment_with_payment_acid, mark_payment_paid_and_activate_appointment
from app.keyboards.builders import pay_kb

router = Router(name="user")

async def _safe_edit_text(message: Message | None, text: str, **kwargs) -> None:
    """edit_text без падения на повторных кликах (message is not modified)."""
    if message is None:
        return
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise

class BookingStates(StatesGroup):
    choosing_master = State()
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    await add_user(session, tg_id=message.from_user.id, username=message.from_user.username)
    await session.commit()

    await message.answer(
        "Привет! Я бот для записи в барбершоп.\n\nВыбирай действие:",
        reply_markup=main_menu_kb(),
    )


@router.message(F.contact)
async def got_contact(message: Message, session: AsyncSession) -> None:
    if message.contact and message.contact.phone_number:
        from app.database.requests import set_user_phone
        await set_user_phone(session, message.from_user.id, message.contact.phone_number)
        await session.commit()
        await message.answer("✅ Номер сохранён.")


@router.message(F.text == "📅 Записаться")
async def book_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    # Пользователь может нажать "Записаться" без /start -> гарантируем users.
    await add_user(session, tg_id=message.from_user.id, username=message.from_user.username)
    await session.commit()
    masters = await list_masters(session)
    if not masters:
        await message.answer("Пока нет мастеров. Админ должен добавить мастеров через /admin.")
        return

    await state.clear()
    await state.set_state(BookingStates.choosing_master)

    items = [(m.id, m.name) for m in masters]
    await message.answer("Шаг 1/4: выбери мастера:", reply_markup=masters_kb(items))


@router.callback_query(F.data == "bk:cancel")
async def booking_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _safe_edit_text(call.message, "Ок, отменено.")
    await call.answer()


@router.callback_query(F.data.startswith("bk:master:"))
async def choose_master(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    master_id = int(call.data.split(":")[-1])
    await state.update_data(master_id=master_id)

    services = await list_services(session)
    if not services:
        await _safe_edit_text(call.message, "Нет услуг. Админ должен добавить услуги через /admin.")
        await call.answer()
        return

    await state.set_state(BookingStates.choosing_service)
    items = [(s.id, s.name) for s in services]
    await _safe_edit_text(call.message, "Шаг 2/5: выбери услугу:", reply_markup=services_kb(items))
    await call.answer()

@router.callback_query(F.data == "bk:back:services")
async def back_to_services(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    services = await list_services(session)
    items = [(s.id, s.name) for s in services]
    await state.set_state(BookingStates.choosing_service)
    await _safe_edit_text(call.message, "Шаг 2/5: выбери услугу:", reply_markup=services_kb(items))
    await call.answer()


@router.callback_query(F.data.startswith("bk:service:"))
async def choose_service(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    service_id = int(call.data.split(":")[-1])
    await state.update_data(service_id=service_id)

    today = dt.datetime.now(tz=config.tz).date()
    await state.set_state(BookingStates.choosing_date)
    await _safe_edit_text(call.message, "Шаг 3/5: выбери дату:", reply_markup=calendar_14d_kb(today))
    await call.answer()


@router.callback_query(F.data == "bk:back:masters")
async def back_to_masters(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    masters = await list_masters(session)
    items = [(m.id, m.name) for m in masters]
    await state.set_state(BookingStates.choosing_master)
    await _safe_edit_text(call.message, "Шаг 1/4: выбери мастера:", reply_markup=masters_kb(items))
    await call.answer()


@router.callback_query(F.data.startswith("bk:date:"))
async def choose_date(call: CallbackQuery, state: FSMContext, config: Config, session: AsyncSession) -> None:
    data = await state.get_data()
    master_id = int(data["master_id"])
    service_id = int(data["service_id"])

    date_ = dt.date.fromisoformat(call.data.split(":")[-1])

    slot_settings = SlotSettings(
        tz=config.tz,
        work_start_hour=config.work_start_hour,
        work_end_hour=config.work_end_hour,
        slot_minutes=config.slot_minutes,
    )

    try:
        free = await get_free_slots(session, master_id=master_id, service_id=service_id, date_=date_,
                                    s=slot_settings)
    except ValueError as e:
        today = dt.datetime.now(tz=config.tz).date()
        await state.set_state(BookingStates.choosing_date)
        await _safe_edit_text(call.message, f"⚠️ {e}\n\nВыбери другую дату:", reply_markup=calendar_14d_kb(today))
        await call.answer()
        return
    await state.update_data(date=date_.isoformat())
    await state.set_state(BookingStates.choosing_time)

    if not free:
        today = dt.datetime.now(tz=config.tz).date()
        await _safe_edit_text(call.message, "Свободных окон нет. Выбери другую дату:", reply_markup=calendar_14d_kb(today))
        await call.answer()
        return

    await _safe_edit_text(call.message, "Шаг 4/5: выбери время:", reply_markup=time_slots_kb(free, config.tz))
    await call.answer()


@router.callback_query(F.data == "bk:back:dates")
async def back_to_dates(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    await state.set_state(BookingStates.choosing_date)
    today = dt.datetime.now(tz=config.tz).date()
    await _safe_edit_text(call.message, "Шаг 3/5: выбери дату:", reply_markup=calendar_14d_kb(today))
    await call.answer()


@router.callback_query(F.data.startswith("bk:time:"))
async def choose_time(call: CallbackQuery, state: FSMContext, config: Config, session: AsyncSession) -> None:
    iso = call.data.split("bk:time:", 1)[1]
    when = dt.datetime.fromisoformat(iso)

    data = await state.get_data()
    master_id = int(data["master_id"])

    masters = await list_masters(session)
    master_name = next((m.name for m in masters if m.id == master_id), f"#{master_id}")

    await state.update_data(when=when.isoformat(), master_name=master_name)

    await state.set_state(BookingStates.confirming)

    text = (
        "Шаг 4/4: подтверди запись:\n\n"
        f"Мастер: {master_name}\n"
        f"Дата/время: {when.astimezone(config.tz).strftime('%d.%m.%Y %H:%M')}"
    )
    await _safe_edit_text(call.message, text, reply_markup=confirm_kb())
    await call.answer()


@router.callback_query(F.data == "bk:back:times")
async def back_to_times(call: CallbackQuery, state: FSMContext, config: Config, session: AsyncSession) -> None:
    data = await state.get_data()
    master_id = int(data["master_id"])
    service_id = int(data["service_id"])
    date_ = dt.date.fromisoformat(data["date"])

    slot_settings = SlotSettings(
        tz=config.tz,
        work_start_hour=config.work_start_hour,
        work_end_hour=config.work_end_hour,
        slot_minutes=config.slot_minutes,
    )

    try:
        free = await get_free_slots(session, master_id=master_id, service_id=service_id, date_=date_,
                                    s=slot_settings)
    except ValueError as e:
        today = dt.datetime.now(tz=config.tz).date()
        await state.set_state(BookingStates.choosing_date)
        await _safe_edit_text(call.message, f"⚠️ {e}\n\nВыбери дату:", reply_markup=calendar_14d_kb(today))
        await call.answer()
        return

    await state.set_state(BookingStates.choosing_time)
    await _safe_edit_text(call.message, "Шаг 3/4: выбери время:", reply_markup=time_slots_kb(free, config.tz))
    await call.answer()


@router.callback_query(F.data == "bk:confirm")
async def confirm(call: CallbackQuery, state: FSMContext, config: Config, session: AsyncSession) -> None:
    # Если пользователь пришёл без /start, FK на appointments упадёт.
    await add_user(session, tg_id=call.from_user.id, username=call.from_user.username)
    await session.flush()
    data = await state.get_data()
    master_id = int(data["master_id"])
    service_id = int(data["service_id"])
    starts_at = dt.datetime.fromisoformat(data["when"])

    created = await create_appointment_with_payment_acid(
        session = session,
        user_id = call.from_user.id,
        master_id = master_id,
        service_id = service_id,
        starts_at = starts_at,
    )
    if not created:
        # await call.message.edit_text("⚠️ Слот пересекается с другой записью (ACID/EXCLUDE). Выбери другое время.")
        # await state.set_state(BookingStates.choosing_date)
        # await call.answer()
        # return

        # Слот уже заняли/зарезервировали (или нажали старую кнопку).
        # Обновляем свободные слоты и возвращаем на выбор времени.
        date_ = starts_at.astimezone(config.tz).date()
        slot_settings = SlotSettings(
            tz=config.tz,
            work_start_hour=config.work_start_hour,
            work_end_hour=config.work_end_hour,
            slot_minutes=config.slot_minutes,
        )
        free = await get_free_slots(
            session=session,
            master_id=master_id,
            service_id=service_id,
            date_=date_,
            s=slot_settings,
        )
        await state.update_data(date=date_.isoformat())
        if not free:
            today = dt.datetime.now(tz=config.tz).date()
            await state.set_state(BookingStates.choosing_date)
            await _safe_edit_text(call.message,
                "⚠️ Этот слот уже занят.\n"
                "На выбранную дату свободных окон больше нет.\n\n"
                "Выбери другую дату:",
                reply_markup=calendar_14d_kb(today),
            )
        else:
            await state.set_state(BookingStates.choosing_time)
            await _safe_edit_text(call.message,
                "⚠️ Этот слот уже занят (или зарезервирован). Выбери другое время:",
                reply_markup=time_slots_kb(free, config.tz),
            )
        await call.answer()
        return

    appt, payment = created
    await session.commit()
    await state.clear()
    await _safe_edit_text(call.message,
        "✅ Почти готово!\n"
        "Оплати, чтобы подтвердить запись.\n\n"
        f"{starts_at.astimezone(config.tz).strftime('%d.%m.%Y %H:%M')}",
        reply_markup = pay_kb(payment.pay_url, payment.id),
    )

    await call.answer()

@router.callback_query(F.data.startswith("pay:done:"))
async def pay_done(call: CallbackQuery, config: Config, session: AsyncSession) -> None:
    payment_id = int(call.data.split(":")[-1])

    appt = await mark_payment_paid_and_activate_appointment(
        session=session,
        payment_id=payment_id,
        user_id=call.from_user.id,
    )
    if not appt:
        await call.answer("Не удалось подтвердить оплату.", show_alert=True)
        return

    await session.commit()

    await _safe_edit_text(call.message,
        "✅ Оплата принята, запись подтверждена!\n"
        f"{appt.starts_at.astimezone(config.tz).strftime('%d.%m.%Y %H:%M')}"
    )
    await call.answer()


@router.message(F.text == "👤 Мои записи")
async def my_appointments(message: Message, config: Config, session: AsyncSession) -> None:
    now = dt.datetime.now(tz=config.tz)
    appts = await get_future_appointments(session, user_id=message.from_user.id, now=now)

    if not appts:
        await message.answer("У тебя нет будущих записей.")
        return

    await message.answer("Твои будущие записи:")

    for a in appts:
        when = a.starts_at.astimezone(config.tz).strftime("%d.%m %H:%M")
        master = a.master.name if a.master else str(a.master_id)
        service = a.service.name if a.service else str(a.service_id)

        if a.status == "pending_payment":
            pay_url = a.payment.pay_url if a.payment else None
            pay_id = a.payment_id
            text = f"🕒 {when} — {master} — {service}\n⚠️ Ожидает оплаты"
            if pay_id is None:
                # на всякий случай, чтобы не падать
                await message.answer(text)
            else:
                await message.answer(text, reply_markup=pay_kb(pay_url, pay_id))
        else:
            label = f"{when} — {master} — {service}"
            await message.answer(
                f"✅ {label}",
                reply_markup=my_appointments_kb([(a.id, label)]),
            )




@router.callback_query(F.data.startswith("bk:cancel_appt:"))
async def cancel_appt(call: CallbackQuery, session: AsyncSession) -> None:
    appt_id = int(call.data.split(":")[-1])
    ok = await cancel_appointment(session, user_id=call.from_user.id, appointment_id=appt_id)
    if ok:
        await session.commit()
        await call.answer("Отменено ✅", show_alert=True)
        await _safe_edit_text(call.message, "✅ Запись отменена.")
    else:
        await call.answer("Не получилось отменить (возможно уже отменено).", show_alert=True)

@router.callback_query(F.data.startswith("pay:cancel:"))
async def pay_cancel(call: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(call.data.split(":")[-1])

    from app.database.requests import cancel_payment_and_cancel_appointment
    ok = await cancel_payment_and_cancel_appointment(
        session=session,
        payment_id=payment_id,
        user_id=call.from_user.id,
    )
    if not ok:
        await call.answer("Не удалось отменить оплату.", show_alert=True)
        return

    await session.commit()
    await _safe_edit_text(call.message, "❌ Оплата отменена, бронь снята.")
    await call.answer()
