"""S3 + S4 — find the right source, and make it clear the same bar.

Two rules:

1. A candidate is only ever recommended after passing the **exact same S2
   verification** the original link failed. A recommendation that cannot clear
   your own standard is worse than no recommendation.

2. "No reliable source found" is only allowed to be said **after** candidates
   were actually fetched and rejected. Never as a shortcut for "I did not look."
   A tool that admits it cannot find something is far more credible than one
   that always produces a link — but it has to have looked first.

The PARTIAL case is the important one: the page is on-topic but the specific
figure is not on it. That is exactly when a web-wide search is most likely to
find the real primary source, so it always gets searched.
"""

from typing import List, Optional, Tuple

from . import cache
from .config import cfg
from .models import Candidate, Claim, Reach, Result
from .verify import client, verify_claim

SEARCH_SYSTEM = """You find primary sources that can substantiate a specific factual \
claim.

Prefer the original source (statistics agency, the report or paper itself, the \
company's own filing) over news coverage, blogs, or aggregators.

The claim has already been checked against one page and that page did not establish \
it. You will be told exactly which element was missing — a figure, a date range, an \
attribution. Target that element: propose pages that are likely to state it \
explicitly, not pages that are merely about the same subject.

Do not judge whether the pages truly support the claim; a separate strict verifier \
fetches and checks each one. Surface the best 3-4 candidates, then call \
propose_candidates once."""

CANDIDATES_TOOL = {
    "name": "propose_candidates",
    "description": "Report candidate source URLs for the claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "why": {
                            "type": "string",
                            "description": "One short sentence on why this page is "
                            "likely to state the missing element.",
                        },
                    },
                    "required": ["url", "title"],
                },
            }
        },
        "required": ["candidates"],
    },
}


def _query_context(result: Result) -> str:
    """Turn the failed verification into a targeted search brief."""
    missing = (result.missing_element or "").strip()
    if missing:
        return f"The cited page does not state {missing}. Find a source that does."
    if result.mismatch_type == "number":
        return "The cited page does not contain the figure stated in the claim."
    if result.mismatch_type == "date":
        return "The cited page does not cover the time period stated in the claim."
    if result.verdict == "UNREACHABLE":
        return (
            "The cited page could not be read (paywall or JavaScript-only). "
            "Prefer an openly accessible source."
        )
    return "The cited page is on-topic but does not establish this specific assertion."


async def find_candidates(result: Result) -> List[Candidate]:
    claim_text = result.claim.display
    bad_url = result.claim.url
    context = _query_context(result)

    ck = cache.key("search", claim_text, context)
    hit = cache.get(ck)
    if hit is not None:
        return [Candidate(**c) for c in hit]

    if cfg.mock:
        from .mock import mock_candidates

        out = mock_candidates(claim_text, bad_url)
    else:
        prompt = (
            f'Find sources that can substantiate this claim:\n\n"""{claim_text}"""\n\n'
            f"{context}\n\n"
            f"The currently cited URL is {bad_url} — do not propose it again."
        )
        try:
            resp = await client().messages.create(
                model=cfg.repair_model,
                max_tokens=2048,
                system=SEARCH_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                tools=[
                    {"type": cfg.web_search_tool, "name": "web_search", "max_uses": 3},
                    CANDIDATES_TOOL,
                ],
            )
        except Exception:
            return []

        out = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "propose_candidates":
                for c in (block.input or {}).get("candidates", []):
                    url = (c.get("url") or "").strip()
                    if url and url.rstrip("/") != bad_url.rstrip("/"):
                        out.append(
                            Candidate(url=url, title=c.get("title", ""), why=c.get("why", ""))
                        )

    cache.put(ck, [{"url": c.url, "title": c.title, "why": c.why} for c in out])
    return out


async def repair(result: Result) -> Tuple[Optional[Candidate], List[Candidate], int]:
    """Search the whole web for a better source for a claim that failed.

    Returns (accepted, rejected, checked_count). `accepted` is None only after
    every candidate has been fetched and verified — so the UI can honestly say
    how many alternatives were examined before giving up.
    """
    claim = result.claim
    candidates = await find_candidates(result)
    if not candidates:
        return None, [], 0

    accepted: Optional[Candidate] = None
    rejected: List[Candidate] = []
    checked = 0

    for cand in candidates[:3]:
        probe = Claim(
            id=f"{claim.id}-cand{checked}",
            sentence=claim.sentence,
            display=claim.display,
            url=cand.url,
            anchor=cand.title,
            start=claim.start,
            end=claim.end,
            link_start=claim.link_start,
            link_end=claim.link_end,
        )
        # Same verify_claim, same system prompt, same "verbatim quote required" gate.
        r = await verify_claim(probe, Reach(ok=True), use_cache=True)
        checked += 1
        cand.verdict = r.verdict
        cand.evidence_quote = r.evidence_quote
        cand.reason = r.reason
        cand.confidence = r.confidence

        if r.verdict == "SUPPORTED":
            accepted = cand
            break
        if r.verdict == "PARTIAL" and accepted is None:
            accepted = cand  # keep as runner-up, but keep looking for a real hit
            continue
        rejected.append(cand)

    return accepted, rejected, checked
