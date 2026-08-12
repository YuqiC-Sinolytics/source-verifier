/* Injected into the hidden tab that renders the cited page.
 *
 * This function is stringified by chrome.scripting.executeScript, so it must
 * be self-contained — no imports, no closure over anything outside itself.
 *
 * This is the whole reason the extension beats the server-side version: by the
 * time this runs, the browser has executed the page's JavaScript and sent the
 * user's own cookies. Single-page apps, login-gated pages and soft paywalls all
 * read normally here and are invisible to a server-side fetcher.
 */
export function extractReadable() {
  const STRIP = 'script,style,noscript,nav,header,footer,aside,form,iframe,svg,' +
                '[role="navigation"],[role="banner"],[role="complementary"],' +
                '.ad,.ads,.advert,.cookie,.newsletter,.related,.comments';

  const pick = () =>
    document.querySelector('article') ||
    document.querySelector('main') ||
    document.querySelector('[role="main"]') ||
    document.body;

  const root = pick();
  if (!root) return { ok: false, reason: 'no body' };

  // Strip in the LIVE document rather than in a clone. innerText is
  // layout-aware — it inserts the line breaks that separate a heading from the
  // paragraph under it — but a detached clone has no layout, so innerText
  // silently degrades to textContent and every block runs together
  // ("...reportThis paragraph only exists..."), which reads as one garbled
  // sentence to the model. Mutating is safe here: this tab was opened by the
  // extension purely to be read and is closed immediately afterwards.
  root.querySelectorAll(STRIP).forEach(n => n.remove());

  const text = (root.innerText || root.textContent || '')
    .replace(/[ \t ]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  // Soft paywalls and consent walls look like a real page but carry no article
  const words = text.split(/\s+/).filter(Boolean).length;
  const wallish = /subscribe to continue|create a free account|sign in to read|accept cookies|you have reached your|register to continue/i
    .test(text.slice(0, 2500));

  // Only hard-fail on a page that is genuinely empty or is obviously a wall.
  // A crude word count must not pre-empt the model: plenty of legitimate
  // sources — press releases, data tables, abstracts — are very short, and
  // calling those UNREACHABLE would be a false negative on a real citation.
  const empty = words < 8;

  return {
    ok: !empty && !(wallish && words < 120),
    reason: empty ? 'empty' : (wallish && words < 120 ? 'wall' : ''),
    title: document.title || '',
    url: location.href,
    words,
    wallish,
    // cap so a 200k-word page cannot blow the context budget
    text: text.slice(0, 60000)
  };
}
