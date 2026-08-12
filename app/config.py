import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    verify_model = os.getenv("VERIFY_MODEL", "claude-sonnet-5")
    repair_model = os.getenv("REPAIR_MODEL", "claude-sonnet-5")

    web_fetch_tool = os.getenv("WEB_FETCH_TOOL", "web_fetch_20260318")
    web_search_tool = os.getenv("WEB_SEARCH_TOOL", "web_search_20250305")

    max_concurrency = _int("MAX_CONCURRENCY", 6)
    max_content_tokens = _int("MAX_CONTENT_TOKENS", 30000)

    cache_dir = ROOT / ".cache"

    @property
    def mock(self) -> bool:
        """No key means mock mode, so the project always runs out of the box."""
        if os.getenv("MOCK", "0") == "1":
            return True
        return not self.api_key


cfg = Config()
