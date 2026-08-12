#!/usr/bin/env python3
"""Run the pipeline from the terminal — much faster than a browser when tuning prompts.

    python cli.py                    # first built-in example
    python cli.py --list             # show the built-in examples
    python cli.py my.md              # your own file
    python cli.py --no-repair        # verify only, skip the search stage
    python cli.py --clear-cache
"""

import asyncio
import sys
from pathlib import Path

from app import cache, examples
from app.config import cfg
from app.pipeline import run

C = {
    "SUPPORTED": "\033[32m",
    "PARTIAL": "\033[33m",
    "UNSUPPORTED": "\033[31m",
    "UNREACHABLE": "\033[90m",
}
DOT = {"SUPPORTED": "●", "PARTIAL": "●", "UNSUPPORTED": "●", "UNREACHABLE": "○"}
R, DIM = "\033[0m", "\033[2m"


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    if "--clear-cache" in flags:
        print(f"Cleared {cache.clear()} cache entries")
        return

    if "--list" in flags:
        for i, ex in enumerate(examples.load_all(), 1):
            print(f"  {i}. {ex['title']:<20} samples/examples/{ex['id']}.md")
        return

    path = Path(args[0]) if args else examples.first_path()
    text = examples.strip_title(path.read_text("utf-8"))

    print(f"{DIM}{path.name} · model {cfg.verify_model} · "
          f"{'MOCK mode (offline)' if cfg.mock else 'live mode'}{R}\n")

    shown = set()
    async for ev in run(text, do_repair="--no-repair" not in flags):
        if ev["type"] == "start":
            print(f"{DIM}{ev['total']} cited claims found{R}\n")

        elif ev["type"] == "result":
            r = ev["result"]
            v, key = r["verdict"], r["claim"]["id"]
            c = C.get(v, "")

            if key not in shown:
                shown.add(key)
                tag = " (cached)" if r["cached"] else ""
                print(f"{c}{DOT.get(v,'·')} {v}{R}{DIM}{tag}{R}  {r['claim']['display'][:88]}")
                print(f"  {DIM}{r['claim']['url']}{R}")
                if r["reason"]:
                    print(f"  {r['reason']}")
                if r["evidence_quote"]:
                    print(f"  {DIM}evidence │ {r['evidence_quote'][:150]}{R}")
                print()

            if r["searching"]:
                print(f"  {DIM}searching the web for "
                      f"{r.get('missing_element') or 'a better source'}…{R}")
            elif r["replacement"]:
                rep = r["replacement"]
                extra = (f" {DIM}({len(r['rejected'])} rejected){R}" if r["rejected"] else "")
                print(f"  {C['SUPPORTED']}→ better source{R} {rep['url']}{extra}")
                if rep.get("evidence_quote"):
                    print(f"    {DIM}evidence │ {rep['evidence_quote'][:150]}{R}")
                print()
            elif r["searched"]:
                n = r["candidates_checked"]
                detail = (
                    "search returned no candidates"
                    if n == 0
                    else f"checked {n} candidate{'' if n == 1 else 's'}"
                )
                print(f"  {C['UNSUPPORTED']}→ no supporting source found{R} {DIM}({detail}){R}")
                for x in r["rejected"]:
                    print(f"    {DIM}✗ {x['url'][:72]}{R}")
                    if x.get("reason"):
                        print(f"      {DIM}{x['reason'][:96]}{R}")
                print()

        elif ev["type"] == "done":
            parts = [f"{C.get(k,'')}{k} {v}{R}" for k, v in sorted(ev["summary"].items())]
            print(f"{DIM}{'─' * 62}{R}")
            print("  ".join(parts) + f"   {DIM}{ev['elapsed_ms']/1000:.1f}s{R}")

        elif ev["type"] == "error":
            print(f"\033[31mError: {ev['message']}{R}")


if __name__ == "__main__":
    asyncio.run(main())
