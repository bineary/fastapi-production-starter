from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as ac,
    ):
        yield ac


def _run_migrations(url: str) -> None:
    # Our alembic env.py always connects with the async (asyncpg) engine,
    # so this needs the same asyncpg DSN the app itself uses — not a sync one.
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def postgres_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        _run_migrations(url)
        yield url


@pytest.fixture(scope="session")
async def db_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """One test = one rolled-back transaction, even if code under test commits."""
    async with db_engine.connect() as connection:
        await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        async with session_factory() as session:
            yield session
        await connection.rollback()
