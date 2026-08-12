#!/usr/bin/env python3
"""Build a static, backend-free copy of the demo into docs/ for GitHub Pages.

    python build_static.py

Why this exists: GitHub Pages only serves files, so `/api/verify` cannot run
there — and it must not. Verification calls the Claude API, and an API key
shipped inside a web page is a key anyone can read out of DevTools.

So instead of exposing anything, we run every example through the pipeline here
and record the event stream. The published page replays those recordings. It is
the real output of the real pipeline, just pre-computed.

The recording is re-timed rather than replayed in capture order. In MOCK mode
everything resolves instantly and claim-by-claim; a real run verifies all the
sources quickly and in parallel, then spends seconds on the repair searches.
Replaying the raw capture would look nothing like the live tool, so events are
regrouped into the three phases a real run has:

    1. verdicts land one by one          (~380ms apart)
    2. searches open together            (shortly after)
    3. repairs resolve one at a time     (1.2-2.6s apart, the slow part)
"""

import asyncio
import json

from app import examples
from app.config import ROOT, cfg
from app.pipeline import run

OUT = ROOT / "docs"

# Replay cadence, milliseconds
T_PARSE = 250       # start -> first paint
T_REACH = 700       # liveness sweep
T_VERDICT = 380     # between successive verdicts
T_SEARCH_OPEN = 320 # verdicts done -> searches visible
T_REPAIR = 1250     # between successive repair results
T_REPAIR_JITTER = 380
T_TAIL = 450        # last repair -> done


def retime(events: list) -> list:
    """Regroup a captured run into verdict / search / repair phases."""
    start = [e for e in events if e["type"] == "start"]
    stage = [e for e in events if e["type"] == "stage"]
    done = [e for e in events if e["type"] == "done"]
    results = [e for e in events if e["type"] == "result"]

    verdicts, searching, repaired = [], [], []
    for e in results:
        r = e["result"]
        if r.get("searching"):
            searching.append(e)
        elif r.get("searched"):
            repaired.append(e)
        else:
            verdicts.append(e)

    out, t = [], 0
    for e in start:
        out.append({**e, "t": 0})
    t = T_PARSE
    for e in stage:
        out.append({**e, "t": T_REACH})
    t = T_REACH

    for e in verdicts:
        t += T_VERDICT
        out.append({**e, "t": t})

    if searching:
        t += T_SEARCH_OPEN
        for i, e in enumerate(searching):
            out.append({**e, "t": t + i * 90})
        t += len(searching) * 90

    for i, e in enumerate(repaired):
        # deterministic jitter so successive repairs do not land in lockstep
        t += T_REPAIR + (i * T_REPAIR_JITTER) % (T_REPAIR_JITTER * 2)
        out.append({**e, "t": t})

    for e in done:
        t += T_TAIL
        # report the replay's own wall-clock, not the instant mock run
        out.append({**e, "t": t, "elapsed_ms": t})

    return out


async def capture(text: str) -> list:
    return [ev async for ev in run(text, do_repair=True)]


async def main() -> None:
    if not cfg.mock:
        print("Note: ANTHROPIC_API_KEY is set, so recordings will use the live API.")
        print("      That is fine, but MOCK=1 gives the scripted demo narrative.\n")

    exs = examples.load_all()
    if not exs:
        raise SystemExit("No examples found in samples/examples/")

    (OUT / "data").mkdir(parents=True, exist_ok=True)

    for ex in exs:
        events = retime(await capture(ex["text"]))
        (OUT / "data" / f"{ex['id']}.json").write_text(
            json.dumps(events, ensure_ascii=False), "utf-8"
        )
        n = sum(1 for e in events if e["type"] == "result")
        span = max((e.get("t", 0) for e in events), default=0)
        print(f"  {ex['id']:<22} {n:>2} events, {span/1000:.1f}s replay")

    # Bake config + examples into the page so it needs no API at all
    config = {
        "examples": [{"id": e["id"], "title": e["title"], "text": e["text"]} for e in exs],
        "notice": (
            'Static demo — these runs were recorded ahead of time. '
            '<a href="https://github.com/YuqiC-Sinolytics/source-verifier" '
            'style="color:inherit">Run it locally</a> with an API key to check your own text.'
        ),
    }
    html = (ROOT / "static" / "index.html").read_text("utf-8")
    inject = "<script>window.SV_STATIC = " + json.dumps(config, ensure_ascii=False) + ";</script>\n"

    # Plain str.replace, never re.sub: in a regex replacement the \n and \" of
    # the JSON payload are treated as escapes and the config is destroyed.
    marker = "<script>\nconst $ ="
    if marker in html:
        html = html.replace(marker, inject + marker, 1)
    else:
        html = html.replace("</body>", inject + "</body>", 1)
    assert html.count("window.SV_STATIC = {") == 1, "config injected more than once"

    (OUT / "index.html").write_text(html, "utf-8")
    (OUT / ".nojekyll").touch()  # stop Pages from running Jekyll over the folder

    print(f"\nBuilt {OUT}")
    print("\nPublish it:")
    print("  git add docs && git commit -m 'static demo' && git push")
    print("  GitHub -> Settings -> Pages -> Source: main, folder: /docs")
    print("\nPublic URL: https://yuqic-sinolytics.github.io/source-verifier/")


if __name__ == "__main__":
    asyncio.run(main())
