import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Cursor:
    """Keyset pagination position: the (created_at, id) of the last row seen."""

    created_at: datetime
    id: uuid.UUID

    def encode(self) -> str:
        payload = {"created_at": self.created_at.isoformat(), "id": str(self.id)}
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

    @classmethod
    def decode(cls, cursor: str) -> "Cursor":
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            return cls(
                created_at=datetime.fromisoformat(payload["created_at"]),
                id=uuid.UUID(payload["id"]),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidCursorError(cursor) from exc


class InvalidCursorError(ValueError):
    def __init__(self, cursor: str) -> None:
        self.cursor = cursor
        super().__init__(f"Invalid pagination cursor: {cursor!r}")
