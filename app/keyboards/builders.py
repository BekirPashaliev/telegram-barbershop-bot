from __future__ import annotations

import datetime as dt

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="📅 Записаться"))
    kb.add(KeyboardButton(text="👤 Мои записи"))
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def admin_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="📋 Записи сегодня"))
    kb.add(KeyboardButton(text="➕ Добавить мастера"))
    kb.add(KeyboardButton(text="➕ Добавить услугу"))
    kb.add(KeyboardButton(text="⬅️ В меню"))
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)


def masters_kb(masters: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for master_id, name in masters:
        b.add(InlineKeyboardButton(text=name, callback_data=f"bk:master:{master_id}"))
    b.adjust(1)
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="bk:cancel"))
    return b.as_markup()


def date_choice_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="Сегодня", callback_data="bk:date:today"))
    b.add(InlineKeyboardButton(text="Завтра", callback_data="bk:date:tomorrow"))
    b.adjust(2)
    b.row(InlineKeyboardButton(text="↩️ Назад", callback_data="bk:back:masters"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="bk:cancel"))
    return b.as_markup()


def time_slots_kb(slots: list[dt.datetime], tz: dt.tzinfo) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for when in slots[:48]:
        label = when.astimezone(tz).strftime("%H:%M")
        payload = when.isoformat()
        b.add(InlineKeyboardButton(text=label, callback_data=f"bk:time:{payload}"))
    b.adjust(4)
    b.row(InlineKeyboardButton(text="↩️ Назад", callback_data="bk:back:dates"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="bk:cancel"))
    return b.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="bk:confirm"))
    b.add(InlineKeyboardButton(text="↩️ Назад", callback_data="bk:back:times"))
    b.adjust(2)
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="bk:cancel"))
    return b.as_markup()


def my_appointments_kb(appts: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for appt_id, label in appts:
        b.add(InlineKeyboardButton(text=f"❌ Отменить: {label}", callback_data=f"bk:cancel_appt:{appt_id}"))
    b.adjust(1)
    return b.as_markup()


def services_kb(services: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for service_id, name in services:
        b.add(InlineKeyboardButton(text=name, callback_data=f"bk:service:{service_id}"))
    b.adjust(1)
    b.row(InlineKeyboardButton(text="↩️ Назад", callback_data="bk:back:masters"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="bk:cancel"))
    return b.as_markup()


def calendar_14d_kb(today: dt.date) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i in range(14):
        d = today + dt.timedelta(days=i)
        label = d.strftime("%d.%m (%a)")
        b.add(InlineKeyboardButton(text=label, callback_data=f"bk:date:{d.isoformat()}"))
    b.adjust(3)
    b.row(InlineKeyboardButton(text="↩️ Назад", callback_data="bk:back:services"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="bk:cancel"))
    return b.as_markup()


def pay_kb(pay_url: str | None, payment_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if pay_url:
        kb.button(text="💳 Оплатить", url=pay_url)
    kb.button(text="✅ Я оплатил", callback_data=f"pay:done:{payment_id}")
    kb.button(text="❌ Отмена", callback_data=f"pay:cancel:{payment_id}")
    kb.adjust(1)
    return kb.as_markup()


