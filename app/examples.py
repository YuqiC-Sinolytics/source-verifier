"""Built-in example documents.

Each file in samples/examples/ may start with `<!-- title: ... -->`, which is
stripped before the text reaches the parser so it never shows up as prose.
"""

import re
from pathlib import Path
from typing import List

from .config import ROOT

TITLE_RE = re.compile(r"^\s*<!--\s*title:\s*(.+?)\s*-->\s*\n", re.I)
DIR = ROOT / "samples" / "examples"


def strip_title(raw: str) -> str:
    return TITLE_RE.sub("", raw, count=1).strip() + "\n"


def load_all() -> List[dict]:
    out = []
    for p in sorted(DIR.glob("*.md")) if DIR.exists() else []:
        raw = p.read_text("utf-8")
        m = TITLE_RE.match(raw)
        out.append(
            {
                "id": p.stem,
                "title": m.group(1) if m else p.stem.replace("-", " ").title(),
                "text": strip_title(raw),
            }
        )
    return out


def first_path() -> Path:
    files = sorted(DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"No example files found in {DIR}")
    return files[0]
