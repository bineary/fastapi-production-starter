import json
from pathlib import Path

from app.main import app

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
