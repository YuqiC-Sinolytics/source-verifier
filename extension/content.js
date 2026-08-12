/* Runs on every page. Its only job is to work out WHAT CLAIM a link is making.
 *
 * chrome.contextMenus gives us info.linkUrl but not the element, and matching
 * by href is unreliable — the same URL is often cited several times on a page.
 * So we remember the element the user actually right-clicked, which the
 * contextmenu event hands us directly.
 */

let lastTarget = null;

document.addEventListener(
  'contextmenu',
  e => { lastTarget = e.target; },
  true // capture: still fires if the page stops propagation
);

const SENT_END = /[.!?。！？]/;

/** Walk up to the nearest block-level container that holds real prose. */
function blockOf(el) {
  const BLOCK = new Set(['P', 'LI', 'TD', 'TH', 'BLOCKQUOTE', 'FIGCAPTION',
                         'DD', 'DT', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']);
  let n = el;
  while (n && n !== document.body) {
    if (BLOCK.has(n.tagName)) return n;
    n = n.parentElement;
  }
  // no semantic block: fall back to the nearest ancestor with enough text
  n = el;
  while (n && n !== document.body) {
    const t = (n.innerText || '').trim();
    if (t.length > 60) return n;
    n = n.parentElement;
  }
  return el;
}

/** The sentence inside `text` that contains `needle`. */
function sentenceAround(text, needle) {
  const clean = text.replace(/\s+/g, ' ').trim();
  const target = needle.replace(/\s+/g, ' ').trim();
  const at = target ? clean.indexOf(target) : -1;
  if (at === -1) return clean.slice(0, 600);

  let start = 0;
  for (let i = at - 1; i >= 0; i--) {
    if (SENT_END.test(clean[i])) {
      // don't break on "U.S." or "No. 5" — require a following space + capital
      const next = clean[i + 1], after = clean[i + 2];
      if (next === ' ' && after && after === after.toUpperCase()) { start = i + 1; break; }
      if (/[。！？]/.test(clean[i])) { start = i + 1; break; }
    }
  }
  let end = clean.length;
  for (let i = at + target.length; i < clean.length; i++) {
    if (SENT_END.test(clean[i])) { end = i + 1; break; }
  }
  return clean.slice(start, end).trim();
}

function describeLink(el) {
  const a = el && el.closest ? el.closest('a[href]') : null;
  if (!a) return null;
  const anchor = (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim();
  const block = blockOf(a);
  const sentence = sentenceAround(block.innerText || block.textContent || '', anchor);
  return {
    url: a.href,
    anchor: anchor || a.href,
    sentence,
    // the surrounding paragraph, so the model can read the claim in context
    context: (block.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 1200),
    pageTitle: document.title,
    pageUrl: location.href
  };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.type !== 'sv:describe-link') return;
  let out = describeLink(lastTarget);
  if (!out && msg.linkUrl) {
    // right-click landed on something odd — fall back to matching by href
    const a = [...document.querySelectorAll('a[href]')].find(x => x.href === msg.linkUrl);
    out = a ? describeLink(a) : null;
  }
  reply(out || null);
  return true;
});
