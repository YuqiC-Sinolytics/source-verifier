"""MOCK mode — the second layer of demo insurance.

With MOCK=1 the entire pipeline runs offline: no HTTP, no API calls. If the
venue wifi dies, the API quota runs out, or a last-minute edit breaks something
five minutes before you present, you still have a working demo.

Everything is matched by URL substring. Candidates are keyed by the *failing*
URL rather than by claim text, because one sentence can carry two links and
claim text alone cannot tell them apart.

Each example is scripted to show a different mix:
  01 solar     404 -> fixed, amber -> fixed via IRENA, contradicted number that
                stays red after two candidates are checked and rejected
  02 obesity   a journal *homepage* cited instead of an article (amber -> fixed),
                a fabricated DOI that no search can rescue
  03 EU AI Act a wrong penalty figure that stays red because no source states
                6%, plus a dead timeline URL that is repaired cleanly
"""

import hashlib
from typing import Dict, List

from .models import Candidate, Reach

# ---------------------------------------------------------------- liveness ---
_REACH: Dict[str, dict] = {
    # 01 solar
    "renewables-2024-nonexistent": dict(ok=False, status=404),
    "this-article-does-not-exist": dict(ok=False, status=404),
    "global-energy-review.org": dict(ok=False, error="getaddrinfo failed"),
    "ourworldindata.org/energy": dict(ok=True, status=200, title="Energy - Our World in Data"),
    "Solar_cell_efficiency": dict(ok=True, status=200, title="Solar cell efficiency - Wikipedia"),
    "wiki/Solar_power": dict(ok=True, status=200, title="Solar power - Wikipedia"),
    # 02 obesity drugs
    "cdc.gov/obesity/data/adult.html": dict(ok=False, status=404),
    "PIIS0140-6736-24-01234": dict(ok=False, status=404),
    "nejm.org/doi/full/10.1056/NEJMoa2032183": dict(
        ok=True, status=200, title="Once-Weekly Semaglutide in Adults with Overweight or Obesity"
    ),
    "nature.com/nrendo": dict(ok=True, status=200, title="Nature Reviews Endocrinology"),
    "novo-nordisk-market-value": dict(ok=True, status=200, title="Novo Nordisk - Reuters"),
    # 03 EU AI Act
    "ai-governance-institute.eu": dict(ok=False, error="getaddrinfo failed"),
    "gpai-timeline-2025": dict(ok=False, status=404),
    "1689/oj": dict(ok=True, status=200, title="Regulation (EU) 2024/1689 - EUR-Lex"),
    "regulatory-framework-ai": dict(
        ok=True, status=200, title="AI Act | Shaping Europe's digital future"
    ),
    "european-approach-artificial-intelligence": dict(
        ok=True, status=200, title="A European approach to artificial intelligence"
    ),
    "high-level-summary": dict(
        ok=True, status=200, title="High-level summary of the AI Act | EU Artificial Intelligence Act"
    ),
}

# ---------------------------------------------------------------- verdicts ---
# NOTE: more specific keys must come before the prefixes they extend.
_VERDICTS: Dict[str, dict] = {
    # ---- 01 solar: originally cited pages ----
    "ourworldindata.org/energy": dict(
        verdict="PARTIAL",
        confidence=0.55,
        evidence_quote="Solar and wind are now the cheapest sources of new electricity "
        "in most countries.",
        reason="The page covers energy cost trends but never states this specific 89% decline.",
        mismatch_type="number",
        missing_element="the 89% fall in the levelised cost of solar between 2010 and 2023",
    ),
    "Solar_cell_efficiency": dict(
        verdict="UNSUPPORTED",
        confidence=0.93,
        evidence_quote=None,
        reason="The page puts commercial silicon cell efficiency at roughly 24-27%, "
        "which contradicts the 45% in the claim.",
        mismatch_type="number",
        missing_element="commercial silicon panels exceeding 45% efficiency",
    ),
    "wiki/Solar_power": dict(
        verdict="SUPPORTED",
        confidence=0.91,
        evidence_quote="In 2023, solar power generated around 5.5% of global electricity.",
        reason="The source states this figure directly.",
        mismatch_type="none",
    ),
    # ---- 01 solar: repair candidates ----
    "iea.org/reports/renewables-2024": dict(
        verdict="SUPPORTED",
        confidence=0.88,
        evidence_quote="Global installed solar PV capacity surpassed 2 200 GW at the end of 2024.",
        reason="The IEA report states the capacity figure directly.",
        mismatch_type="none",
    ),
    "ember-energy.org": dict(
        verdict="SUPPORTED",
        confidence=0.86,
        evidence_quote="China accounted for around 60% of all new solar capacity added "
        "worldwide in 2024.",
        reason="The source states the share explicitly.",
        mismatch_type="none",
    ),
    "cleantechnica.com": dict(
        verdict="UNSUPPORTED",
        confidence=0.8,
        evidence_quote=None,
        reason="Covers 2024 cost trends but gives no 2010-2023 decline figure.",
        mismatch_type="number",
    ),
    "irena.org/Publications": dict(
        verdict="SUPPORTED",
        confidence=0.9,
        evidence_quote="The global weighted average levelised cost of electricity of "
        "utility-scale solar PV declined by 89% between 2010 and 2023.",
        reason="IRENA's cost report states the 89% decline verbatim.",
        mismatch_type="none",
    ),
    "nrel.gov/pv/cell-efficiency": dict(
        verdict="UNSUPPORTED",
        confidence=0.92,
        evidence_quote=None,
        reason="NREL's chart tops out at 27.8% for record silicon lab cells — nothing "
        "near 45% in commercial deployment.",
        mismatch_type="number",
    ),
    "Shockley": dict(
        verdict="UNSUPPORTED",
        confidence=0.94,
        evidence_quote=None,
        reason="The theoretical single-junction limit is about 33%, which rules out the "
        "claim outright.",
        mismatch_type="number",
    ),
    # ---- 02 obesity drugs: originally cited pages ----
    "NEJMoa2032183": dict(
        verdict="SUPPORTED",
        confidence=0.94,
        evidence_quote="The mean change in body weight from baseline to week 68 was "
        "-14.9% in the semaglutide group.",
        reason="The STEP 1 primary endpoint matches the claim exactly.",
        mismatch_type="none",
    ),
    "nature.com/nrendo": dict(
        verdict="PARTIAL",
        confidence=0.4,
        evidence_quote=None,
        reason="This is the journal's landing page, not an article. It lists issues and "
        "editorial information, and contains no statement about GLP-1 mechanism.",
        mismatch_type="topic",
        missing_element="a statement that GLP-1 agonists mimic a gut hormone that "
        "regulates appetite and slows gastric emptying",
    ),
    "novo-nordisk-market-value": dict(
        verdict="SUPPORTED",
        confidence=0.87,
        evidence_quote="Novo Nordisk's market capitalisation overtook the size of the "
        "Danish economy in 2023.",
        reason="The article states the comparison directly.",
        mismatch_type="none",
    ),
    # ---- 02 obesity drugs: repair candidates ----
    "adult-obesity-facts": dict(
        verdict="SUPPORTED",
        confidence=0.93,
        evidence_quote="The prevalence of obesity among U.S. adults was 40.3%.",
        reason="CDC's current obesity page states the prevalence figure.",
        mismatch_type="none",
    ),
    "NEJMoa2206038": dict(  # SURMOUNT-1 — real trial, but not head-to-head
        verdict="UNSUPPORTED",
        confidence=0.9,
        evidence_quote=None,
        reason="SURMOUNT-1 was placebo-controlled, not a head-to-head against "
        "semaglutide, and reports 20.9% rather than 26%.",
        mismatch_type="number",
    ),
    "obesity-glp1-meta-analysis": dict(
        verdict="UNSUPPORTED",
        confidence=0.85,
        evidence_quote=None,
        reason="An indirect comparison only; it reports no 26% head-to-head result.",
        mismatch_type="number",
    ),
    "s41574-021-00498": dict(
        verdict="SUPPORTED",
        confidence=0.89,
        evidence_quote="GLP-1 is an incretin hormone released from the gut that "
        "suppresses appetite and delays gastric emptying.",
        reason="The review states the mechanism explicitly.",
        mismatch_type="none",
    ),
    # ---- 03 EU AI Act: originally cited pages ----
    "1689/oj": dict(
        verdict="SUPPORTED",
        confidence=0.95,
        evidence_quote="This Regulation shall enter into force on the twentieth day "
        "following that of its publication in the Official Journal of the European "
        "Union. It shall apply from 2 August 2026.",
        reason="The Official Journal text confirms entry into force on 1 August 2024.",
        mismatch_type="none",
    ),
    "regulatory-framework-ai": dict(
        verdict="UNSUPPORTED",
        confidence=0.91,
        evidence_quote=None,
        reason="The Commission page states fines of up to EUR 35 million or 7% of "
        "global annual turnover — not 6%.",
        mismatch_type="number",
        missing_element="a penalty ceiling of 6% of global annual turnover for "
        "prohibited AI practices",
    ),
    "european-approach-artificial-intelligence": dict(
        verdict="PARTIAL",
        confidence=0.45,
        evidence_quote="The EU's approach to AI centres on excellence and trust.",
        reason="A high-level policy overview. It never states that the Act reaches "
        "providers established outside the EU.",
        mismatch_type="topic",
        missing_element="the extraterritorial scope of the AI Act, covering non-EU "
        "providers whose system output is used in the Union",
    ),
    "high-level-summary": dict(
        verdict="SUPPORTED",
        confidence=0.88,
        evidence_quote="High-risk AI systems are subject to a conformity assessment "
        "before they can be placed on the market.",
        reason="The summary states the conformity assessment requirement directly.",
        mismatch_type="none",
    ),
    # ---- 03 EU AI Act: repair candidates ----
    "implementation-timeline": dict(
        verdict="SUPPORTED",
        confidence=0.9,
        evidence_quote="2 August 2025: obligations for providers of general-purpose AI "
        "models start to apply.",
        reason="The implementation timeline states the GPAI date directly.",
        mismatch_type="none",
    ),
    "article/99": dict(
        verdict="UNSUPPORTED",
        confidence=0.93,
        evidence_quote=None,
        reason="Article 99 sets the ceiling at EUR 35 million or 7% of worldwide annual "
        "turnover, which contradicts the 6% in the claim.",
        mismatch_type="number",
    ),
    "penalties-explained": dict(
        verdict="UNSUPPORTED",
        confidence=0.88,
        evidence_quote=None,
        reason="Repeats the 7% ceiling. No source states 6%.",
        mismatch_type="number",
    ),
    "article/2": dict(
        verdict="SUPPORTED",
        confidence=0.91,
        evidence_quote="This Regulation applies to providers placing on the market or "
        "putting into service AI systems in the Union, irrespective of whether those "
        "providers are established in the Union or in a third country.",
        reason="Article 2 states the extraterritorial scope verbatim.",
        mismatch_type="none",
    ),
}

# ------------------------------------------------------------- candidates ---
# Keyed by the FAILING url, not by claim text: one sentence can carry two links
# and claim text alone cannot distinguish them.
_CANDIDATES: Dict[str, List[dict]] = {
    # 01 solar
    "renewables-2024-nonexistent": [
        dict(url="https://www.iea.org/reports/renewables-2024",
             title="Renewables 2024 - IEA",
             why="The IEA annual report is the original source for this capacity figure."),
    ],
    "this-article-does-not-exist": [
        dict(url="https://ember-energy.org/latest-insights/global-solar-2024/",
             title="Global Solar Review 2024 - Ember",
             why="Ember breaks new capacity additions down by country."),
    ],
    "ourworldindata.org/energy": [  # amber -> green, after rejecting a blog
        dict(url="https://cleantechnica.com/2024/solar-costs-plunge/",
             title="Solar Costs Plunge Again - CleanTechnica",
             why="Recent coverage of solar cost declines."),
        dict(url="https://www.irena.org/Publications/2024/Sep/Renewable-Power-Generation-Costs-in-2023",
             title="Renewable Power Generation Costs in 2023 - IRENA",
             why="IRENA is the primary source for levelised-cost time series."),
    ],
    "Solar_cell_efficiency": [  # stays red: both candidates checked and rejected
        dict(url="https://www.nrel.gov/pv/cell-efficiency.html",
             title="Best Research-Cell Efficiency Chart - NREL",
             why="NREL maintains the reference chart for record cell efficiencies."),
        dict(url="https://en.wikipedia.org/wiki/Shockley%E2%80%93Queisser_limit",
             title="Shockley-Queisser limit - Wikipedia",
             why="Defines the theoretical ceiling for single-junction cells."),
    ],
    "global-energy-review.org": [],
    # 02 obesity drugs
    "cdc.gov/obesity/data/adult.html": [  # classic site-redesign fix
        dict(url="https://www.cdc.gov/obesity/php/data-research/adult-obesity-facts.html",
             title="Adult Obesity Facts - CDC",
             why="CDC moved its obesity statistics to this path in the 2024 redesign."),
    ],
    "PIIS0140-6736-24-01234": [  # fabricated DOI: nothing supports 26% head-to-head
        dict(url="https://www.nejm.org/doi/full/10.1056/NEJMoa2206038",
             title="Tirzepatide Once Weekly for the Treatment of Obesity (SURMOUNT-1)",
             why="The pivotal tirzepatide weight-loss trial."),
        dict(url="https://www.thelancet.com/journals/lancet/article/obesity-glp1-meta-analysis/fulltext",
             title="Comparative efficacy of GLP-1 agonists - The Lancet",
             why="An indirect comparison across trials."),
    ],
    "nature.com/nrendo": [  # journal homepage -> actual review article
        dict(url="https://www.nature.com/articles/s41574-021-00498-x",
             title="GLP-1 physiology in obesity - Nature Reviews Endocrinology",
             why="A review article in the same journal that covers the mechanism."),
    ],
    # 03 EU AI Act
    "regulatory-framework-ai": [  # stays red: no source states 6%
        dict(url="https://artificialintelligenceact.eu/article/99/",
             title="Article 99: Penalties - EU Artificial Intelligence Act",
             why="The penalties article states the statutory ceilings."),
        dict(url="https://artificialintelligenceact.eu/penalties-explained/",
             title="Penalties under the AI Act",
             why="A summary of the fine tiers."),
    ],
    "gpai-timeline-2025": [
        dict(url="https://artificialintelligenceact.eu/implementation-timeline/",
             title="Implementation Timeline - EU Artificial Intelligence Act",
             why="The canonical timeline of application dates."),
    ],
    "european-approach-artificial-intelligence": [
        dict(url="https://artificialintelligenceact.eu/article/2/",
             title="Article 2: Scope - EU Artificial Intelligence Act",
             why="Article 2 defines who the Regulation applies to."),
    ],
    "ai-governance-institute.eu": [],
}


def _pick(table: dict, url: str):
    for frag, val in table.items():
        if frag in url:
            return val
    return None


def mock_reach(urls: List[str]) -> Dict[str, Reach]:
    out = {}
    for u in urls:
        kw = _pick(_REACH, u) or dict(ok=True, status=200, title="Example page")
        out[u] = Reach(final_url=u, **kw)
    return out


def mock_verify(url: str, claim: str) -> dict:
    hit = _pick(_VERDICTS, url)
    if hit:
        return dict(hit)
    # Fallback: hash to a stable verdict so demos stay reproducible.
    h = int(hashlib.sha1(f"{url}{claim}".encode()).hexdigest(), 16) % 3
    return [
        dict(verdict="PARTIAL", confidence=0.5, evidence_quote=None,
             reason="[MOCK] On-topic, but no verbatim evidence for this assertion.",
             mismatch_type="topic",
             missing_element="the specific assertion made in this sentence"),
        dict(verdict="SUPPORTED", confidence=0.8,
             evidence_quote="[MOCK] A verbatim line from the source.",
             reason="[MOCK] Direct supporting evidence found.", mismatch_type="none"),
        dict(verdict="UNSUPPORTED", confidence=0.85, evidence_quote=None,
             reason="[MOCK] Page content is unrelated to the claim.",
             mismatch_type="topic", missing_element="any statement of this claim"),
    ][h]


def mock_candidates(claim: str, bad_url: str) -> List[Candidate]:
    hit = _pick(_CANDIDATES, bad_url)
    return [Candidate(**i) for i in hit] if hit else []
