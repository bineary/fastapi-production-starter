from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_email_sender
from app.core.redis import get_redis
from app.main import app
from app.services.email_sender import EmailSender


class CapturingEmailSender(EmailSender):
    """Test double: records what would have been sent instead of sending it,
    so tests can pull the verification/reset token out of the "email"."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})

    def last_token(self) -> str:
        return self.sent[-1]["body"].rsplit(": ", 1)[-1]


@pytest.fixture
def email_sender() -> Iterator[CapturingEmailSender]:
    sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender
    app.dependency_overrides.pop(get_email_sender, None)


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> AsyncIterator[None]:
    """Auth-endpoint rate limiting is keyed by client IP, and httpx's
    ASGITransport gives every test the same synthetic IP — without this,
    e2e tests would rate-limit each other in test-order-dependent ways."""
    redis = get_redis()
    async for key in redis.scan_iter("rate_limit:*"):
        await redis.delete(key)
    yield


@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client wired to the app with `get_db` overridden to the per-test,
    rolled-back testcontainers session — same isolation guarantee as the
    integration tests, but exercised through real HTTP + routing + DI."""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as ac,
    ):
        yield ac
    app.dependency_overrides.pop(get_db, None)
