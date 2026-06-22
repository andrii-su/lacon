"""Package the lacon skill into a distributable lacon.skill zip file."""

import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SOURCE = REPO_ROOT / "skills" / "lacon" / "SKILL.md"
OUTPUT = REPO_ROOT / "lacon.skill"
ZIP_ENTRY = "lacon/SKILL.md"


def build() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source not found: {SOURCE}")

    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(SOURCE, ZIP_ENTRY)

    print(f"Built lacon.skill ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
