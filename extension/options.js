const PROVIDERS = {
  claude: {
    label: 'Claude (Anthropic)', needsKey: true, defaultModel: 'claude-sonnet-5',
    hint: 'Tested path. Also the only provider wired for the "find a better source" search step.',
    modelHint: 'e.g. claude-sonnet-5 — Sonnet is fast and cheap enough for this.'
  },
  openai: {
    label: 'OpenAI', needsKey: true, defaultModel: 'gpt-4.1',
    hint: 'Implemented and wired, but less tested than Claude. No search step yet, so failed links are reported without a replacement.',
    modelHint: 'Any chat model that supports JSON schema responses.'
  },
  demo: {
    label: 'Demo — offline, no key', needsKey: false, defaultModel: '',
    hint: 'No key, no network, no API calls. Replays the same fixtures the web app ships, so you can install and demo the extension before any key exists.',
    modelHint: 'Not used in demo mode.'
  }
};

const $ = s => document.querySelector(s);

function syncHints() {
  const p = PROVIDERS[$('#provider').value];
  $('#phint').textContent = p.hint;
  $('#mhint').textContent = p.modelHint;
  $('#key').disabled = !p.needsKey;
  $('#model').disabled = !p.needsKey;
  $('#key').placeholder = p.needsKey ? 'sk-…' : 'not needed in demo mode';
}

async function load() {
  const sel = $('#provider');
  for (const [id, p] of Object.entries(PROVIDERS)) {
    const o = document.createElement('option');
    o.value = id; o.textContent = p.label; sel.appendChild(o);
  }
  const d = await chrome.storage.local.get(['provider', 'key', 'model', 'autoRepair']);
  sel.value = d.provider || 'demo';
  $('#key').value = d.key || '';
  $('#model').value = d.model || PROVIDERS[sel.value].defaultModel;
  $('#autoRepair').checked = d.autoRepair !== false;
  syncHints();
}

$('#provider').addEventListener('change', () => {
  $('#model').value = PROVIDERS[$('#provider').value].defaultModel;
  syncHints();
});

$('#save').addEventListener('click', async () => {
  await chrome.storage.local.set({
    provider: $('#provider').value,
    key: $('#key').value.trim(),
    model: $('#model').value.trim(),
    autoRepair: $('#autoRepair').checked
  });
  $('#saved').textContent = 'Saved';
  setTimeout(() => ($('#saved').textContent = ''), 1800);
});

$('#test').addEventListener('click', async () => {
  const box = $('#result');
  box.className = 'result ok';
  box.textContent = 'Testing…';
  const res = await chrome.runtime.sendMessage({
    type: 'sv:test-key',
    cfg: {
      provider: $('#provider').value,
      key: $('#key').value.trim(),
      model: $('#model').value.trim()
    }
  });
  box.className = 'result ' + (res.ok ? 'ok' : 'bad');
  box.textContent = (res.ok ? '✓ ' : '✗ ') + res.detail;
});

load();
