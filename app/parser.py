"""S0 — split the document into (sentence, link) pairs.

Deliberately no LLM here: rules are faster and far more stable for this, and
there is no credit to be won at this stage. Spend the model budget on S2.

Two spans are recorded per claim:
  * start / end            the sentence, which is what gets verified
  * link_start / link_end  the `[anchor](url)` construct, which is what gets
                           underlined in the UI
"""

import hashlib
import re
from typing import List, Tuple

from .models import Claim, Document

MD_LINK = re.compile(r"\[([^\]\n]*)\]\(\s*(https?://[^\s\)]+?)\s*\)")
BARE_URL = re.compile(r"(?<![\(\]])\bhttps?://[^\s<>\)\]]+")
SENT_SPLIT = re.compile(
    r"(?<=[.!?。！？])[ \t]*\n"  # terminator + newline
    r"|(?<=[.!?。！？])[ \t]+"  # terminator + space
    r"|(?<=[。！？])"  # CJK terminators are rarely followed by a space
    r"|\n{2,}"  # blank line
    r"|\n(?=[#\-*>\|])"  # newline + markdown block marker
)
TRAILING_PUNCT = ".,;:!?)]}。，；：！？"


def _mask(text: str) -> str:
    """Replace link constructs with an equal-length run of X.

    This keeps every character offset identical to the original while hiding
    periods inside anchors ("[U.S. Census](...)") and slashes inside URLs from
    the sentence splitter.
    """
    out = list(text)
    for m in list(MD_LINK.finditer(text)) + list(BARE_URL.finditer(text)):
        for i in range(m.start(), m.end()):
            out[i] = "X"
    return "".join(out)


def sentence_spans(text: str) -> List[Tuple[int, int]]:
    masked = _mask(text)
    spans, cursor = [], 0
    for m in SENT_SPLIT.finditer(masked):
        if m.end() > cursor:
            spans.append((cursor, m.end()))
            cursor = m.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def strip_markdown(s: str) -> str:
    s = MD_LINK.sub(r"\1", s)
    s = re.sub(r"^[#>\s\-\*]+", "", s)
    s = re.sub(r"[*_`]", "", s)
    return s.strip()


def _clean_url(u: str) -> str:
    return u.rstrip(TRAILING_PUNCT)


def parse(text: str) -> Document:
    spans = sentence_spans(text)

    def owning_span(pos: int) -> Tuple[int, int]:
        for s, e in spans:
            if s <= pos < e:
                return s, e
        return 0, len(text)

    # (link_start, link_end, url, anchor)
    found: List[Tuple[int, int, str, str]] = []
    for m in MD_LINK.finditer(text):
        found.append((m.start(), m.end(), _clean_url(m.group(2)), m.group(1).strip()))
    taken = [(m.start(), m.end()) for m in MD_LINK.finditer(text)]
    for m in BARE_URL.finditer(text):
        if any(s <= m.start() < e for s, e in taken):
            continue  # already inside a markdown link
        url = _clean_url(m.group(0))
        found.append((m.start(), m.start() + len(url), url, url))

    claims: List[Claim] = []
    seen = set()
    for ls, le, url, anchor in sorted(found):
        s, e = owning_span(ls)
        if (s, url) in seen:
            continue
        seen.add((s, url))
        claims.append(
            Claim(
                id=hashlib.sha1(f"{ls}|{url}".encode()).hexdigest()[:10],
                sentence=text[s:e].strip(),
                display=strip_markdown(text[s:e]),
                url=url,
                anchor=anchor or url,
                start=s,
                end=e,
                link_start=ls,
                link_end=le,
            )
        )
    return Document(text=text, claims=claims)
