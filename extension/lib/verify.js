/* The verification contract, ported from the Python app.
 *
 * The rule that matters is unchanged and must stay unchanged: the DEFAULT
 * verdict is UNSUPPORTED, and SUPPORTED has to be earned with a verbatim quote.
 * Models lean hard toward agreeable "yes, that supports it" answers; without
 * inverting the burden of proof the false-positive rate makes the tool useless.
 */

export const SYSTEM = `You are a strict source verifier. You are given a claim, and \
the readable text of the page that the claim cites. Decide whether the page \
actually supports the claim.

RULES — follow them literally:

1. The DEFAULT verdict is UNSUPPORTED. SUPPORTED must be earned.
2. You may only answer SUPPORTED if you can quote VERBATIM text from the page \
that directly supports the claim. No quote means not supported. Ever.
3. Do NOT infer. Do NOT reason "this page is about the right topic, so it \
probably supports it." Topic relevance is PARTIAL at best, never SUPPORTED.
4. Check the specifics: numbers, dates, units, magnitudes, named entities, and \
the direction of any causal statement. A page saying "grew 12%" does not support \
a claim of "grew 20%". That is UNSUPPORTED with mismatch_type "number".
5. If the page contradicts the claim, that is UNSUPPORTED, not PARTIAL.
6. If the supplied page text is empty, truncated to nothing, or is obviously a \
paywall or consent wall rather than content, answer UNREACHABLE.
7. The quote you return must appear character-for-character in the page text you \
were given. It is used to build a link that highlights the passage in the \
browser, so an approximate or tidied-up quote breaks the feature.

Verdicts:
- SUPPORTED   : verbatim evidence directly supports the claim
- PARTIAL     : page is relevant and on-topic, but does not establish this \
specific assertion (or supports only part of it)
- UNSUPPORTED : page does not support, or actively contradicts, the claim
- UNREACHABLE : the page content could not be read

For PARTIAL and UNSUPPORTED, missing_element matters: name the exact thing that \
could not be found, phrased so it can be used as a search query — for example \
"the 89% figure" or "the 2010-2023 date range". A later search stage uses that \
string to look for a better source.`;

export const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['SUPPORTED', 'PARTIAL', 'UNSUPPORTED', 'UNREACHABLE'] },
    confidence: { type: 'number' },
    evidence_quote: {
      type: ['string', 'null'],
      description: 'Verbatim text from the page. Null unless SUPPORTED or PARTIAL.'
    },
    reason: { type: 'string', description: 'One short sentence for the end user.' },
    mismatch_type: {
      type: 'string',
      enum: ['number', 'date', 'causality', 'topic', 'entity', 'none']
    },
    missing_element: { type: ['string', 'null'] }
  },
  required: ['verdict', 'confidence', 'reason', 'mismatch_type']
};

export function buildPrompt({ sentence, anchor, context, page }) {
  const focus = anchor && anchor !== sentence
    ? `\nThe link is attached to this span of the sentence: "${anchor}"\n` +
      `Judge whether the page supports the assertion made by that span, read in ` +
      `the context of the full sentence. Other parts of the sentence may be ` +
      `backed by a different source and are not your concern.\n`
    : '';

  const ctx = context && context !== sentence
    ? `\nSURROUNDING PARAGRAPH (context only, do not verify this):\n"""${context}"""\n`
    : '';

  return `Verify this claim against the cited page.

CLAIM:
"""${sentence}"""
${focus}${ctx}
CITED PAGE: ${page.title || '(untitled)'}
URL: ${page.url}
WORDS EXTRACTED: ${page.words}

PAGE TEXT:
"""
${page.text}
"""

Remember: no verbatim quote means not SUPPORTED, and the quote must appear \
exactly as written in the page text above.`;
}

/** Code-level backstop. Prompts get talked around; this does not. */
export function enforceEvidenceGate(v) {
  if (v.verdict === 'SUPPORTED' && !(v.evidence_quote || '').trim()) {
    return {
      ...v,
      verdict: 'PARTIAL',
      confidence: Math.min(v.confidence ?? 0.5, 0.5),
      reason: `${(v.reason || '').trim()} (Downgraded: no verbatim evidence.)`.trim()
    };
  }
  return v;
}

/** The quote must really be on the page, or the highlight link is a lie. */
export function checkQuoteOnPage(v, pageText) {
  const q = (v.evidence_quote || '').trim();
  if (!q) return v;
  const norm = s => s.replace(/[\s ]+/g, ' ').toLowerCase();
  if (norm(pageText).includes(norm(q))) return { ...v, quote_verified: true };
  return {
    ...v,
    quote_verified: false,
    reason: `${(v.reason || '').trim()} (Quote could not be located verbatim on the page.)`.trim()
  };
}
