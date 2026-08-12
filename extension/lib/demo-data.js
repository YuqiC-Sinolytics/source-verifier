/* Offline fixtures — the same ones the web app ships, so the extension is
 * installable and demoable before any API key exists. Matched by URL substring;
 * anything unrecognised falls back to a hash so a given link always produces
 * the same verdict (a demo whose results jump around is worse than no demo).
 */

const VERDICTS = {
  'ourworldindata.org/energy': {
    verdict: 'PARTIAL', confidence: 0.55,
    evidence_quote: 'Solar and wind are now the cheapest sources of new electricity in most countries.',
    reason: 'The page covers energy cost trends but never states this specific 89% decline.',
    mismatch_type: 'number',
    missing_element: 'the 89% fall in the levelised cost of solar between 2010 and 2023'
  },
  'Solar_cell_efficiency': {
    verdict: 'UNSUPPORTED', confidence: 0.93, evidence_quote: null,
    reason: 'The page puts commercial silicon cell efficiency at roughly 24-27%, which contradicts the 45% in the claim.',
    mismatch_type: 'number',
    missing_element: 'commercial silicon panels exceeding 45% efficiency'
  },
  'wiki/Solar_power': {
    verdict: 'SUPPORTED', confidence: 0.91,
    evidence_quote: 'In 2023, solar power generated around 5.5% of global electricity.',
    reason: 'The source states this figure directly.', mismatch_type: 'none'
  },
  'irena.org': {
    verdict: 'SUPPORTED', confidence: 0.9,
    evidence_quote: 'The global weighted average levelised cost of electricity of utility-scale solar PV declined by 89% between 2010 and 2023.',
    reason: "IRENA's cost report states the 89% decline verbatim.", mismatch_type: 'none'
  },
  'cleantechnica.com': {
    verdict: 'UNSUPPORTED', confidence: 0.8, evidence_quote: null,
    reason: 'Covers 2024 cost trends but gives no 2010-2023 decline figure.', mismatch_type: 'number'
  },
  'nrel.gov': {
    verdict: 'UNSUPPORTED', confidence: 0.92, evidence_quote: null,
    reason: "NREL's chart tops out at 27.8% for record silicon lab cells — nothing near 45% in commercial deployment.",
    mismatch_type: 'number'
  },
  'nature.com/nrendo': {
    verdict: 'PARTIAL', confidence: 0.4, evidence_quote: null,
    reason: "This is the journal's landing page, not an article. It contains no statement about GLP-1 mechanism.",
    mismatch_type: 'topic',
    missing_element: 'a statement that GLP-1 agonists mimic a gut hormone that regulates appetite'
  },
  'regulatory-framework-ai': {
    verdict: 'UNSUPPORTED', confidence: 0.91, evidence_quote: null,
    reason: 'The Commission page states fines of up to EUR 35 million or 7% of global annual turnover — not 6%.',
    mismatch_type: 'number',
    missing_element: 'a penalty ceiling of 6% of global annual turnover'
  }
};

const CANDIDATES = {
  'ourworldindata.org/energy': [
    { url: 'https://cleantechnica.com/2024/solar-costs-plunge/', title: 'Solar Costs Plunge Again - CleanTechnica', why: 'Recent coverage of solar cost declines.' },
    { url: 'https://www.irena.org/Publications/2024/Sep/Renewable-Power-Generation-Costs-in-2023', title: 'Renewable Power Generation Costs in 2023 - IRENA', why: 'IRENA is the primary source for levelised-cost time series.' }
  ],
  'Solar_cell_efficiency': [
    { url: 'https://www.nrel.gov/pv/cell-efficiency.html', title: 'Best Research-Cell Efficiency Chart - NREL', why: 'NREL maintains the reference chart for record cell efficiencies.' }
  ]
};

function pick(table, url) {
  for (const frag of Object.keys(table)) if (url.includes(frag)) return table[frag];
  return null;
}

export function demoVerdict(url) {
  const hit = pick(VERDICTS, url || '');
  if (hit) return { ...hit };
  let h = 0;
  for (const ch of String(url)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return [
    { verdict: 'PARTIAL', confidence: 0.5, evidence_quote: null,
      reason: '[DEMO] On-topic, but no verbatim evidence for this assertion.',
      mismatch_type: 'topic', missing_element: 'the specific assertion in this sentence' },
    { verdict: 'SUPPORTED', confidence: 0.8,
      evidence_quote: '[DEMO] A verbatim line from the source.',
      reason: '[DEMO] Direct supporting evidence found.', mismatch_type: 'none' },
    { verdict: 'UNSUPPORTED', confidence: 0.85, evidence_quote: null,
      reason: '[DEMO] Page content is unrelated to the claim.',
      mismatch_type: 'topic', missing_element: 'any statement of this claim' }
  ][h % 3];
}

export function demoCandidates(url) {
  return (pick(CANDIDATES, url || '') || []).map(c => ({ ...c }));
}

/* Demo mode must not touch the network at all — otherwise it is not the
 * fallback it claims to be. So instead of rendering the page in a tab we
 * synthesise one containing the fixture's evidence quote, which keeps the
 * verbatim-quote check meaningful rather than bypassed. */
export function demoPage(url) {
  const v = demoVerdict(url);
  const quote = v.evidence_quote || '';
  let host = url;
  try { host = new URL(url).hostname; } catch {}
  const filler =
    'This page is part of the offline demo fixture set. It stands in for the ' +
    'real article so the extension can be installed and demonstrated with no ' +
    'API key and no network access whatsoever. ';
  return {
    ok: true, reason: '', url,
    title: `${host} (demo fixture)`,
    text: filler + quote + ' ' + filler,
    words: 60 + quote.split(/\s+/).length,
    wallish: false
  };
}
