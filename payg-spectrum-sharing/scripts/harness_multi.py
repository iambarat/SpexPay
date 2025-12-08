#!/usr/bin/env python3
"""
Multi-session runner built on top of harness.py helpers.

Runs N sessions (User issues VC-A/B, proves, BM verifies), logs JSON summaries,
and appends rows to data/results/bm_user_sessions.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from harness import bm_verify, issue_credentials, prove_presentation


def run_session(attrs_a, attrs_b, device_index: int = 0) -> dict:
    cred_a, cred_b = issue_credentials(attrs_a, attrs_b, device_index=device_index)
    proof_result = prove_presentation(cred_a, cred_b, device_index=device_index)
    verified, t_verify = bm_verify(proof_result, cred_a, cred_b, device_index=device_index)
    proof_bytes = len(proof_result.proof.proof_hex) // 2
    return {
        "verified": bool(verified),
        "proof_size_bytes": proof_bytes,
        "prove_ms": proof_result.timings_ms["prove"],
        "verify_ms": t_verify,
    }


def append_row(row: dict, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    header = ["verified", "proof_size_bytes", "prove_ms", "verify_ms"]
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k) for k in header})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multiple BM/User sessions.")
    parser.add_argument("--sessions", type=int, default=10, help="Number of sessions to run")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("data/results/bm_user_sessions.csv"),
        help="CSV output path",
    )
    args = parser.parse_args()

    attrs_a = ["device_1234", "tier_gold", "class_nav", "expA_2026-12-31"]
    attrs_b = ["device_1234", "session_sid_01", "limit_3600", "y0_root", "band_X", "eirp_30dbm", "bm_0xabc", "expB_2026-12-31", "unit_price_100"]

    for i in range(args.sessions):
        result = run_session(attrs_a, attrs_b, device_index=0)
        print(json.dumps({"session": i + 1, **result}, indent=2))
        append_row(result, args.csv)


if __name__ == "__main__":
    main()
