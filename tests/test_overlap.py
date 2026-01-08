import datetime as dt
import os
import subprocess

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from testcontainers.postgres import PostgresContainer

from app.database.models import Master, Service, Appointment, User


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Spin up Postgres in Docker and apply alembic migrations."""
    with PostgresContainer("postgres:16") as pg:
        sync_url = pg.get_connection_url()  # postgresql://...
        async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        env = os.environ.copy()
        env["DATABASE_URL"] = async_url
        # Alembic needs repo root in sys.path
        env["PYTHONPATH"] = os.getcwd()

        subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)

        yield async_url


@pytest.mark.asyncio
async def test_no_overlap(pg_url: str):
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        async with s.begin():
            s.add_all([
                User(id=1, username="u1"),
                Master(name="M1"),
                Service(name="S1", duration_minutes=60, price_cents=10000),
            ])

    async with Session() as s:
        async with s.begin():
            m = (await s.execute(select(Master))).scalars().first()
            srv = (await s.execute(select(Service))).scalars().first()

            t0 = dt.datetime(2026, 1, 8, 10, 0, tzinfo=dt.timezone.utc)
            a1 = Appointment(
                user_id=1,
                master_id=m.id,
                service_id=srv.id,
                starts_at=t0,
                ends_at=t0 + dt.timedelta(hours=1),
                status="active",
            )
            s.add(a1)

    # Overlapping appointment must fail (EXCLUDE constraint)
    async with Session() as s:
        with pytest.raises(IntegrityError):
            async with s.begin():
                m = (await s.execute(select(Master))).scalars().first()
                srv = (await s.execute(select(Service))).scalars().first()

                t0 = dt.datetime(2026, 1, 8, 10, 30, tzinfo=dt.timezone.utc)
                a2 = Appointment(
                    user_id=1,
                    master_id=m.id,
                    service_id=srv.id,
                    starts_at=t0,
                    ends_at=t0 + dt.timedelta(hours=1),
                    status="active",
                )
                s.add(a2)

    await engine.dispose()
