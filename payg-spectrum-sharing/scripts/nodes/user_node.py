#!/usr/bin/env python3
"""
User node: streams heartbeats to a file for BM to consume.

Reads data/hash_chain.json and emits heartbeat entries (i, y_i) every period seconds
into data/heartbeats.jsonl. BM node can tail this file to auto-claim.

Usage:
  python scripts/nodes/user_node.py --L 10 --period 30 --output data/heartbeats.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="User node: send heartbeats every period seconds.")
    parser.add_argument("--L", type=int, required=True, help="Limit (must match hash_chain.json)")
    parser.add_argument("--period", type=int, default=30, help="Seconds between heartbeats")
    parser.add_argument("--chain", type=Path, default=Path("data/hash_chain.json"))
    parser.add_argument("--output", type=Path, default=Path("data/heartbeats.jsonl"))
    args = parser.parse_args()

    chain = json.loads(args.chain.read_text())
    ys = chain["y_values"]
    sid_hex = chain["sid_hex"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Starting heartbeat stream (sid={sid_hex}, L={args.L}, period={args.period}s)")
    for i in range(1, args.L + 1):
        y_i = ys[f"y_{i}"]
        entry = {"i": i, "y_i": y_i, "sid": sid_hex, "ts": int(time.time())}
        with args.output.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"Heartbeat {i} -> {y_i}")
        if i != args.L:
            time.sleep(args.period)


if __name__ == "__main__":
    main()
