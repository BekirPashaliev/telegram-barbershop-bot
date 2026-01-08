from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, Time,
    func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ENUM, JSONB


class Base(DeclarativeBase):
    pass


# ---- ENUMs ----
user_role_enum = ENUM("user", "master", "admin", name="user_role", create_type=True)

appointment_status_enum = ENUM(
    "pending_payment",   # NEW
    "active",
    "cancelled",
    name="appointment_status",
    create_type=True,
)

payment_status_enum = ENUM(
    "pending", "paid", "failed", "refunded", "cancelled",
    name="payment_status",
    create_type=True,
)

payment_provider_enum = ENUM(
    "dummy", "yookassa", "stripe",
    name="payment_provider",
    create_type=True,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram ID
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reg_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    role: Mapped[str] = mapped_column(user_role_enum, nullable=False, server_default="user")  # NEW

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="user")
    audit_events: Mapped[list["AuditLog"]] = relationship(back_populates="actor_user")


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    tg_user_id: Mapped[int | None] = mapped_column(  # NEW: привязка мастера к TG-пользователю (для роли master)
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    tg_user: Mapped[User | None] = relationship(foreign_keys=[tg_user_id])

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="master")
    working_hours: Mapped[list["MasterWorkingHours"]] = relationship(back_populates="master", cascade="all, delete-orphan")
    breaks: Mapped[list["MasterBreak"]] = relationship(back_populates="master", cascade="all, delete-orphan")
    days_off: Mapped[list["MasterDayOff"]] = relationship(back_populates="master", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="service")


# ---- Schedule tables (пункт 2) ----
class MasterWorkingHours(Base):
    __tablename__ = "master_working_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int] = mapped_column(Integer, ForeignKey("masters.id", ondelete="CASCADE"), nullable=False)

    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon ... 6=Sun
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)

    master: Mapped["Master"] = relationship(back_populates="working_hours")


class MasterBreak(Base):
    __tablename__ = "master_breaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int] = mapped_column(Integer, ForeignKey("masters.id", ondelete="CASCADE"), nullable=False)

    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)

    master: Mapped["Master"] = relationship(back_populates="breaks")


class MasterDayOff(Base):
    __tablename__ = "master_days_off"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int] = mapped_column(Integer, ForeignKey("masters.id", ondelete="CASCADE"), nullable=False)

    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    master: Mapped["Master"] = relationship(back_populates="days_off")


# ---- Payments (пункт 5) ----
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(payment_provider_enum, nullable=False, server_default="dummy")
    status: Mapped[str] = mapped_column(payment_status_enum, nullable=False, server_default="pending")

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="RUB")

    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pay_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---- Audit (пункт 1) ----
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False)      # e.g. "add_master"
    entity: Mapped[str] = mapped_column(String(64), nullable=False)      # e.g. "Master"
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor_user: Mapped[User | None] = relationship(
       back_populates = "audit_events",
       foreign_keys = [actor_user_id],
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    master_id: Mapped[int] = mapped_column(Integer, ForeignKey("masters.id", ondelete="CASCADE"), nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("services.id", ondelete="RESTRICT"), nullable=False)

    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(appointment_status_enum, nullable=False, server_default="active")

    payment_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)  # NEW

    reminded_24h: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    reminded_1h: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="appointments")
    master: Mapped["Master"] = relationship(back_populates="appointments")
    service: Mapped["Service"] = relationship(back_populates="appointments")
    payment: Mapped[Payment | None] = relationship(foreign_keys=[payment_id])
