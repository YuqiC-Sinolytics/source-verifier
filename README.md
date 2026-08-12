# Source Verifier

Checks whether each cited link in a piece of text **actually supports the sentence it
is attached to** — not just whether the link opens.

```
🟢 SUPPORTED    verbatim evidence on the page supports the claim
🟡 PARTIAL      page is on-topic but does not state this specific figure / date / claim
🔴 UNSUPPORTED  link is dead, or the page is unrelated to or contradicts the claim
⚪️ UNREACHABLE  paywall / JS-only / blocked — reported honestly, never guessed
```

Anything that is not green triggers a **web-wide search for a better source**, and any
candidate found has to pass the exact same verification before it is recommended.

## Run it in 30 seconds

```bash
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY

python cli.py                 # run the first built-in example in the terminal
python run.py                 # start the web UI and open a browser
```

**It runs without a key** — with no `ANTHROPIC_API_KEY` it drops into MOCK mode and
walks the whole pipeline on offline fixtures.

## Pipeline

```
S0  parse     regex -> (sentence, link) pairs      app/parser.py       rules, no LLM
S1  liveness  concurrent GET + soft-404 detection  app/reachability.py kills hard failures
S2  verify    Claude + web_fetch + citations       app/verify.py       <- the heart
S3  search    Claude + web_search for candidates   app/repair.py
S4  re-verify candidates face the same S2 gate     app/repair.py
```

Everything runs on Anthropic server tools, so **one API key covers all of it**:

| Purpose | Tool | Cost |
|---|---|---|
| Fetch the cited page (PDFs included) | `web_fetch` | free, tokens only |
| Search for a correct source | `web_search` | $10 / 1,000 searches |
| Verbatim evidence from the page | Citations | free — `cited_text` is not billed as output |

## Three things not to break

**1. `SYSTEM` in `app/verify.py` — the burden of proof sits on SUPPORTED.**
The default verdict is UNSUPPORTED; SUPPORTED requires a verbatim quote from the page.
Models lean hard toward agreeable "yes, this supports it" answers, and without
inverting the burden of proof the false-positive rate makes the tool worthless. There
is also a code-level backstop at the end of `verify_claim()`: a SUPPORTED verdict with
no `evidence_quote` is downgraded to PARTIAL. Prompts get talked around; that line
does not. **Do not delete it.**

**2. `app/cache.py` — venue wifi is the number one killer of live demos.**
Every verdict is written to disk keyed by `hash(kind|url|claim)`, so rehearsals and the
real run both return instantly and burn no quota. Warm the cache at the hotel the night
before.

**3. `MOCK=1` — the second, independent fallback.**
Fully offline: no HTTP, no API calls. Fixtures live in `app/mock.py`, matched by URL
substring.

## How the repair stage decides

PARTIAL is the case that matters most: the page is on-topic but the specific figure is
not on it. That is exactly when the real primary source is usually one search away, so
it always gets searched — and the search is *targeted*, not generic. `verify.py` asks
the model for a `missing_element` ("the 89% fall in the levelised cost of solar between
2010 and 2023"), and `repair.py` builds the search brief around that string.

"No reliable source found" is only ever said **after** candidates were fetched and
rejected, and the UI reports how many were checked and why each failed. A tool that
admits it cannot find something is far more credible than one that always produces a
link — but it has to have looked first.

## Opening a source at the evidence

Every link in the detail panel — the cited one and any better source found — carries a
[Text Fragment](https://developer.mozilla.org/en-US/docs/Web/URI/Fragment/Text_fragments)
directive built from the evidence quote:

```
https://example.org/report#:~:text=The%20global%20weighted%20average,between%202010%20and%202023.
```

Chrome, Edge and Safari scroll to that passage and highlight it on arrival, so a judge
clicking through lands on the sentence rather than on a 20,000-word page. Quotes longer
than 12 words are sent as `textStart,textEnd` — matching a range rather than one exact
string survives the whitespace and soft-hyphen differences that break full-string
matches.

Two honest caveats: Firefox ignores the directive and simply opens the page, and if the
page has changed since it was fetched the browser opens at the top. Both degrade
silently, which is the right behaviour — nothing breaks, you just do not get the jump.

The panel itself is ordered so the source comes before the verdict: **cited link → text
found in the source → the sentence from your text → analysis → repair outcome**. That
order matters on stage, because it makes the audience read the evidence before they read
the conclusion.

## Input

The textarea takes markdown, but it also **keeps hyperlinks when you paste formatted
text**. Copy a paragraph out of Word, Google Docs, Notion or a web page and the `<a href>`
elements are converted to markdown links on paste — including unwrapping the
`google.com/url?q=` redirectors that Google Docs inserts. A confirmation line tells you
how many links survived. Plain-text pastes are left alone.

Links are expected to sit on words inside the prose, the way cited AI output actually
looks, rather than as bare URLs at the end of a sentence. A sentence carrying two links
is handled correctly: each source is judged against the span it is attached to, not
against the whole sentence.

## Examples

Three are built in (`samples/examples/`), pickable from the chip row and preloaded on
open so a demo is one click from a result:

| Example | What it demonstrates |
|---|---|
| **Solar energy** | two dead links (one repaired), an on-topic page missing the figure that gets fixed via IRENA, and a contradicted number that stays red after two candidates are checked |
| **Obesity drugs** | a **journal homepage cited instead of an article** — the most common real-world citation failure — plus a fabricated DOI no search can rescue |
| **EU AI Act** | a wrong penalty figure (6% vs the statutory 7%) that stays red because no source states it, and a dead timeline URL repaired cleanly |

To add your own, drop a `.md` file into `samples/examples/`. An optional first line
`<!-- title: Something -->` sets the chip label.

## Demo script

Walk the **Solar energy** example:

| Sentence | Trap | Why it matters |
|---|---|---|
| 2,200 GW (IEA) | hard 404 | 🔴 warm-up, establishes trust |
| 60% (Reuters) | hard 404, replacement found | 🔴→🟢 shows the repair loop |
| 89% decline (OWID) | live, on-topic, figure absent | 🟡→🟢 **the first "huh?"** — searches, rejects a blog, lands on IRENA |
| 45% efficiency (Wikipedia) | page directly contradicts it | 🔴 **the big one** — checks 2 candidates, refuses to invent a source |
| 5.5% of generation (Wikipedia) | actually correct | 🟢 proves it is not just alarming |
| global-energy-review.org | domain does not exist | 🔴 the classic hallucinated URL |

Opening line, under 30 seconds:

> "This paragraph was written by an AI. Every sentence is cited. All but one of the
> links open fine — I checked."
> *(run it; the underlines light up one by one)*
> "Only one of those sentences is actually supported by the source it points at."

Close on the repair: show the better link **and the verbatim line inside it**. That
evidence quote is what separates this from every link checker in the room. Then click
the 45% claim and show the tool refusing to invent a source — that contrast is the
strongest 20 seconds you have.

## Evaluation

```bash
python eval.py
```

Reads `samples/eval.jsonl`, prints accuracy and a confusion matrix, and singles out
**SUPPORTED precision** — calling something supported when it is not is the only
failure mode that makes this tool worse than useless. Roughly 90 minutes of labelling
buys you "87% accuracy on 30 hand-labelled samples", which is the highest-return
addition you can make.

## Other commands

```bash
python run.py                # start the web UI (finds a free port from 8000 up)
python run.py 9000           # start looking from 9000 instead
python cli.py --list         # list the built-in examples
python cli.py my.md          # verify your own file
python cli.py --no-repair    # verify only — twice as fast while tuning prompts
python cli.py --clear-cache
```

`python run.py` exists because on Windows pip often puts console scripts in a
`Scripts\` directory that is not on PATH, so `uvicorn ...` fails even though the package
is installed. It also steps past a port that is already taken, which is the usual cause
of `WinError 10048`.

## Known limits

- `web_fetch` **does not render JavaScript**. Bloomberg, NYT and similar will fail and
  land in UNREACHABLE. That is the honest outcome — do not paper over it.
- `web_fetch` can only retrieve URLs that already appeared in context (from the user's
  text, or from a prior `web_search` result). The pipeline satisfies this naturally,
  but never expect the model to construct a URL itself.
- If the API rejects a server tool version, step `WEB_FETCH_TOOL` / `WEB_SEARCH_TOOL`
  down one release in `.env`.

## If time remains, in this order

1. **Accuracy numbers** — `eval.py` is built, it only needs labels
2. Same-domain retry: search again with `allowed_domains=[original domain]`, which is
   the usual fix when a site has been redesigned
3. Wayback fallback: `http://archive.org/wayback/available?url=...`, public, no key
4. docx / pdf upload: `python-docx` reads `w:hyperlink`, `pymupdf` has `page.get_links()`
   — lower priority than item 1, since it only adds an input path, not core value
