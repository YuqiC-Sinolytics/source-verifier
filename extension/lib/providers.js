/* Provider layer.
 *
 * Because the extension reads the page itself, the model only ever has to
 * judge text it is handed — no vendor-specific fetch tooling is involved. That
 * is what makes swapping providers realistic rather than aspirational.
 *
 * Claude is the tested path. OpenAI is implemented and wired but has had less
 * mileage. `demo` needs no key at all and replays the same fixtures the web app
 * uses, so the extension is installable and demoable before any key exists.
 */

import { SYSTEM, VERDICT_SCHEMA, buildPrompt } from './verify.js';
import { demoVerdict, demoCandidates } from './demo-data.js';

export const PROVIDERS = {
  claude: { label: 'Claude (Anthropic)', needsKey: true, defaultModel: 'claude-sonnet-5' },
  openai: { label: 'OpenAI', needsKey: true, defaultModel: 'gpt-4.1' },
  demo:   { label: 'Demo — offline, no key', needsKey: false, defaultModel: '' }
};

const TOOL_NAME = 'submit_verdict';

/* ------------------------------------------------------------------ Claude */

async function claudeVerify({ key, model, prompt }) {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
      // Without this the browser request is refused by CORS. The key lives in
      // chrome.storage.local on this machine and is the user's own — quite
      // different from shipping a key inside a public web page.
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify({
      model: model || PROVIDERS.claude.defaultModel,
      max_tokens: 1500,
      system: SYSTEM,
      messages: [{ role: 'user', content: prompt }],
      tools: [{ name: TOOL_NAME, description: 'Report the verification result.', input_schema: VERDICT_SCHEMA }],
      tool_choice: { type: 'tool', name: TOOL_NAME }
    })
  });
  if (!res.ok) throw new Error(`Claude ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const data = await res.json();
  const block = (data.content || []).find(b => b.type === 'tool_use' && b.name === TOOL_NAME);
  if (!block) throw new Error('Claude returned no structured verdict');
  return block.input;
}

/** Repair search. Anthropic's server-side web_search; skipped for providers without one. */
async function claudeSearch({ key, model, claim, missing, badUrl }) {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify({
      model: model || PROVIDERS.claude.defaultModel,
      max_tokens: 1500,
      system:
        'You find primary sources that can substantiate a specific factual claim. ' +
        'Prefer the original source (statistics agency, the report or paper itself, ' +
        'the filing) over news coverage or aggregators. Target the element that was ' +
        'missing. Do not judge whether the pages truly support the claim — a strict ' +
        'verifier fetches and checks each one. Then call propose_candidates once.',
      messages: [{
        role: 'user',
        content: `Find sources that can substantiate this claim:\n\n"""${claim}"""\n\n` +
                 `The cited page does not state ${missing || 'this claim'}. Find one that does.\n` +
                 `The currently cited URL is ${badUrl} — do not propose it again.`
      }],
      tools: [
        { type: 'web_search_20250305', name: 'web_search', max_uses: 3 },
        {
          name: 'propose_candidates',
          description: 'Report candidate source URLs.',
          input_schema: {
            type: 'object',
            properties: {
              candidates: {
                type: 'array', maxItems: 4,
                items: {
                  type: 'object',
                  properties: { url: { type: 'string' }, title: { type: 'string' }, why: { type: 'string' } },
                  required: ['url', 'title']
                }
              }
            },
            required: ['candidates']
          }
        }
      ]
    })
  });
  if (!res.ok) throw new Error(`Claude search ${res.status}`);
  const data = await res.json();
  const block = (data.content || []).find(b => b.type === 'tool_use' && b.name === 'propose_candidates');
  return block ? (block.input.candidates || []) : [];
}

/* ------------------------------------------------------------------ OpenAI */

async function openaiVerify({ key, model, prompt }) {
  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${key}` },
    body: JSON.stringify({
      model: model || PROVIDERS.openai.defaultModel,
      messages: [{ role: 'system', content: SYSTEM }, { role: 'user', content: prompt }],
      response_format: {
        type: 'json_schema',
        json_schema: {
          name: 'verdict',
          strict: false,
          schema: VERDICT_SCHEMA
        }
      }
    })
  });
  if (!res.ok) throw new Error(`OpenAI ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const data = await res.json();
  return JSON.parse(data.choices[0].message.content);
}

/* -------------------------------------------------------------------- Demo */

async function demoVerifyCall({ url }) {
  await new Promise(r => setTimeout(r, 700 + Math.floor(Math.random() * 500)));
  return demoVerdict(url);
}

/* ----------------------------------------------------------------- Facade */

export async function verifyClaim(cfg, args) {
  const prompt = buildPrompt(args);
  switch (cfg.provider) {
    case 'openai': return openaiVerify({ key: cfg.key, model: cfg.model, prompt });
    case 'demo':   return demoVerifyCall({ url: args.page.url });
    default:       return claudeVerify({ key: cfg.key, model: cfg.model, prompt });
  }
}

/** Returns [] when the configured provider has no search capability. */
export async function findCandidates(cfg, { claim, missing, badUrl }) {
  if (cfg.provider === 'demo') {
    await new Promise(r => setTimeout(r, 900));
    return demoCandidates(badUrl);
  }
  if (cfg.provider === 'claude') {
    return claudeSearch({ key: cfg.key, model: cfg.model, claim, missing, badUrl });
  }
  return []; // OpenAI: no built-in search tool wired yet
}

export function supportsRepair(provider) {
  return provider === 'claude' || provider === 'demo';
}

/**
 * Smallest possible real call, so a wrong key fails here rather than halfway
 * through a verification. Deliberately routed through the same code path and
 * the same origin as the real requests — a test that takes a different route
 * can pass while the real one still fails.
 */
export async function testProvider({ provider, key, model }) {
  if (provider === 'demo') return { ok: true, detail: 'Demo mode makes no API calls.' };
  if (!key) return { ok: false, detail: 'No key entered.' };

  try {
    if (provider === 'openai') {
      const res = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${key}` },
        body: JSON.stringify({
          model: model || PROVIDERS.openai.defaultModel,
          messages: [{ role: 'user', content: 'ok' }],
          max_tokens: 1
        })
      });
      if (res.ok) return { ok: true, detail: `Reached OpenAI with ${model || PROVIDERS.openai.defaultModel}.` };
      const body = await res.text();
      return { ok: false, detail: explain(res.status, body, 'model name') };
    }

    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify({
        model: model || PROVIDERS.claude.defaultModel,
        max_tokens: 1,
        messages: [{ role: 'user', content: 'ok' }]
      })
    });
    if (res.ok) return { ok: true, detail: `Reached Claude with ${model || PROVIDERS.claude.defaultModel}.` };
    const body = await res.text();
    return { ok: false, detail: explain(res.status, body, 'model name') };
  } catch (e) {
    // A wrong key comes back as an HTTP 401, not as an exception. Landing here
    // means the request never reached the provider at all, so say that instead
    // of leaving the user staring at "Failed to fetch".
    const host = provider === 'openai' ? 'api.openai.com' : 'api.anthropic.com';
    return {
      ok: false,
      detail: `Could not reach ${host} — the request never left the browser, so this ` +
              `is not a bad key (that would come back as 401). Usual causes: no internet, ` +
              `a corporate proxy or VPN blocking the domain, or the extension was reloaded ` +
              `without host permissions. Raw error: ${e.message}`
    };
  }
}

function explain(status, body, hint) {
  let msg = '';
  try { msg = JSON.parse(body)?.error?.message || ''; } catch { msg = body.slice(0, 200); }
  if (status === 401) return `401 — the key was rejected. Check for a stray space or a key from a different provider. ${msg}`;
  if (status === 403) return `403 — key is valid but not allowed to use this ${hint}. ${msg}`;
  if (status === 404) return `404 — that model name does not exist for this key. ${msg}`;
  if (status === 429) return `429 — rate limited or out of credit. ${msg}`;
  return `${status} — ${msg}`;
}
