#!/usr/bin/env python3
"""
Issuer B node: opens an escrow session using sid/y0 from data/hash_chain.json.
Prereqs:
  - Anvil running on RPC_URL (default http://127.0.0.1:8545)
  - TOKEN, ESCROW env vars set to deployed addresses
  - IssuerB private key set (ISSUERB_PK)
Usage:
  python scripts/nodes/issuer_b_node.py --L 10 --price 1000000000000000000 --deposit 10000000000000000000 --bm 0x... [--sid-json data/hash_chain.json]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_RPC = "http://127.0.0.1:8545"


def run_cast(args):
    cmd = ["cast"] + args
    env = os.environ.copy()
    env["PATH"] = f"{os.path.expanduser('~')}/.foundry/bin:" + env.get("PATH", "")
    out = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if out.returncode != 0:
        print(out.stdout)
        print(out.stderr, file=sys.stderr)
        raise SystemExit(out.returncode)
    return out.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description="Issuer B: open escrow session.")
    parser.add_argument("--L", type=int, required=True)
    parser.add_argument("--price", type=int, required=True, help="price per beat (wei)")
    parser.add_argument("--deposit", type=int, required=True, help="deposit (wei)")
    parser.add_argument("--bm", required=True, help="Band Manager address")
    parser.add_argument("--pk-session", default="0x01", help="session pubkey bytes")
    parser.add_argument("--sid-json", type=Path, default=Path("data/hash_chain.json"))
    parser.add_argument("--rpc-url", default=DEFAULT_RPC)
    args = parser.parse_args()

    token = os.environ.get("TOKEN")
    escrow = os.environ.get("ESCROW")
    issuer_pk = os.environ.get("ISSUERB_PK", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
    if not token or not escrow:
        raise SystemExit("Set TOKEN and ESCROW env vars to deployed addresses.")

    data = json.loads(args.sid_json.read_text())
    sid_hex = data["sid_hex"]
    y0_hex = data["y_values"]["y_0"]

    print(f"Opening session sid={sid_hex}, y0={y0_hex}, L={args.L}, price={args.price}, deposit={args.deposit}")
    run_cast(
        [
            "send",
            escrow,
            "openSession(bytes32,address,address,bytes,uint64,uint64,uint256,uint256,bytes32)",
            sid_hex,
            args.bm,
            token,
            args.pk_session,
            str(args.L),
            "0",
            str(args.price),
            str(args.deposit),
            y0_hex,
            "--rpc-url",
            args.rpc_url,
            "--private-key",
            issuer_pk,
        ]
    )
    print("Session opened.")


if __name__ == "__main__":
    main()
