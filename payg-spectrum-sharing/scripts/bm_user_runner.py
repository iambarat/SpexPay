#!/usr/bin/env python3
"""
Simple BM/User runner using the harness helpers.

Simulates a single session:
 1) Issuer A/B issue credentials to the user.
 2) User proves presentation (equality of hidden device_id across VC-A/VC-B).
 3) BM verifies off-chain and logs result.

Outputs a JSON summary and appends a CSV row for quick analysis.
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
    summary = {
        "verified": bool(verified),
        "proof_size_bytes": proof_bytes,
        "timings_ms": {
            "prove": proof_result.timings_ms["prove"],
            "verify": t_verify,
        },
    }
    return summary


def append_csv(row: dict, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    header = ["verified", "proof_size_bytes", "prove_ms", "verify_ms"]
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerow(
            [
                row["verified"],
                row["proof_size_bytes"],
                round(row["timings_ms"]["prove"], 3),
                round(row["timings_ms"]["verify"], 3),
            ]
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single BM/User off-chain verification session.")
    parser.add_argument("--csv", type=Path, default=Path("data/results/bm_user_sessions.csv"), help="CSV output path")
    args = parser.parse_args()

    attrs_a = ["device_1234", "tier_gold", "class_nav", "expA_2026-12-31"]
    attrs_b = ["device_1234", "session_sid_01", "limit_3600", "y0_root", "band_X", "eirp_30dbm", "bm_0xabc", "expB_2026-12-31", "unit_price_100"]

    summary = run_session(attrs_a, attrs_b, device_index=0)
    print(json.dumps(summary, indent=2))
    append_csv(summary, args.csv)


if __name__ == "__main__":
    main()
