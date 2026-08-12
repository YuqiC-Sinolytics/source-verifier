const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/* Text Fragments: Chrome scrolls to the quoted passage and highlights it on
 * arrival, so clicking through lands on the sentence rather than on a
 * 20,000-word page. Long quotes go as textStart,textEnd — matching a range
 * survives the whitespace differences that break exact-string matches. */
function fragUrl(url, quote) {
  const clean = (quote || '').replace(/\s+/g, ' ').trim();
  if (!url || !clean) return url;
  const enc = s => encodeURIComponent(s).replace(/-/g, '%2D');
  const w = clean.split(' ');
  const frag = w.length > 12
    ? `${enc(w.slice(0, 5).join(' '))},${enc(w.slice(-5).join(' '))}`
    : enc(clean);
  return url.includes('#') ? `${url}:~:text=${frag}` : `${url}#:~:text=${frag}`;
}

function link(url, quote) {
  return `<a href="${esc(fragUrl(url, quote))}" target="_blank" rel="noopener">${esc(url)}</a>`;
}

function steps(state) {
  const order = ['reading', 'verifying', 'searching', 'checking', 'done'];
  const at = order.indexOf(state.phase === 'verified' ? 'verifying' : state.phase);
  const row = (i, label) => {
    const cls = at > i || state.phase === 'done' ? 'tick' : (at === i ? 'spin' : 'idle');
    return `<div class="step"><span class="${cls}"></span>${esc(label)}</div>`;
  };
  let h = row(0, 'Rendering the cited page in a background tab');
  h += row(1, 'Checking whether it supports the claim');
  if (state.phase === 'searching' || state.phase === 'checking' ||
      (state.phase === 'done' && state.candidatesChecked)) {
    h += row(2, 'Searching for a source that does');
    if (state.checking) h += row(3, `Checking ${new URL(state.checking).hostname}`);
  }
  return h;
}

function render(state) {
  const out = $('#out');
  $('#foot').textContent = state && state.provider
    ? `Provider: ${state.provider}${state.provider === 'demo' ? ' (offline fixtures, no API calls)' : ''}`
    : '';

  if (!state) {
    out.innerHTML = `<p class="empty">Right-click a cited link on any page and choose
      <b>Verify this source</b>.<br><br>The extension opens that link in a hidden tab, lets the
      page's own JavaScript run, and reads what you would see — so pages behind logins and
      client-side rendering work here even though a server-side fetcher cannot read them.</p>`;
    return;
  }

  if (state.phase === 'nokey') {
    out.innerHTML = `<p class="empty"><b>No API key set.</b><br><br>Open the extension options
      and add a key for ${esc(state.provider)}, or switch the provider to
      <b>Demo</b> to try the flow with offline fixtures.</p>
      <p><button id="opts">Open options</button></p>`;
    $('#opts').onclick = () => chrome.runtime.openOptionsPage();
    return;
  }

  if (state.phase === 'error') {
    out.innerHTML = `<div class="nofix"><b>Something went wrong.</b><br>${esc(state.message)}</div>`;
    return;
  }

  const c = state.claim || {};
  const r = state.result;
  let h = '';

  if (!r) {
    h += `<p class="quoted">“${esc(c.sentence || '')}”</p>`;
    h += `<div class="label">Cited link</div><div class="url">${esc(c.url || '')}</div>`;
    h += `<div style="margin-top:18px">${steps(state)}</div>`;
    out.innerHTML = h;
    return;
  }

  const dead = ['UNSUPPORTED', 'UNREACHABLE'].includes(r.verdict);
  h += `<span class="badge b-${esc(r.verdict)}">${esc(r.verdict)}</span>`;

  // Same order as the web app: source first, conclusion last.
  h += `<div class="label">Cited link</div>`;
  h += `<div class="url ${dead ? 'dead' : ''}">${link(c.url, r.evidence_quote)}</div>`;
  if (state.page && state.page.words)
    h += `<div class="url">${state.page.words.toLocaleString()} words read from the rendered page</div>`;
  if (r.evidence_quote && r.quote_verified !== false)
    h += `<div class="jump">↗ opens at the highlighted passage</div>`;

  h += `<div class="label">Text found in the source</div>`;
  h += r.evidence_quote
    ? `<div class="quote ${r.verdict === 'PARTIAL' ? 'amber' : ''}">${esc(r.evidence_quote)}</div>`
    : `<div class="none">Nothing on the page supports this claim.</div>`;

  h += `<div class="label">Sentence on the page you were reading</div>`;
  h += `<p class="quoted">“${esc(c.sentence)}”</p>`;

  h += `<div class="label">Analysis</div><p class="reason">${esc(r.reason)}</p>`;
  if (r.mismatch_type && r.mismatch_type !== 'none')
    h += `<div class="url">Mismatch type: ${esc(r.mismatch_type)}</div>`;

  if (state.phase === 'searching' || state.phase === 'checking') {
    h += `<div class="work">${state.checking
      ? `Checking ${esc(new URL(state.checking).hostname)}…`
      : `Searching the web for a source that states ${esc(r.missing_element || 'this claim')}…`}</div>`;
    h += `<div style="margin-top:12px">${steps(state)}</div>`;
  } else if (state.replacement) {
    const rep = state.replacement;
    h += `<div class="fix"><div class="label">Better source found</div>${link(rep.url, rep.evidence_quote)}`;
    if (rep.evidence_quote) {
      h += `<div class="jump">↗ opens at the highlighted passage</div>`;
      h += `<div class="label" style="margin-top:10px">Its evidence</div>`;
      h += `<div class="quote">${esc(rep.evidence_quote)}</div>`;
    }
    h += `</div>`;
    if (state.rejected?.length)
      h += `<div class="tried">Rejected ${state.rejected.length} other candidate${state.rejected.length > 1 ? 's' : ''} that did not contain it.</div>`;
  } else if (state.phase === 'done' && state.candidatesChecked > 0) {
    h += `<div class="nofix">No source found that supports this. Rendered and checked
      ${state.candidatesChecked} candidate${state.candidatesChecked === 1 ? '' : 's'} — none
      contained it. This sentence may be fabricated.</div>`;
    if (state.rejected?.length)
      h += `<div class="tried">Checked and rejected:<br>` +
           state.rejected.map(x => `<code>${esc(x.url)}</code> — ${esc(x.reason || x.why || 'no match')}`).join('<br>') +
           `</div>`;
  } else if (state.phase === 'done' && dead) {
    h += `<div class="tried">No replacement search was run (either disabled in options,
      or this provider has no search capability).</div>`;
  }

  out.innerHTML = h;
}

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'sv:state') render(msg.state);
});
chrome.runtime.sendMessage({ type: 'sv:get-state' }).then(render).catch(() => render(null));
