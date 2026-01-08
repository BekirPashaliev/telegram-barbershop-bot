from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy import delete
from app.database.models import (
    AuditLog, MasterWorkingHours, MasterBreak, MasterDayOff, Payment
)

from app.database.models import Appointment, Master, Service, User


@dataclass(frozen=True)
class SlotSettings:
    tz: dt.tzinfo
    work_start_hour: int
    work_end_hour: int
    slot_minutes: int


async def add_user(session: AsyncSession, tg_id: int, username: str | None) -> None:
    existing = await session.get(User, tg_id)
    if existing:
        if username and existing.username != username:
            existing.username = username
        return
    session.add(User(id=tg_id, username=username))



async def set_user_phone(session: AsyncSession, tg_id: int, phone_number: str) -> None:
    """Save/overwrite user's phone number."""
    phone_number = (phone_number or "").strip()
    if not phone_number:
        return
    user = await session.get(User, tg_id)
    if not user:
        user = User(id=tg_id, username=None)
        session.add(user)
        await session.flush()
    user.phone_number = phone_number
    # commit is handled by middleware / caller


async def list_masters(session: AsyncSession) -> list[Master]:
    res = await session.execute(select(Master).order_by(Master.name.asc()))
    return list(res.scalars().all())


async def list_services(session: AsyncSession) -> list[Service]:
    res = await session.execute(select(Service).order_by(Service.name.asc()))
    return list(res.scalars().all())


async def ensure_seed_service(session: AsyncSession) -> None:
    res = await session.execute(select(Service.id).limit(1))
    if res.first():
        return
    session.add(Service(name="Стрижка", description="Базовая стрижка", duration_minutes=60, price_cents=150000))


def _day_bounds(date_: dt.date, tz: dt.tzinfo) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(date_.year, date_.month, date_.day, 0, 0, tzinfo=tz)
    end = start + dt.timedelta(days=1)
    return start, end


def build_slot_starts(date_: dt.date, s: SlotSettings) -> list[dt.datetime]:
    start = dt.datetime(date_.year, date_.month, date_.day, s.work_start_hour, 0, tzinfo=s.tz)
    end = dt.datetime(date_.year, date_.month, date_.day, s.work_end_hour, 0, tzinfo=s.tz)

    out: list[dt.datetime] = []
    step = dt.timedelta(minutes=s.slot_minutes)
    cur = start
    while cur < end:
        out.append(cur)
        cur += step
    return out


async def get_free_slots(
    session: AsyncSession,
    master_id: int,
    service_id: int,
    date_: dt.date,
    s: SlotSettings,
    now: dt.datetime | None = None,
) -> list[dt.datetime]:
    now = now or dt.datetime.now(tz=s.tz)

    service = await session.get(Service, service_id)
    if not service:
        return []

    duration = dt.timedelta(minutes=int(service.duration_minutes))

    day_start, day_end = _day_bounds(date_, s.tz)

    # fetch busy intervals for this master, intersecting the day
    res = await session.execute(
        select(Appointment.starts_at, Appointment.ends_at).where(
            and_(
                Appointment.master_id == master_id,
                Appointment.status.in_(["active", "pending_payment"]),
                Appointment.starts_at < day_end,
                Appointment.ends_at > day_start,
            )
        )
    )
    busy = list(res.all())  # list[(starts_at, ends_at)]

    schedule, breaks = await get_master_schedule_for_day(
        session=session,
        master_id=master_id,
        date_=date_,
        tz=s.tz,
        fallback_start_hour=s.work_start_hour,
        fallback_end_hour=s.work_end_hour,
    )
    if not schedule:
        return []
    work_start, work_end = schedule

    # slot starts строим от work_start, а не от fixed hours
    slot_starts = []
    cur = work_start
    step = dt.timedelta(minutes=s.slot_minutes)
    while cur < work_end:
        slot_starts.append(cur)
        cur += step

    free: list[dt.datetime] = []
    for start_at in slot_starts:
        end_at = start_at + duration

        # don’t go outside working hours
        if end_at > work_end:
            continue

        # don’t allow in the past for today
        if date_ == now.date() and start_at <= now:
            continue

        # overlap check
        overlapped = False
        for b_start, b_end in busy:
            if start_at < b_end and end_at > b_start:
                overlapped = True
                break
        if overlapped:
            continue

        # break overlap
        in_break = False
        for br_start, br_end in breaks:
            if start_at < br_end and end_at > br_start:
                in_break = True
                break
        if in_break:
            continue


        free.append(start_at)

    return free


async def create_appointment_acid(
    session: AsyncSession,
    user_id: int,
    master_id: int,
    service_id: int,
    starts_at: dt.datetime,
) -> Appointment | None:
    service = await session.get(Service, service_id)
    if not service:
        return None

    ends_at = starts_at + dt.timedelta(minutes=int(service.duration_minutes))

    try:
        tx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx:
            appt = Appointment(
                user_id=user_id,
                master_id=master_id,
                service_id=service_id,
                starts_at=starts_at,
                ends_at=ends_at,
                status="active",
                reminded_24h=False,
                reminded_1h=False,
            )
            session.add(appt)
        return appt
    except IntegrityError:
        # Транзакция/сейвпоинт выше откатывается контекст-менеджером.
        # Здесь НЕ делаем session.rollback(), иначе можно откатить чужие изменения.
        return None


async def get_future_appointments(session: AsyncSession, user_id: int, now: dt.datetime) -> list[Appointment]:
    res = await session.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.master),
            selectinload(Appointment.service),
            selectinload(Appointment.payment),  # чтобы при pending показать pay_url
        )
        .where(
            and_(
                Appointment.user_id == user_id,
                Appointment.status.in_(["active", "pending_payment"]),
                Appointment.starts_at > now,
            )
        )
        .order_by(Appointment.starts_at.asc())
    )
    return list(res.scalars().all())



async def cancel_appointment(session: AsyncSession, user_id: int, appointment_id: int) -> bool:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        res = await session.execute(
            update(Appointment)
            .where(and_(
                Appointment.id == appointment_id,
                Appointment.user_id == user_id,
                Appointment.status.in_(["active", "pending_payment"]),
            ))
            .values(status="cancelled")
            .returning(Appointment.id, Appointment.payment_id)
        )
        row = res.first()
        if not row:
            return False
        _, pay_id = row
        if pay_id:
            p = await session.get(Payment, pay_id)
            if p and p.status == "pending":
                p.status = "cancelled"
        return True

async def cancel_payment_and_cancel_appointment(
    session: AsyncSession,
    payment_id: int,
    user_id: int,
) -> bool:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        p = await session.get(Payment, payment_id)
        if not p or p.status != "pending":
            return False

        res = await session.execute(
            select(Appointment).where(
                and_(
                    Appointment.payment_id == payment_id,
                    Appointment.user_id == user_id,
                    Appointment.status == "pending_payment",
                )
            ).limit(1)
        )
        appt = res.scalars().first()
        if not appt:
            return False

        appt.status = "cancelled"
        p.status = "cancelled"
        return True


async def get_today_appointments(session: AsyncSession, tz: dt.tzinfo, today: dt.date) -> list[Appointment]:
    day_start, day_end = _day_bounds(today, tz)
    res = await session.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.master),
            selectinload(Appointment.service),
            selectinload(Appointment.user),
        )
        .where(
            and_(
                Appointment.status == "active",
                Appointment.starts_at >= day_start,
                Appointment.starts_at < day_end,
            )
        )
        .order_by(Appointment.starts_at.asc())
    )
    return list(res.scalars().all())



async def add_master(session: AsyncSession, name: str, description: str | None) -> Master:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        m = Master(name=name.strip(), description=(description.strip() if description else None))
        session.add(m)
    return m


async def add_service(session: AsyncSession, name: str, description: str | None, duration_minutes: int, price_cents: int) -> Service:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        s = Service(
            name=name.strip(),
            description=(description.strip() if description else None),
            duration_minutes=int(duration_minutes),
            price_cents=int(price_cents),
        )
        session.add(s)
    return s


# ---- RBAC ----
async def get_user_role(session: AsyncSession, user_id: int) -> str | None:
    u = await session.get(User, user_id)
    return u.role if u else None

async def set_user_role(session: AsyncSession, user_id: int, role: str) -> None:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        u = await session.get(User, user_id)
        if not u:
            u = User(id=user_id, username=None, role=role)
            session.add(u)
        else:
            u.role = role

async def audit(session: AsyncSession, actor_user_id: int | None, action: str, entity: str, entity_id: int | None, meta: dict | None = None) -> None:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        session.add(AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            meta=meta,
        ))

# ---- Schedule CRUD ----
async def upsert_working_hours(session: AsyncSession, master_id: int, weekday: int, start: dt.time, end: dt.time) -> None:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        await session.execute(
            delete(MasterWorkingHours).where(
                and_(MasterWorkingHours.master_id == master_id, MasterWorkingHours.weekday == weekday)
            )
        )
        session.add(MasterWorkingHours(master_id=master_id, weekday=weekday, start_time=start, end_time=end))

async def add_break(session: AsyncSession, master_id: int, weekday: int, start: dt.time, end: dt.time) -> None:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        session.add(MasterBreak(master_id=master_id, weekday=weekday, start_time=start, end_time=end))

async def add_day_off(session: AsyncSession, master_id: int, date_: dt.date, reason: str | None = None) -> None:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        session.add(MasterDayOff(master_id=master_id, date=date_, reason=reason))

async def get_master_schedule_for_day(
    session: AsyncSession,
    master_id: int,
    date_: dt.date,
    tz: dt.tzinfo,
    fallback_start_hour: int,
    fallback_end_hour: int,
) -> tuple[tuple[dt.datetime, dt.datetime] | None, list[tuple[dt.datetime, dt.datetime]]]:
    # day off?
    off = await session.execute(
        select(MasterDayOff.id).where(and_(MasterDayOff.master_id == master_id, MasterDayOff.date == date_)).limit(1)
    )
    if off.first():
        return None, []

    wd = date_.weekday()

    wh = await session.execute(
        select(MasterWorkingHours).where(and_(MasterWorkingHours.master_id == master_id, MasterWorkingHours.weekday == wd)).limit(1)
    )
    wh_row = wh.scalars().first()

    if wh_row:
        start_dt = dt.datetime.combine(date_, wh_row.start_time, tzinfo=tz)
        end_dt = dt.datetime.combine(date_, wh_row.end_time, tzinfo=tz)
    else:
        start_dt = dt.datetime(date_.year, date_.month, date_.day, fallback_start_hour, 0, tzinfo=tz)
        end_dt = dt.datetime(date_.year, date_.month, date_.day, fallback_end_hour, 0, tzinfo=tz)

    br = await session.execute(
        select(MasterBreak).where(and_(MasterBreak.master_id == master_id, MasterBreak.weekday == wd))
    )
    breaks = []
    for b in br.scalars().all():
        b_start = dt.datetime.combine(date_, b.start_time, tzinfo=tz)
        b_end = dt.datetime.combine(date_, b.end_time, tzinfo=tz)
        breaks.append((b_start, b_end))

    return (start_dt, end_dt), breaks

# ---- Payments ----
async def create_payment(session: AsyncSession, provider: str, amount_cents: int, currency: str = "RUB", external_id: str | None = None, pay_url: str | None = None) -> Payment:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        p = Payment(provider=provider, status="pending", amount_cents=amount_cents, currency=currency, external_id=external_id, pay_url=pay_url)
        session.add(p)
        await session.flush()  # чтобы появился p.id прямо сейчас
        if not p.pay_url and provider == "dummy":
            p.pay_url = f"https://example.com/pay/dummy/{p.id}"
    return p

async def mark_payment_paid(session: AsyncSession, payment_id: int) -> bool:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        p = await session.get(Payment, payment_id)
        if not p:
            return False
        if p.status == "paid":
            return True
        if p.status != "pending":
            return False
        p.status = "paid"
        p.paid_at = dt.datetime.now(dt.timezone.utc)
        return True


async def create_appointment_with_payment_acid(
    session: AsyncSession,
    user_id: int,
    master_id: int,
    service_id: int,
    starts_at: dt.datetime,
    provider: str = "dummy",
) -> tuple[Appointment, Payment] | None:
    service = await session.get(Service, service_id)
    if not service:
        return None

    ends_at = starts_at + dt.timedelta(minutes=int(service.duration_minutes))
    amount = int(service.price_cents)

    try:
        tx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx:
            # 1) создаём платёж
            payment = Payment(
                provider=provider,
                status="pending",
                amount_cents=amount,
                currency="RUB",
            )
            session.add(payment)
            await session.flush()  # получить payment.id

            if not payment.pay_url and provider == "dummy":
                payment.pay_url = f"https://example.com/pay/dummy/{payment.id}"

            # 2) создаём запись, но НЕ активируем
            appt = Appointment(
                user_id=user_id,
                master_id=master_id,
                service_id=service_id,
                starts_at=starts_at,
                ends_at=ends_at,
                status="pending_payment",
                payment_id=payment.id,
                reminded_24h=False,
                reminded_1h=False,
            )
            session.add(appt)
            await session.flush()  # на всякий (appt.id)

        return appt, payment
    except IntegrityError:
        # Транзакция/сейвпоинт выше откатывается контекст-менеджером.
        # Здесь НЕ делаем session.rollback(), иначе можно откатить чужие изменения.
        return None

async def mark_payment_paid_and_activate_appointment(
    session: AsyncSession,
    payment_id: int,
    user_id: int,
) -> Appointment | None:
    tx = session.begin_nested() if session.in_transaction() else session.begin()
    async with tx:
        # ЛОЧИМ платёж, чтобы не было гонок при параллельных кликах
        p = (
            await session.execute(
                select(Payment).where(Payment.id == payment_id).with_for_update()
            )
        ).scalars().first()
        if not p:
            return None

        # И сразу вытаскиваем запись именно этого пользователя (и тоже можно залочить)
        appt = (
            await session.execute(
                select(Appointment)
                .where(and_(Appointment.payment_id == payment_id, Appointment.user_id == user_id))
                .with_for_update()
                .limit(1)
            )
        ).scalars().first()
        if not appt:
            return None

        # если уже отменено — не подтверждаем
        if appt.status == "cancelled" or p.status == "cancelled":
            return None

        # идемпотентность:
        # - если уже paid -> просто гарантируем active и возвращаем
        if p.status == "paid":
            if appt.status == "pending_payment":
                appt.status = "active"
            return appt

        # нормальный сценарий: pending -> paid + pending_payment -> active
        if p.status != "pending":
            return None

        p.status = "paid"
        p.paid_at = dt.datetime.now(dt.timezone.utc)

        if appt.status != "pending_payment":
            return None

        appt.status = "active"
        return appt

