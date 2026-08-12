#!/usr/bin/env python3
"""Evaluation set — the highest-return add-on you can build.

Judges react far better to "87% accuracy on 30 hand-labelled samples" than to
any additional feature. Labelling 30 pairs takes about 90 minutes. Worth it.

Usage:
    1. Add lines to samples/eval.jsonl:
       {"claim": "...", "url": "...", "label": "SUPPORTED"}
       label is one of SUPPORTED / PARTIAL / UNSUPPORTED / UNREACHABLE
    2. python eval.py
"""

import asyncio
import json
from collections import defaultdict

from app.config import ROOT
from app.models import Claim, Reach
from app.reachability import resolve as resolve_reach
from app.verify import verify_claim

LABELS = ["SUPPORTED", "PARTIAL", "UNSUPPORTED", "UNREACHABLE"]


async def main() -> None:
    path = ROOT / "samples" / "eval.jsonl"
    rows = [json.loads(l) for l in path.read_text("utf-8").splitlines() if l.strip()]
    if not rows:
        print("samples/eval.jsonl is empty — label a few pairs first.")
        return

    claims = [
        Claim(id=str(i), sentence=r["claim"], display=r["claim"], url=r["url"],
              anchor="", start=0, end=0, link_start=0, link_end=0)
        for i, r in enumerate(rows)
    ]
    reaches = await resolve_reach(claims)
    results = await asyncio.gather(
        *(verify_claim(c, reaches.get(c.url, Reach())) for c in claims)
    )

    correct = 0
    confusion = defaultdict(int)
    for r, row in zip(results, rows):
        gold = row["label"]
        confusion[(gold, r.verdict)] += 1
        if gold == r.verdict:
            correct += 1
        else:
            print(f"✗ gold={gold:<12} pred={r.verdict:<12} {row['claim'][:58]}")

    n = len(rows)
    print(f"\nAccuracy {correct}/{n} = {correct/n:.1%}\n")

    # The number to watch. Calling something SUPPORTED when it is not is the
    # only failure mode that makes this tool worse than useless.
    pred_sup = sum(v for (g, p), v in confusion.items() if p == "SUPPORTED")
    true_sup = confusion[("SUPPORTED", "SUPPORTED")]
    if pred_sup:
        print(f"SUPPORTED precision {true_sup}/{pred_sup} = {true_sup/pred_sup:.1%}"
              f"   <- if this drops, the prompt has gone soft")

    print("\nConfusion matrix (rows = gold, cols = predicted)")
    print(f"{'':<14}" + "".join(f"{l[:6]:<8}" for l in LABELS))
    for g in LABELS:
        print(f"{g:<14}" + "".join(f"{confusion[(g, p)]:<8}" for p in LABELS))


if __name__ == "__main__":
    asyncio.run(main())
