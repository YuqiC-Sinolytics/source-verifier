"""S1 — link liveness.

Cheap and fast, and it eliminates a batch of links before any model is called.
The actual judgement stays in S2.
"""

import asyncio
import re
from typing import List

import httpx

from .models import Claim, Reach

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

SOFT_404 = re.compile(
    r"(page not found|404 not found|404 error|we can'?t find|"
    r"page (you (are )?(requested|looking for) )?(does not|doesn'?t) exist|"
    r"no longer available|content unavailable|this page has moved)",
    re.I,
)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


async def _one(client: httpx.AsyncClient, url: str) -> Reach:
    try:
        # GET, not HEAD — too many sites answer HEAD with 405 or lie about it.
        r = await client.get(url, headers={"User-Agent": UA})
    except httpx.TimeoutException:
        return Reach(ok=False, error="timeout")
    except httpx.HTTPError as e:
        return Reach(ok=False, error=type(e).__name__)
    except Exception as e:  # DNS and friends
        return Reach(ok=False, error=str(e)[:120])

    body = r.text[:20000] if "text" in r.headers.get("content-type", "") else ""
    tm = TITLE.search(body)
    title = re.sub(r"\s+", " ", tm.group(1)).strip()[:200] if tm else None

    soft = False
    if r.status_code == 200:
        probe = f"{title or ''} {body[:3000]}"
        # Either the title says it, or the body says it and the page is oddly short.
        if SOFT_404.search(title or "") or (SOFT_404.search(probe) and len(body) < 8000):
            soft = True

    return Reach(
        ok=r.status_code < 400 and not soft,
        status=r.status_code,
        final_url=str(r.url),
        redirected=str(r.url).rstrip("/") != url.rstrip("/"),
        soft_404=soft,
        title=title,
    )


async def check_all(claims: List[Claim], concurrency: int = 8) -> dict:
    """Returns {url: Reach}. Each distinct URL is probed once."""
    urls = list({c.url for c in claims})
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency)

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=12.0, limits=limits, verify=False
    ) as client:

        async def guarded(u: str):
            async with sem:
                return u, await _one(client, u)

        return dict(await asyncio.gather(*(guarded(u) for u in urls)))


async def resolve(claims: List[Claim]) -> dict:
    """Single entry point for liveness. MOCK mode issues no HTTP at all.

    Both the pipeline and eval.py go through here so the two cannot drift apart.
    """
    from .config import cfg

    if cfg.mock:
        from .mock import mock_reach

        return mock_reach([c.url for c in claims])
    return await check_all(claims)
