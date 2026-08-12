"""S2 — the verification engine. The heart of the project.

One design rule governs everything here: **the burden of proof sits on
SUPPORTED.** The default verdict is UNSUPPORTED, and SUPPORTED is only allowed
when the model can quote verbatim text from the page that supports the claim.

Models lean hard toward agreeable "yes, this supports it" answers. Without
inverting the burden of proof, the false-positive rate makes the whole tool
worthless — this is where products like this usually fail.
"""

import json
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

from anthropic import AsyncAnthropic

from . import cache
from .config import cfg
from .models import Claim, Reach, Result

_client: Optional[AsyncAnthropic] = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=cfg.api_key)
    return _client


SYSTEM = """You are a strict source verifier. You check whether a cited web page \
actually supports a specific claim.

RULES — follow them literally:

1. The DEFAULT verdict is UNSUPPORTED. SUPPORTED must be earned.
2. You may only answer SUPPORTED if you can quote VERBATIM text from the fetched \
page that directly supports the claim. No quote means not supported. Ever.
3. Do NOT infer. Do NOT reason "this page is about the right topic, so it probably \
supports it." Topic relevance is PARTIAL at best, never SUPPORTED.
4. Check the specifics: numbers, dates, units, magnitudes, named entities, and the \
direction of any causal statement. A page saying "grew 12%" does not support a claim \
of "grew 20%". That is UNSUPPORTED with mismatch_type "number".
5. If the page contradicts the claim, that is UNSUPPORTED, not PARTIAL.
6. If you cannot retrieve readable content (paywall, JavaScript-only page, blocked, \
empty), answer UNREACHABLE. Never guess at content you could not read.
7. Fetch the page before deciding. Do not decide from the URL alone.

Verdicts:
- SUPPORTED   : verbatim evidence directly supports the claim
- PARTIAL     : page is relevant and on-topic, but does not establish this specific \
assertion (or supports only part of it)
- UNSUPPORTED : page does not support, or actively contradicts, the claim
- UNREACHABLE : content could not be read

For PARTIAL and UNSUPPORTED, `missing_element` matters: name the exact thing that \
could not be found on the page (for example "the 89% figure", "the 2010-2023 date \
range", "the attribution to the IEA"). A separate search stage uses that string to \
look for a better source, so be specific and literal.

When finished, call submit_verdict exactly once."""

VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": "Report the verification result for this claim/source pair.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["SUPPORTED", "PARTIAL", "UNSUPPORTED", "UNREACHABLE"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_quote": {
                "type": ["string", "null"],
                "description": "Verbatim sentence(s) from the page supporting the "
                "claim. MUST be null unless verdict is SUPPORTED or PARTIAL.",
            },
            "reason": {
                "type": "string",
                "description": "One short sentence for the end user explaining the "
                "verdict. Be concrete about what was missing.",
            },
            "mismatch_type": {
                "type": "string",
                "enum": ["number", "date", "causality", "topic", "entity", "none"],
            },
            "missing_element": {
                "type": ["string", "null"],
                "description": "The exact element the page failed to establish, "
                "phrased so it can be used as a search query. Null if SUPPORTED.",
            },
        },
        "required": ["verdict", "confidence", "reason", "mismatch_type"],
    },
}


def fetch_tool(url: str, lock_domain: bool = True) -> dict:
    t = {
        "type": cfg.web_fetch_tool,
        "name": "web_fetch",
        "max_uses": 3,
        # Citations make the API hand back verbatim spans from the source, and
        # cited_text does not count toward output tokens. This is the data behind
        # the "evidence" block in the UI.
        "citations": {"enabled": True},
        "max_content_tokens": cfg.max_content_tokens,
    }
    if lock_domain:
        host = urlparse(url).netloc
        if host:
            # Pin the domain so the model cannot go find evidence elsewhere and
            # then declare the original link fine.
            t["allowed_domains"] = [host]
    return t


def _user_prompt(claim_text: str, url: str, anchor: str = "", hint: str = "") -> str:
    # A sentence can carry two links. Telling the model which span this link is
    # attached to keeps each source judged against the part it actually backs,
    # instead of against the whole sentence.
    focus = ""
    if anchor and anchor.strip() and anchor.strip() not in ("", url):
        focus = (
            f'\nThe link is attached to this span of the sentence: "{anchor.strip()}"\n'
            f"Judge whether the source supports the assertion made by that span, read "
            f"in the context of the full sentence. Other parts of the sentence may be "
            f"backed by a different source and are not your concern.\n"
        )
    return f"""Verify this claim against this source.

SENTENCE:
\"\"\"{claim_text}\"\"\"
{focus}
SOURCE URL:
{url}
{hint}
Fetch the URL, then call submit_verdict. Remember: no verbatim quote means \
not SUPPORTED."""


def _harvest(resp) -> Tuple[Optional[dict], Optional[str]]:
    """Pull submit_verdict's arguments out of the response; grab a citation too."""
    payload, cited = None, None
    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "tool_use" and getattr(block, "name", "") == "submit_verdict":
            payload = block.input
        elif btype == "text":
            for c in getattr(block, "citations", None) or []:
                if cited is None:
                    cited = getattr(c, "cited_text", None)
            if payload is None:
                payload = _loose_json(getattr(block, "text", "") or "")
    return payload, cited


def _loose_json(text: str) -> Optional[dict]:
    """Fallback for when the model writes JSON into prose instead of calling the tool."""
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return None
    try:
        d = json.loads(text[s : e + 1])
        return d if isinstance(d, dict) and "verdict" in d else None
    except json.JSONDecodeError:
        return None


async def verify_claim(claim: Claim, reach: Reach, use_cache: bool = True) -> Result:
    t0 = time.time()
    res = Result(claim=claim, reach=reach)

    # Hard failures short-circuit — no point spending an API call.
    if reach.error or (reach.status is not None and reach.status >= 400) or reach.soft_404:
        res.verdict = "UNSUPPORTED"
        res.confidence = 0.99
        res.mismatch_type = "topic"
        if reach.soft_404:
            res.reason = "Page returns HTTP 200 but serves a 'not found' placeholder."
        elif reach.error:
            res.reason = f"Could not connect ({reach.error}). The domain may not exist."
        else:
            res.reason = f"Link is dead (HTTP {reach.status})."
        res.elapsed_ms = int((time.time() - t0) * 1000)
        return res

    ck = cache.key("verify", claim.url, claim.display)
    if use_cache:
        hit = cache.get(ck)
        if hit:
            res.verdict = hit.get("verdict", "PENDING")
            res.confidence = hit.get("confidence", 0.0)
            res.evidence_quote = hit.get("evidence_quote")
            res.reason = hit.get("reason", "")
            res.mismatch_type = hit.get("mismatch_type", "none")
            res.missing_element = hit.get("missing_element")
            res.cached = True
            res.elapsed_ms = int((time.time() - t0) * 1000)
            return res

    if cfg.mock:
        from .mock import mock_verify

        payload = mock_verify(claim.url, claim.display)
    else:
        hint = f"\nPage title seen by our crawler: {reach.title!r}\n" if reach.title else ""
        try:
            resp = await client().messages.create(
                model=cfg.verify_model,
                max_tokens=2048,
                system=SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": _user_prompt(claim.display, claim.url, claim.anchor, hint),
                    }
                ],
                tools=[fetch_tool(claim.url), VERDICT_TOOL],
            )
            payload, cited = _harvest(resp)
            if payload and not payload.get("evidence_quote") and cited:
                payload["evidence_quote"] = cited
        except Exception as e:
            res.verdict = "UNREACHABLE"
            res.reason = f"Verification call failed: {type(e).__name__}"
            res.elapsed_ms = int((time.time() - t0) * 1000)
            return res

    if not payload:
        res.verdict = "UNREACHABLE"
        res.reason = "The model returned no structured verdict."
        res.elapsed_ms = int((time.time() - t0) * 1000)
        return res

    res.verdict = payload.get("verdict", "UNSUPPORTED")
    res.confidence = float(payload.get("confidence") or 0.0)
    res.reason = payload.get("reason", "")
    res.mismatch_type = payload.get("mismatch_type", "none")
    res.evidence_quote = payload.get("evidence_quote")
    res.missing_element = payload.get("missing_element")

    # Code-level backstop for the one rule that matters: no verbatim quote, no
    # SUPPORTED. Prompts get talked around; this line does not. Do not delete it.
    if res.verdict == "SUPPORTED" and not (res.evidence_quote or "").strip():
        res.verdict = "PARTIAL"
        res.reason = (res.reason + " ").strip() + " (Downgraded: no verbatim evidence.)"
        res.confidence = min(res.confidence, 0.5)

    cache.put(
        ck,
        {
            "verdict": res.verdict,
            "confidence": res.confidence,
            "evidence_quote": res.evidence_quote,
            "reason": res.reason,
            "mismatch_type": res.mismatch_type,
            "missing_element": res.missing_element,
        },
    )
    res.elapsed_ms = int((time.time() - t0) * 1000)
    return res
