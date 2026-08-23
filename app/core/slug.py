import re
import uuid


def slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "org"
    return f"{base}-{uuid.uuid4().hex[:8]}"
