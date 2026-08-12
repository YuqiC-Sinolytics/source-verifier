from dataclasses import dataclass, field, asdict
from typing import Optional, List, Literal

Verdict = Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED", "UNREACHABLE", "PENDING"]

# Higher = worse. Used to pick the worst verdict when one sentence cites several
# sources, and to decide what is worth spending a repair search on.
SEVERITY = {
    "SUPPORTED": 0,
    "PARTIAL": 1,
    "UNREACHABLE": 2,
    "UNSUPPORTED": 3,
    "PENDING": -1,
}


@dataclass
class Claim:
    """One claim = a sentence plus the link attached to it."""

    id: str
    sentence: str  # raw markdown sentence
    display: str  # readable text with link syntax stripped
    url: str
    anchor: str  # the link's anchor text
    start: int  # char offset of the sentence in the source text
    end: int
    link_start: int  # char offset of the `[anchor](url)` construct itself
    link_end: int


@dataclass
class Reach:
    ok: bool = False
    status: Optional[int] = None
    final_url: Optional[str] = None
    redirected: bool = False
    soft_404: bool = False
    title: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Candidate:
    url: str
    title: str = ""
    why: str = ""
    verdict: Verdict = "PENDING"
    evidence_quote: Optional[str] = None
    reason: str = ""  # why this candidate passed or was rejected
    confidence: float = 0.0


@dataclass
class Result:
    claim: Claim
    verdict: Verdict = "PENDING"
    confidence: float = 0.0
    evidence_quote: Optional[str] = None
    reason: str = ""
    mismatch_type: str = "none"  # number | date | causality | topic | entity | none
    # The exact thing the cited page failed to establish, phrased as a search
    # query. This is what makes the repair search targeted rather than generic.
    missing_element: Optional[str] = None
    reach: Reach = field(default_factory=Reach)

    # Repair stage
    searching: bool = False  # a web-wide search is running right now
    searched: bool = False  # the search finished
    candidates_checked: int = 0  # how many alternatives were fetched and verified
    rejected: List[Candidate] = field(default_factory=list)
    replacement: Optional[Candidate] = None

    cached: bool = False
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = SEVERITY.get(self.verdict, -1)
        return d


@dataclass
class Document:
    text: str
    claims: List[Claim] = field(default_factory=list)
