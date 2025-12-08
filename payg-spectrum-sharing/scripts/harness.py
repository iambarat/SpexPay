#!/usr/bin/env python3
"""
Minimal harness wrapping the Rust bindings for issuing creds, proving, and BM verification.

Exposes three key helpers:
  - issue_credentials(attrs_a, attrs_b)
  - prove_presentation(creds, reveals_a, reveals_b, session_nonce, device_index=0)
  - bm_verify(proof, session_nonce, issuers, device_index=0)

Intended to be reused by higher-level orchestrators and tests.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from time import perf_counter
from typing import Dict, List, Tuple

import crypto_bindings as cb


@dataclass
class IssuerKeys:
    sk_hex: str
    pk_hex: str
    params_hex: str


@dataclass
class CredBundle:
    issuer: IssuerKeys
    credential: object  # cb.Credential
    revealed: List[Tuple[int, str]]


@dataclass
class ProofResult:
    proof: object  # cb.CompositeProof
    timings_ms: Dict[str, float]


def timed(fn, *args, **kwargs) -> Tuple[object, float]:
    start = perf_counter()
    result = fn(*args, **kwargs)
    elapsed_ms = (perf_counter() - start) * 1000.0
    return result, elapsed_ms


def issue_credentials(attrs_a: List[str], attrs_b: List[str], device_index: int = 0) -> Tuple[CredBundle, CredBundle]:
    raw_a = cb.keygen(len(attrs_a))
    raw_b = cb.keygen(len(attrs_b))
    issuer_a = IssuerKeys(sk_hex=raw_a.sk_hex, pk_hex=raw_a.pk_hex, params_hex=raw_a.params_hex)
    issuer_b = IssuerKeys(sk_hex=raw_b.sk_hex, pk_hex=raw_b.pk_hex, params_hex=raw_b.params_hex)

    cred_a = cb.issue_credential(issuer_a.sk_hex, issuer_a.params_hex, attrs_a)
    cred_b = cb.issue_credential(issuer_b.sk_hex, issuer_b.params_hex, attrs_b)

    # Default policy: hide device_id at device_index, reveal all others.
    revealed_a = [(idx, val) for idx, val in enumerate(attrs_a) if idx != device_index]
    revealed_b = [(idx, val) for idx, val in enumerate(attrs_b) if idx != device_index]

    return (
        CredBundle(issuer=issuer_a, credential=cred_a, revealed=revealed_a),
        CredBundle(issuer=issuer_b, credential=cred_b, revealed=revealed_b),
    )


def prove_presentation(
    cred_a: CredBundle,
    cred_b: CredBundle,
    device_index: int = 0,
    session_nonce: str | None = None,
) -> ProofResult:
    device_value = cred_a.credential.messages[device_index]

    nonce = session_nonce or ("0x" + secrets.token_hex(16))
    proof, t_prove = timed(
        cb.prove_session_presentation,
        cred_a.credential,
        cred_b.credential,
        cred_a.revealed,
        cred_b.revealed,
        nonce,
        cred_a.issuer.pk_hex,
        cred_b.issuer.pk_hex,
        device_index,
    )

    return ProofResult(
        proof=proof,
        timings_ms={
            "prove": t_prove,
            "device_index": device_index,
            "nonce": nonce,
        },
    )


def bm_verify(proof_result: ProofResult, cred_a: CredBundle, cred_b: CredBundle, device_index: int = 0) -> Tuple[bool, float]:
    verified, t_verify = timed(
        cb.verify_session_presentation,
        proof_result.proof,
        proof_result.timings_ms["nonce"],
        cred_a.issuer.params_hex,
        cred_a.issuer.pk_hex,
        cred_b.issuer.params_hex,
        cred_b.issuer.pk_hex,
        device_index,
    )
    return bool(verified), t_verify


def demo() -> None:
    attrs_a = ["device_1234", "tier_gold", "class_nav", "expA_2026-12-31"]
    attrs_b = ["device_1234", "session_sid_01", "limit_3600", "y0_root", "band_X", "eirp_30dbm", "bm_0xabc", "expB_2026-12-31", "unit_price_100"]

    cred_a, cred_b = issue_credentials(attrs_a, attrs_b, device_index=0)
    proof_result = prove_presentation(cred_a, cred_b, device_index=0)
    verified, t_verify = bm_verify(proof_result, cred_a, cred_b, device_index=0)

    proof_bytes = len(proof_result.proof.proof_hex) // 2
    print(
        f"Verified={verified}, proof_size={proof_bytes} bytes, "
        f"prove_ms={proof_result.timings_ms['prove']:.2f}, verify_ms={t_verify:.2f}"
    )


if __name__ == "__main__":
    demo()
