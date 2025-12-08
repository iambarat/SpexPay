#!/usr/bin/env python3
"""
End-to-end contract session runner using Foundry tools (anvil + cast/forge).

Flow:
 1) Start anvil locally.
 2) Deploy MockERC20 and Escrow with forge.
 3) Mint tokens to IssuerB, approve Escrow.
 4) Build hash chain y_L -> y_0 with sid, L.
 5) openSession, claim, closeSession.
Outputs JSON summary with tx hashes and gas used.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

FOUNDRY_BIN = Path.home() / ".foundry" / "bin"
ANVIL = FOUNDRY_BIN / "anvil"
CAST = FOUNDRY_BIN / "cast"
FORGE = FOUNDRY_BIN / "forge"
CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"

# Default Anvil accounts (foundry standard)
ISSUER_B_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ISSUER_B_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
BM_PK = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
BM_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def run(cmd: List[str], env: Dict[str, str] | None = None, capture_json: bool = False, cwd: Path | None = None) -> Tuple[str, Dict]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    merged_env["PATH"] = f"{FOUNDRY_BIN}:{merged_env.get('PATH','')}"
    proc = subprocess.run(cmd, env=merged_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    if proc.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    if capture_json:
        try:
            return proc.stdout.strip(), json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    return proc.stdout.strip(), {}


def start_anvil(port: int = 8545) -> subprocess.Popen:
    cmd = [str(ANVIL), "--port", str(port), "--silent"]
    env = os.environ.copy()
    env["PATH"] = f"{FOUNDRY_BIN}:{env.get('PATH','')}"
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    return proc


def stop_anvil(proc: subprocess.Popen) -> None:
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=2)
    except Exception:
        proc.kill()


def build_hash_chain(sid: bytes, L: int) -> List[bytes]:
    ys = [b""] * (L + 1)
    ys[L] = secrets.token_bytes(32)
    for idx in range(L, 0, -1):
        ys[idx - 1] = struct.pack(">Q", idx - 1)  # placeholder
        payload = sid + struct.pack(">Q", idx - 1) + ys[idx]
        ys[idx - 1] = __import__("hashlib").sha256(payload).digest()
    return ys


def hex32(b: bytes) -> str:
    return "0x" + b.hex()


def deploy(contract: str, args: List[str], rpc: str) -> str:
    cmd = [
        str(FORGE),
        "create",
        f"src/{contract}.sol:{contract}",
        "--rpc-url",
        rpc,
        "--private-key",
        ISSUER_B_PK,
        "--json",
    ]
    if args:
        cmd.extend(["--constructor-args"] + args)
    out, parsed = run(cmd, cwd=CONTRACTS_DIR, capture_json=True)
    if parsed and isinstance(parsed, dict):
        if "deployedTo" in parsed:
            return parsed["deployedTo"]
    # fallback parse: try to extract init code and deploy via cast --create
    try:
        data = json.loads(out)
        init_code = data.get("transaction", {}).get("input")
        if init_code:
            tx_out = cast_send_create(init_code, ISSUER_B_PK, rpc)
            tx_hash = parse_tx_hash(tx_out)
            receipt = get_receipt(tx_hash, rpc)
            if receipt.get("contractAddress"):
                return receipt["contractAddress"]
    except Exception:
        pass
    raise RuntimeError(f"Deploy address not found in output: {out}")


def cast_send_create(data_hex: str, pk: str, rpc: str) -> str:
    cmd = [
        str(CAST),
        "send",
        "--create",
        data_hex,
        "--",
        "--rpc-url",
        rpc,
        "--private-key",
        pk,
        "--gas-limit",
        "15000000",
    ]
    out, _ = run(cmd)
    return out


def parse_tx_hash(cast_output: str) -> str:
    # cast send typically prints the tx hash on the last line
    lines = cast_output.strip().splitlines()
    for line in reversed(lines):
        parts = line.strip().split()
        for p in parts:
            if p.startswith("0x") and len(p) >= 66:
                return p
    raise RuntimeError(f"Tx hash not found in output: {cast_output}")


def cast_send(to: str, sig: str, args: List[str], pk: str, rpc: str) -> str:
    cmd = [str(CAST), "send", to, sig] + args + ["--rpc-url", rpc, "--private-key", pk]
    out, _ = run(cmd)
    return out  # contains tx hash


def get_receipt(tx: str, rpc: str) -> Dict:
    out, parsed = run([str(CAST), "receipt", tx, "--rpc-url", rpc, "--json"], capture_json=True)
    if parsed and isinstance(parsed, dict):
        return parsed
    try:
        return json.loads(out)
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a full contract session on Anvil.")
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545", help="RPC URL (default anvil)")
    parser.add_argument("--port", type=int, default=8545, help="Anvil port to spawn")
    parser.add_argument("--L", type=int, default=10, help="Heartbeat limit L")
    parser.add_argument("--price", type=int, default=10**18, help="Price per beat (wei)")
    parser.add_argument("--deposit-mult", type=int, default=1, help="Multiply price*L by this factor")
    args = parser.parse_args()

    anvil_proc = start_anvil(port=args.port)
    rpc = f"http://127.0.0.1:{args.port}"
    try:
        # Deploy MockERC20
        token_addr = deploy("MockERC20", ["Mock", "MCK"], rpc)
        # Mint to IssuerB
        cast_send(token_addr, "mint(address,uint256)", [ISSUER_B_ADDR, str(10**24)], ISSUER_B_PK, rpc)

        # Deploy Escrow
        escrow_addr = deploy("Escrow", [], rpc)

        # Approve deposit
        deposit = args.price * args.L * args.deposit_mult
        cast_send(token_addr, "approve(address,uint256)", [escrow_addr, str(deposit)], ISSUER_B_PK, rpc)

        # Build hash chain
        sid_bytes = secrets.token_bytes(32)
        ys = build_hash_chain(sid_bytes, args.L)
        sid_hex = hex32(sid_bytes)
        y0_hex = hex32(ys[0])

        # Open session
        tx_open = cast_send(
            escrow_addr,
            "openSession(bytes32,address,address,bytes,uint64,uint64,uint256,uint256,bytes32)",
            [
                sid_hex,
                BM_ADDR,
                token_addr,
                "0x01",
                str(args.L),
                "0",
                str(args.price),
                str(deposit),
                y0_hex,
            ],
            ISSUER_B_PK,
            rpc,
        )
        txh_open = parse_tx_hash(tx_open)

        # Claim up to i=5 (or L if smaller)
        claim_i = min(5, args.L)
        tx_claim = cast_send(
            escrow_addr,
            "claim(bytes32,uint64,bytes32)",
            [sid_hex, str(claim_i), hex32(ys[claim_i])],
            BM_PK,
            rpc,
        )
        txh_claim = parse_tx_hash(tx_claim)

        # Close session
        tx_close = cast_send(escrow_addr, "closeSession(bytes32)", [sid_hex], ISSUER_B_PK, rpc)
        txh_close = parse_tx_hash(tx_close)

        receipt_open = get_receipt(txh_open, rpc)
        receipt_claim = get_receipt(txh_claim, rpc)
        receipt_close = get_receipt(txh_close, rpc)

        summary = {
            "token": token_addr,
            "escrow": escrow_addr,
            "sid": sid_hex,
            "L": args.L,
            "price": args.price,
            "deposit": deposit,
            "claim_i": claim_i,
            "txs": {
                "open": tx_open.strip(),
                "claim": tx_claim.strip(),
                "close": tx_close.strip(),
            },
            "gas_used": {
                "open": receipt_open.get("gasUsed"),
                "claim": receipt_claim.get("gasUsed"),
                "close": receipt_close.get("gasUsed"),
            },
        }
        print(json.dumps(summary, indent=2))
    finally:
        stop_anvil(anvil_proc)


if __name__ == "__main__":
    main()
