use pyo3::prelude::*;

/// added lines 
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};

// Dock crates
use bbs_plus::prelude::*;
use proof_system::prelude::*;


/// Simple struct to return keys as hex strings
#[derive(Serialize, Deserialize)]
struct BbsKeyPair {
    sk: String,
    pk: String,
}

/// Convert bytes -> 0x-hex
fn to_hex(b: &[u8]) -> String { format!("0x{}", hex::encode(b)) }

#[pyfunction]
fn bbs_keygen(message_count: usize) -> PyResult<String> {
    // Generate issuer keys for BBS+
    // Note: message_count is used by some APIs for key tailoring; here we keep generic sk/pk.
    let mut rng = OsRng;
    let (sk, pk) = DeterministicPublicKey::keygen_using_seed::<Bls12_381>(&mut rng);
    let sk_bytes = sk.to_bytes();
    let pk_bytes = pk.to_bytes_compressed_form();
    let out = BbsKeyPair {
        sk: to_hex(&sk_bytes),
        pk: to_hex(&pk_bytes),
    };
    Ok(serde_json::to_string(&out).unwrap())
}

#[pyfunction]
fn bbs_sign(sk_hex: &str, messages: Vec<String>) -> PyResult<String> {
    // Sign a vector of messages (as UTF-8 strings) with BBS+
    let sk_bytes = hex::decode(&sk_hex.trim_start_matches("0x")).unwrap();
    let sk = SecretKey::<Bls12_381>::from_bytes(&sk_bytes).unwrap();

    let msgs: Vec<Fr> = messages.iter().map(|m| Fr::from_le_bytes_mod_order(m.as_bytes())).collect();

    let mut rng = OsRng;
    let sig = Signature::<Bls12_381>::new(&mut rng, &msgs, &sk).unwrap();
    Ok(to_hex(&sig.to_bytes()))

#[pyfunction]
fn bbs_verify(pk_hex: &str, messages: Vec<String>, sig_hex: &str) -> PyResult<bool> {
    let pk_bytes = hex::decode(pk_hex.trim_start_matches("0x")).unwrap();
    let pk = DeterministicPublicKey::<Bls12_381>::from_bytes_compressed_form(&pk_bytes).unwrap();

    let msgs: Vec<Fr> = messages.iter().map(|m| Fr::from_le_bytes_mod_order(m.as_bytes())).collect();

    let sig_bytes = hex::decode(sig_hex.trim_start_matches("0x")).unwrap();
    let sig = Signature::<Bls12_381>::from_bytes(&sig_bytes).unwrap();

    Ok(sig.verify(&msgs, &pk).unwrap_or(false))
}

/// Create a ZK proof that:
/// 1) You know a valid BBS+ signature over messages of VC-A (some revealed, one hidden m*).
/// 2) You know a valid BBS+ signature over messages of VC-B (some revealed, same hidden m*).
/// 3) You know a Pedersen commitment U_sess = g^{m*} h^{rho}.
///
/// And that the hidden m* in both signatures equals the m* in the commitment (unlinkable per-session via fresh rho).
#[pyfunction]
fn prove_cross_cred_equality_with_pedersen(
    pk_a_hex: &str,
    sig_a_hex: &str,
    msgs_a: Vec<Option<String>>, // None = hidden, Some = revealed
    pk_b_hex: &str,
    sig_b_hex: &str,
    msgs_b: Vec<Option<String>>,
    session_nonce: &str,         // binds proof to a session context
) -> PyResult<String> {
    // NOTE: This function sketches the structure using proof_system meta-statements.
    // In your real code, define statements for each signature and a commitment statement,
    // then add EqualWitnesses meta-statements tying the same witness index across statements.
    // For brevity, we return a JSON "placeholder" with fields you'd transmit.

    // -- parse inputs (omitted: full construction of Statements & Witnesses with proof_system) --

    #[derive(Serialize)]
    struct ProofBundle {
        pedersen_commitment: String, // 0x...
        proof_bytes: String,         // 0x...
        revealed_a: Vec<(usize, String)>,
        revealed_b: Vec<(usize, String)>,
        nonce: String,
    }

    // Pseudo: build Pedersen commitment with fresh rho and same m* (hidden index must match in msgs_a/msgs_b)
    let pedersen_commitment_hex = "0xPSEUDO_COMMITMENT";

    // Pseudo: build composite proof (BBS+ knowledge for A, B, plus Pedersen knowledge)
    // with EqualWitnesses([ (A, idx_mstar), (B, idx_mstar), (Pedersen, idx_mstar) ])
    let proof_hex = "0xPSEUDO_PROOF";

    let revealed_a: Vec<(usize, String)> = msgs_a.iter().enumerate()
        .filter_map(|(i, m)| m.as_ref().map(|v| (i, v.clone()))).collect();
    let revealed_b: Vec<(usize, String)> = msgs_b.iter().enumerate()
        .filter_map(|(i, m)| m.as_ref().map(|v| (i, v.clone()))).collect();

    let out = ProofBundle {
        pedersen_commitment: pedersen_commitment_hex.to_string(),
        proof_bytes: proof_hex.to_string(),
        revealed_a,
        revealed_b,
        nonce: session_nonce.to_string(),
    };
    Ok(serde_json::to_string(&out).unwrap())
}

#[pymodule]
fn payg_bbs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(bbs_keygen, m)?)?;
    m.add_function(wrap_pyfunction!(bbs_sign, m)?)?;
    m.add_function(wrap_pyfunction!(bbs_verify, m)?)?;
    m.add_function(wrap_pyfunction!(prove_cross_cred_equality_with_pedersen, m)?)?;
    Ok(())
}








/// Formats the sum of two numbers as string.
#[pyfunction]
fn sum_as_string(a: usize, b: usize) -> PyResult<String> {
    Ok((a + b).to_string())
}

/// A Python module implemented in Rust.
#[pymodule]
fn payg_bbs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sum_as_string, m)?)?;
    Ok(())
}
