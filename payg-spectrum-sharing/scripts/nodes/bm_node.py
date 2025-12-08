#!/usr/bin/env python3
"""
BM node: tails data/heartbeats.jsonl and calls claim on Escrow for each new heartbeat.

Prereqs:
  - TOKEN, ESCROW env vars set
  - BM private key set (BM_PK); defaults to Anvil account #2
  - Anvil running on RPC_URL (default http://127.0.0.1:8545)

Usage:
  # follow new beats and claim automatically (default)
  python scripts/nodes/bm_node.py --heartbeats data/heartbeats.jsonl --rpc-url http://127.0.0.1:8545

  # one-shot: claim all beats seen so far, then exit
  python scripts/nodes/bm_node.py --claim-mode all

  # one-shot: claim only the latest beat, then exit
  python scripts/nodes/bm_node.py --claim-mode latest
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def run_cast(args, env=None):
    cmd = ["cast"] + args
    merged_env = os.environ.copy()
    merged_env["PATH"] = f"{os.path.expanduser('~')}/.foundry/bin:" + merged_env.get("PATH", "")
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, env=merged_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="BM node: watch heartbeats and claim on-chain.")
    parser.add_argument("--heartbeats", type=Path, default=Path("data/heartbeats.jsonl"))
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument("--poll", type=int, default=5, help="Polling interval seconds")
    parser.add_argument(
        "--claim-mode",
        choices=["auto", "all", "latest"],
        default="auto",
        help="auto = tail file, claim up to latest seen; all = claim up to latest seen then exit; latest = claim only most recent then exit",
    )
    parser.add_argument(
        "--receipts",
        type=Path,
        default=Path("data/claims.jsonl"),
        help="Where to append claim receipts (tx hash, sid, i)",
    )
    args = parser.parse_args()

    escrow = os.environ.get("ESCROW")
    bm_pk = os.environ.get("BM_PK", "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")
    if not escrow:
        raise SystemExit("Set ESCROW env var to deployed Escrow address.")

    def write_receipt(sid: str, i: int, tx: str, mode: str) -> None:
        args.receipts.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": int(time.time()), "sid": sid, "i": i, "tx": tx, "mode": mode}
        with args.receipts.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def process(lines: list[str], mode: str) -> None:
        if not lines:
            print("No heartbeats found.")
            return
        # Aggregate: claim only the latest beat (contract checks hash chain back to last claim)
        targets = [lines[-1]]
        for line in targets:
            if not line.strip():
                continue
            hb = json.loads(line)
            sid = hb["sid"]
            i = hb["i"]
            y_i = hb["y_i"]
            print(f"Claiming sid={sid} i={i} y_i={y_i}")
            tx = run_cast(
                [
                    "send",
                    escrow,
                    "claim(bytes32,uint64,bytes32)",
                    sid,
                    str(i),
                    y_i,
                    "--rpc-url",
                    args.rpc_url,
                    "--private-key",
                        bm_pk,
                    ]
                )
            write_receipt(sid, i, tx, mode)

    if args.claim_mode in {"all", "latest"}:
        if args.heartbeats.exists():
            lines = args.heartbeats.read_text().splitlines()
            process(lines, args.claim_mode)
        else:
            print(f"No heartbeat file at {args.heartbeats}")
        return

    print(f"BM node watching {args.heartbeats} (poll={args.poll}s)")
    processed = 0
    while True:
        if args.heartbeats.exists():
            lines = args.heartbeats.read_text().splitlines()
            new = lines[processed:]
            process(new, mode="all")
            processed = len(lines)
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
