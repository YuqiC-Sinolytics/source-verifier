/* Service worker: context menu -> read the linked page -> verify -> repair.
 *
 * MV3 service workers are killed aggressively, so every step also writes state
 * to chrome.storage.session. The side panel reads that on load, which means a
 * worker restart mid-run leaves the panel showing the last known state instead
 * of going blank.
 */

import { extractReadable } from './lib/extract.js';
import { enforceEvidenceGate, checkQuoteOnPage } from './lib/verify.js';
import { verifyClaim, findCandidates, supportsRepair, testProvider } from './lib/providers.js';
import { demoPage } from './lib/demo-data.js';

const MENU_ID = 'sv-verify-link';
const TAB_TIMEOUT = 20000;

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: 'Verify this source',
    contexts: ['link']
  });
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});

async function getConfig() {
  const d = await chrome.storage.local.get(['provider', 'key', 'model', 'autoRepair']);
  return {
    provider: d.provider || 'demo',
    key: d.key || '',
    model: d.model || '',
    autoRepair: d.autoRepair !== false
  };
}

let runSeq = 0;

/** Push state to the panel and persist it for a worker restart. */
async function emit(state) {
  await chrome.storage.session.set({ svState: state });
  chrome.runtime.sendMessage({ type: 'sv:state', state }).catch(() => {});
}

/* ------------------------------------------------ read a page in a real tab */

function waitForComplete(tabId, timeout = TAB_TIMEOUT) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve('timeout'); // render whatever loaded rather than failing outright
    }, timeout);
    function listener(id, info) {
      if (id === tabId && info.status === 'complete') {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve('complete');
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId).catch(reject);
  });
}

/**
 * Open the URL in a hidden tab, let the page's own JavaScript run, then read
 * the rendered DOM. This is the extension's entire reason to exist: a
 * server-side fetcher sees the empty shell of a single-page app and none of the
 * user's logged-in content.
 */
async function readPage(url, openerTabId, provider) {
  // Demo mode opens nothing and requests nothing: the whole point of it is to
  // survive a dead venue network, which a real tab load would defeat.
  if (provider === 'demo') {
    await new Promise(r => setTimeout(r, 800));
    return demoPage(url);
  }

  let tab;
  try {
    tab = await chrome.tabs.create({ url, active: false, openerTabId });
  } catch {
    tab = await chrome.tabs.create({ url, active: false });
  }
  try {
    await waitForComplete(tab.id);
    await new Promise(r => setTimeout(r, 900)); // let late client-side render settle
    const [{ result } = {}] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractReadable
    });
    return result || { ok: false, reason: 'no result', url, text: '', words: 0 };
  } catch (e) {
    // PDFs and chrome:// pages reject script injection
    return { ok: false, reason: `cannot read page (${e.message})`, url, text: '', words: 0, title: '' };
  } finally {
    if (tab?.id) chrome.tabs.remove(tab.id).catch(() => {});
  }
}

/* --------------------------------------------------------------- main flow */

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== MENU_ID || !tab) return;
  // Must be called synchronously inside the gesture handler, before any await,
  // or Chrome rejects it as not user-initiated.
  chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});
  run(info, tab).catch(async e => {
    await emit({ phase: 'error', message: String(e.message || e) });
  });
});

async function run(info, tab) {
  const seq = ++runSeq;
  const cfg = await getConfig();

  if (cfg.provider !== 'demo' && !cfg.key) {
    return emit({ phase: 'nokey', provider: cfg.provider });
  }

  // 1. what is this link actually claiming?
  let claim = null;
  try {
    claim = await chrome.tabs.sendMessage(tab.id, {
      type: 'sv:describe-link', linkUrl: info.linkUrl
    });
  } catch { /* content script not present (e.g. chrome:// page) */ }

  if (!claim) {
    claim = {
      url: info.linkUrl,
      anchor: info.selectionText || info.linkUrl,
      sentence: info.selectionText || '(could not read the sentence around this link)',
      context: '', pageTitle: tab.title || '', pageUrl: tab.url || ''
    };
  }
  claim.url = info.linkUrl || claim.url;

  const state = {
    phase: 'reading', provider: cfg.provider, claim,
    startedAt: Date.now(), result: null, replacement: null,
    rejected: [], candidatesChecked: 0
  };
  await emit(state);

  // 2. render the cited page in a hidden tab and read it
  const page = await readPage(claim.url, tab.id, cfg.provider);
  state.page = { title: page.title, words: page.words, ok: page.ok, reason: page.reason };
  state.phase = 'verifying';
  await emit(state);
  if (seq !== runSeq) return;

  // 3. verify
  let verdict;
  if (!page.ok) {
    verdict = {
      verdict: 'UNREACHABLE', confidence: 0.9, evidence_quote: null,
      reason: page.reason === 'wall'
        ? 'The page rendered a paywall or consent wall instead of content.'
        : `The page produced no readable text (${page.reason || 'empty'}).`,
      mismatch_type: 'none', missing_element: null
    };
  } else {
    verdict = await verifyClaim(cfg, {
      sentence: claim.sentence, anchor: claim.anchor, context: claim.context, page
    });
    verdict = enforceEvidenceGate(verdict);
    verdict = checkQuoteOnPage(verdict, page.text);
  }

  state.result = verdict;
  state.phase = 'verified';
  await emit(state);
  if (seq !== runSeq) return;

  // 4. repair — only for non-green verdicts, and only if the provider can search
  const needsRepair = ['PARTIAL', 'UNSUPPORTED', 'UNREACHABLE'].includes(verdict.verdict);
  if (!cfg.autoRepair || !needsRepair || !supportsRepair(cfg.provider)) {
    state.phase = 'done';
    return emit(state);
  }

  state.phase = 'searching';
  await emit(state);

  let candidates = [];
  try {
    candidates = await findCandidates(cfg, {
      claim: claim.sentence, missing: verdict.missing_element, badUrl: claim.url
    });
  } catch (e) {
    state.searchError = String(e.message || e);
  }

  // Every candidate faces the same gate the original failed: rendered in a real
  // tab, judged by the same prompt. A recommendation that cannot clear your own
  // standard is worse than no recommendation.
  for (const cand of candidates.slice(0, 3)) {
    if (seq !== runSeq) return;
    state.phase = 'checking';
    state.checking = cand.url;
    await emit(state);

    const cpage = await readPage(cand.url, tab.id, cfg.provider);
    let cv;
    if (!cpage.ok) {
      cv = { verdict: 'UNREACHABLE', reason: 'Candidate page could not be read.' };
    } else {
      cv = await verifyClaim(cfg, {
        sentence: claim.sentence, anchor: claim.anchor, context: claim.context, page: cpage
      });
      cv = enforceEvidenceGate(cv);
      cv = checkQuoteOnPage(cv, cpage.text);
    }
    state.candidatesChecked++;

    const entry = { ...cand, ...cv };
    if (cv.verdict === 'SUPPORTED') { state.replacement = entry; break; }
    if (cv.verdict === 'PARTIAL' && !state.replacement) { state.replacement = entry; continue; }
    state.rejected.push(entry);
    await emit(state);
  }

  state.checking = null;
  state.phase = 'done';
  await emit(state);
}

// The panel asks for the current state when it opens or the worker restarted.
chrome.runtime.onMessage.addListener((msg, _s, reply) => {
  if (msg.type === 'sv:get-state') {
    chrome.storage.session.get('svState').then(d => reply(d.svState || null));
    return true;
  }

  // Key check. Runs in the service worker, which is where the real requests are
  // made — testing from the options page would use a different origin and could
  // pass while the real call still fails.
  if (msg.type === 'sv:test-key') {
    testProvider(msg.cfg).then(reply).catch(e => reply({ ok: false, detail: String(e.message || e) }));
    return true;
  }

  // Run the same flow without a right-click. Only extension pages can reach
  // this (no externally_connectable), so it is not a web-facing entry point.
  // Used by the test harness, and handy for wiring a keyboard shortcut later.
  if (msg.type === 'sv:run') {
    chrome.tabs.get(msg.tabId)
      .then(tab => run({ menuItemId: MENU_ID, linkUrl: msg.linkUrl }, tab))
      .then(() => chrome.storage.session.get('svState'))
      .then(d => reply(d.svState || null))
      .catch(e => reply({ phase: 'error', message: String(e.message || e) }));
    return true;
  }
});
