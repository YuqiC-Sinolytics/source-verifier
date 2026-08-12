"""Orchestration: S0 -> S1 -> S2 -> S3/S4, streaming results as they land.

Streaming is not a nice-to-have. Ten links verified serially is ~25 seconds of
dead air, which kills a demo. Each claim is pushed up to three times:

  1. verdict in    -> the underline lights up
  2. search opened -> the panel shows "searching the web..."
  3. search closed -> replacement, or an honest "checked N, none supported it"
"""

import asyncio
import time
from typing import AsyncIterator, Dict

from .config import cfg
from .models import SEVERITY, Claim, Reach
from .parser import parse
from .reachability import resolve as resolve_reach
from .repair import repair
from .verify import verify_claim

# Anything that is not green gets a web-wide search. PARTIAL especially: an
# on-topic page missing the specific figure is exactly the case where the real
# primary source is usually one search away.
NEEDS_REPAIR = {"UNSUPPORTED", "PARTIAL", "UNREACHABLE"}


async def run(text: str, do_repair: bool = True) -> AsyncIterator[dict]:
    t0 = time.time()
    doc = parse(text)

    yield {
        "type": "start",
        "mock": cfg.mock,
        "total": len(doc.claims),
        "claims": [
            {
                "id": c.id,
                "start": c.start,
                "end": c.end,
                "link_start": c.link_start,
                "link_end": c.link_end,
                "url": c.url,
                "anchor": c.anchor,
                "display": c.display,
            }
            for c in doc.claims
        ],
    }

    if not doc.claims:
        yield {"type": "done", "elapsed_ms": int((time.time() - t0) * 1000), "summary": {}}
        return

    # ---- S1 reachability ----
    reaches: Dict[str, Reach] = await resolve_reach(doc.claims)
    yield {"type": "stage", "stage": "reachability", "elapsed_ms": int((time.time() - t0) * 1000)}

    # ---- S2 (+ S3/S4) verification, concurrent ----
    sem = asyncio.Semaphore(cfg.max_concurrency)
    queue: asyncio.Queue = asyncio.Queue()

    async def work(claim: Claim):
        async with sem:
            res = await verify_claim(claim, reaches.get(claim.url, Reach()))
            # Snapshots, not the object itself: repair mutates `res` in place and
            # a queued reference would make both pushes identical.
            await queue.put(res.to_dict())

            if not (do_repair and res.verdict in NEEDS_REPAIR):
                return

            res.searching = True
            await queue.put(res.to_dict())  # UI shows "searching the web..."
            try:
                accepted, rejected, checked = await repair(res)
            except Exception:
                accepted, rejected, checked = None, [], 0
            res.searching = False
            res.searched = True
            res.replacement = accepted
            res.rejected = rejected
            res.candidates_checked = checked
            await queue.put(res.to_dict())

    tasks = [asyncio.create_task(work(c)) for c in doc.claims]
    gather = asyncio.ensure_future(asyncio.gather(*tasks, return_exceptions=True))

    # Track the latest verdict per claim so the repair pushes do not double-count.
    final: Dict[str, str] = {}

    def emit(snapshot: dict) -> dict:
        final[snapshot["claim"]["id"]] = snapshot["verdict"]
        return {"type": "result", "result": snapshot}

    while True:
        drain = asyncio.ensure_future(queue.get())
        done, _ = await asyncio.wait({drain, gather}, return_when=asyncio.FIRST_COMPLETED)
        if drain in done:
            yield emit(drain.result())
            continue
        drain.cancel()
        while not queue.empty():
            yield emit(queue.get_nowait())
        break

    counts: Dict[str, int] = {}
    for v in final.values():
        counts[v] = counts.get(v, 0) + 1

    yield {
        "type": "done",
        "elapsed_ms": int((time.time() - t0) * 1000),
        "summary": counts,
        "worst": max((SEVERITY.get(v, -1) for v in final.values()), default=-1),
    }
