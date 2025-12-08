#!/usr/bin/env python3
"""
Build a hash chain y_L -> y_0 given a session id (sid) and limit L.
Uses: y_i = sha256(sid || i || y_{i+1}) with i encoded as big-endian uint64.
Outputs JSON with sid, y_0..y_L, and heartbeat payloads (i || y_i).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import struct
from pathlib import Path


def build_hash_chain(L: int, sid: bytes | None = None) -> dict:
    if L <= 0:
        raise ValueError("L must be > 0")
    sid_bytes = sid or secrets.token_bytes(32)
    ys = [b""] * (L + 1)
    ys[L] = secrets.token_bytes(32)  # user-chosen random y_L
    for i in range(L - 1, -1, -1):
        ys[i] = hashlib.sha256(sid_bytes + struct.pack(">Q", i) + ys[i + 1]).digest()

    # Build heartbeat payloads (i || y_i)
    heartbeats = {f"heartbeat_{i}": "0x" + (struct.pack(">Q", i) + ys[i]).hex() for i in range(1, L + 1)}

    return {
        "L": L,
        "sid_hex": "0x" + sid_bytes.hex(),
        "y_values": {f"y_{i}": "0x" + ys[i].hex() for i in range(L + 1)},
        "heartbeats": heartbeats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate hash chain y_L -> y_0 for heartbeats.")
    parser.add_argument("--L", type=int, required=True, help="Limit (max heartbeat index)")
    parser.add_argument("--sid", type=str, default=None, help="Hex sid (32 bytes) from Issuer B; if omitted, random is used")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write JSON output")
    args = parser.parse_args()

    sid_bytes = bytes.fromhex(args.sid[2:] if args.sid and args.sid.startswith("0x") else args.sid) if args.sid else None
    result = build_hash_chain(args.L, sid_bytes)
    out_json = json.dumps(result, indent=2)
    print(out_json)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out_json, encoding="utf-8")


if __name__ == "__main__":
    main()
