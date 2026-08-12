# Source Verifier — Chrome extension

Right-click any cited link → **Verify this source** → the side panel says whether the
page it points at actually supports the sentence the link is attached to.

## Install (unpacked)

1. `chrome://extensions` → turn on **Developer mode**
2. **Load unpacked** → select this `extension/` folder
3. Right-click any link on any page → **Verify this source**

It works immediately with no API key: the provider defaults to **Demo**, which replays
offline fixtures and makes no network calls at all. To verify real pages, open the
extension's options and add a key.

## Why an extension beats the web version

The web version asks Claude's `web_fetch` to retrieve the cited page server-side. That
fetcher does not execute JavaScript and carries none of your cookies, so single-page
apps, login-gated pages and soft paywalls all come back as empty shells.

The extension opens the link in a **hidden background tab**, lets the page's own
JavaScript run, and reads the rendered DOM using your session. Measured on a
client-rendered test page:

```
server-side fetcher (raw HTML) :   2 readable words  -> UNREACHABLE
extension (hidden rendered tab): 113 readable words  -> verifiable
```

Same page, same URL. **If you can read it, the extension can read it.**

That also makes the provider genuinely swappable: because the extension does its own
reading, the model only ever judges text it is handed, so nothing depends on
Anthropic-specific fetch tooling.

## Flow

```
right-click a link
  -> content.js       finds the anchor you clicked and the sentence around it
  -> background.js    opens the link in a hidden tab, waits for render, reads it
  -> providers.js     model judges: does this page support that sentence?
  -> background.js    if not green: search for a better source
  -> each candidate   rendered in a hidden tab and put through the SAME gate
  -> sidepanel.js     verdict, evidence, and a link that highlights the passage
```

## Files

| File | Role |
|---|---|
| `content.js` | remembers the right-clicked element, extracts the claim sentence |
| `lib/extract.js` | injected into the hidden tab; returns readable text |
| `lib/verify.js` | the system prompt, the schema, and the two gates |
| `lib/providers.js` | Claude / OpenAI / demo behind one interface |
| `lib/demo-data.js` | offline fixtures |
| `background.js` | service worker: orchestrates everything |
| `sidepanel.js` | the result panel |
| `options.js` | provider, key, model, auto-repair |

## Two gates that must not be removed

**`enforceEvidenceGate`** — a SUPPORTED verdict with no verbatim quote is downgraded to
PARTIAL. Models lean hard toward agreeable "yes, that supports it" answers, and the
prompt alone gets talked around. This is the code-level backstop.

**`checkQuoteOnPage`** — the returned quote is searched for in the page text that was
actually read. A quote the model tidied up or half-remembered would produce a highlight
link that jumps nowhere, so an unverifiable quote is flagged rather than trusted. The
extension is in a better position than the web version here: it has the exact text the
page rendered, so this check is exact rather than approximate.

## Notes

- **The API key** lives in `chrome.storage.local` on this machine and goes only to the
  provider. That is a different situation from a public web page, where a key would be
  readable by anyone who opens DevTools — which is why the [GitHub Pages demo](../docs)
  ships pre-recorded results instead of calling any API.
- Claude needs the `anthropic-dangerous-direct-browser-access: true` header to be
  callable from a browser at all. It is set in `lib/providers.js`.
- **OpenAI is wired but less tested**, and has no search step, so a failed link is
  reported without a replacement.
- PDFs and `chrome://` pages reject script injection and come back UNREACHABLE. That is
  the honest answer, not a bug to paper over.
- The extension cannot be shared as a link — judges install it unpacked. That is why the
  GitHub Pages static demo stays as the public artifact.
