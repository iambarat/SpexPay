#!/usr/bin/env python3
"""
Lightweight sanity check for the Rust↔Python BBS+ bindings.

Steps:
1. keygen for N messages.
2. issue credentials (VC-A, VC-B) with the paper’s attribute schema.
3. derive a Pedersen pseudonym for device_id.
4. prove and verify the composite equality proof.
Outputs timing metrics and proof size for quick benchmarking.

Supports multiple runs and CSV logging for batching.
"""

from __future__ import annotations

import argparse
import csv
import json
import secrets
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional

import crypto_bindings as cb


def timed(fn, *args, **kwargs):
    start = perf_counter()
    result = fn(*args, **kwargs)
    elapsed_ms = (perf_counter() - start) * 1000.0
    return result, elapsed_ms


def run_once(
    attrs_a: List[str],
    attrs_b: List[str],
    device_id: str,
    session_nonce: Optional[str] = None,
    csv_path: Path = Path("data/results/zk_smoke.csv"),
    extra_csv_fields: Optional[Dict[str, str]] = None,
) -> Dict:
    issuer_a = cb.keygen(len(attrs_a))
    issuer_b = cb.keygen(len(attrs_b))

    vc_a, t_issue_a = timed(cb.issue_credential, issuer_a.sk_hex, issuer_a.params_hex, attrs_a)
    vc_b, t_issue_b = timed(cb.issue_credential, issuer_b.sk_hex, issuer_b.params_hex, attrs_b)

    device_index = 0
    device_id_hex = "0x" + device_id.encode().hex()

    revealed_a = [(1, attrs_a[1]), (3, attrs_a[3])]
    # Reveal everything except device_id (index 0)
    revealed_b = [
        (1, attrs_b[1]),  # s_id
        (2, attrs_b[2]),  # limit L
        (3, attrs_b[3]),  # y0 root
        (4, attrs_b[4]),  # band
        (5, attrs_b[5]),  # max eirp
        (6, attrs_b[6]),  # bm_addr
        (7, attrs_b[7]),  # expB
        (8, attrs_b[8]),  # unit price
    ]

    session_nonce = session_nonce or ("0x" + secrets.token_hex(16))
    proof, t_prove = timed(
        cb.prove_session_presentation,
        vc_a,
        vc_b,
        revealed_a,
        revealed_b,
        session_nonce,
        issuer_a.pk_hex,
        issuer_b.pk_hex,
        device_index,
    )
    verified, t_verify = timed(
        cb.verify_session_presentation,
        proof,
        session_nonce,
        issuer_a.params_hex,
        issuer_a.pk_hex,
        issuer_b.params_hex,
        issuer_b.pk_hex,
        device_index,
    )

    proof_bytes = len(proof.proof_hex) // 2  # hex string -> byte length

    payload = {
        "message_count": {"vc_a": len(attrs_a), "vc_b": len(attrs_b)},
        "device_id_hex": device_id_hex,
        "session_nonce": session_nonce,
        "issuer_a_pk": issuer_a.pk_hex[:20] + "...",
        "issuer_b_pk": issuer_b.pk_hex[:20] + "...",
        "proof_verified": verified,
        "proof_size_bytes": proof_bytes,
        "timings_ms": {
            "issue_a": t_issue_a,
            "issue_b": t_issue_b,
            "prove": t_prove,
            "verify": t_verify,
        },
    }

    print(json.dumps(payload, indent=2))

    # Append metrics to CSV for batching.
    out_dir = csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    header = [
        "message_count_a",
        "message_count_b",
        "proof_size_bytes",
        "issue_a_ms",
        "issue_b_ms",
        "prove_ms",
        "verify_ms",
    ]
    extra_header = list(extra_csv_fields.keys()) if extra_csv_fields else []
    row = [
        len(attrs_a),
        len(attrs_b),
        proof_bytes,
        round(t_issue_a, 3),
        round(t_issue_b, 3),
        round(t_prove, 3),
        round(t_verify, 3),
    ]
    extra_values = list(extra_csv_fields.values()) if extra_csv_fields else []

    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header + extra_header)
        writer.writerow(row + extra_values)

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run zk smoke test and log metrics.")
    parser.add_argument("--runs", type=int, default=10, help="Number of iterations to run")
    parser.add_argument("--device", type=str, default="device_1234", help="Device ID value")
    parser.add_argument("--nonce", type=str, default=None, help="Hex or ascii nonce (optional)")
    parser.add_argument("--csv", type=Path, default=Path("data/results/zk_runs.csv"), help="CSV output path")
    args = parser.parse_args()

    attrs_a = [
        args.device,
        "tier_gold",
        "class_nav",
        "expA_2026-12-31",
    ]
    attrs_b = [
        args.device,
        "session_sid_01",
        "limit_3600",
        "y0_root",
        "band_X",
        "eirp_30dbm",
        "bm_0xabc",
        "expB_2026-12-31",
        "unit_price_100",
    ]

    for run_idx in range(1, args.runs + 1):
        extra = {"run": run_idx}
        run_once(attrs_a, attrs_b, args.device, session_nonce=args.nonce, csv_path=args.csv, extra_csv_fields=extra)


if __name__ == "__main__":
    main()
