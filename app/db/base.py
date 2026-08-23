from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base; model modules register their tables on this metadata."""
