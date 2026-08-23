from app.core.exceptions import DomainValidationError
from app.core.pagination import Cursor, InvalidCursorError


def parse_cursor(cursor: str | None) -> Cursor | None:
    if cursor is None:
        return None
    try:
        return Cursor.decode(cursor)
    except InvalidCursorError as exc:
        raise DomainValidationError(str(exc)) from exc
