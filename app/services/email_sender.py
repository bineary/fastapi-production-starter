from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger(__name__)


class EmailSender(ABC):
    """Boundary for outbound email. Swap in a real provider (SES, Postmark,
    ...) by implementing this — nothing else in the app needs to change."""

    @abstractmethod
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender(EmailSender):
    """Reference implementation: logs the email instead of sending it, so
    verification/reset flows are runnable end-to-end without a mail provider."""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info("email.sent", to=to, subject=subject, body=body)
