use std::collections::{BTreeMap, BTreeSet};

use ark_bls12_381::{Bls12_381, Fr, G1Affine, G1Projective};
use ark_ec::Group;
use ark_ff::{PrimeField, UniformRand};
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use blake2::Blake2b512;
use once_cell::sync::Lazy;
use pyo3::{exceptions::PyValueError, prelude::*};
use rand::{rngs::OsRng, rngs::StdRng, SeedableRng};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use bbs_plus::prelude::{KeypairG2, PublicKeyG2, SecretKey, SignatureG1, SignatureParamsG1};
use dock_crypto_utils::signature::MultiMessageSignatureParams;
use proof_system::prelude::{
    EqualWitnesses, MetaStatement, MetaStatements, Proof, ProofSpec, Statements, Witness, Witnesses,
};
use proof_system::statement::{
    bbs_plus::{
        PoKBBSSignatureG1Prover as BbsProverStatement,
        PoKBBSSignatureG1Verifier as BbsVerifierStatement,
    },
};
use proof_system::witness::PoKBBSSignatureG1 as BbsSignatureWitness;

/// Issuer key material for BBS+ credentials.
#[pyclass]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct IssuerKeyPair {
    /// Hex-encoded secret key (bls12-381 scalar).
    #[pyo3(get)]
    pub sk_hex: String,
    /// Hex-encoded public key (compressed G2 bytes).
    #[pyo3(get)]
    pub pk_hex: String,
    /// Hex-encoded signature parameters (G1) tied to message count.
    #[pyo3(get)]
    pub params_hex: String,
}

/// Holder-facing credential artifact (signature + full message list).
#[pyclass]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Credential {
    /// Hex-encoded BBS+ signature bytes.
    #[pyo3(get)]
    pub signature_hex: String,
    /// Original messages (as UTF-8 strings).
    #[pyo3(get)]
    pub messages: Vec<String>,
    /// Hex-encoded signature params associated with this credential.
    #[pyo3(get)]
    pub params_hex: String,
}

/// Pedersen pseudonym committed to the hidden device identifier.
#[pyclass]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PedersenCommitment {
    /// Hex-encoded commitment (g^m * h^rho).
    #[pyo3(get)]
    pub commitment_hex: String,
    /// Hex-encoded blinding factor rho (kept client-side; optional for debugging).
    #[pyo3(get)]
    pub blinding_hex: String,
}

/// Composite proof tying two credentials together (hidden device_id equality).
#[pyclass]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompositeProof {
    /// Hex-encoded serialized proof bytes emitted by Dock proof_system.
    #[pyo3(get)]
    pub proof_hex: String,
    /// Indices + values revealed from VC-A.
    #[pyo3(get)]
    pub revealed_a: Vec<(usize, String)>,
    /// Indices + values revealed from VC-B.
    #[pyo3(get)]
    pub revealed_b: Vec<(usize, String)>,
}

/// Domain separators for deterministic generators.
const PEDERSEN_H_LABEL: &[u8] = b"PAYG-PEDERSEN-H";

static PEDERSEN_G: Lazy<G1Projective> = Lazy::new(G1Projective::generator);
static PEDERSEN_H: Lazy<G1Projective> = Lazy::new(|| derive_alt_generator(PEDERSEN_H_LABEL));

/// Generate issuer keys for a credential definition.
#[pyfunction]
pub fn keygen(message_count: usize) -> PyResult<IssuerKeyPair> {
    if message_count == 0 {
        return Err(PyValueError::new_err("message_count must be > 0"));
    }

    let mut rng = OsRng;
    let msg_count_u32 = u32::try_from(message_count)
        .map_err(|_| PyValueError::new_err("message_count must fit into u32"))?;
    let params = SignatureParamsG1::<Bls12_381>::generate_using_rng(&mut rng, msg_count_u32);
    let keypair = KeypairG2::<Bls12_381>::generate_using_rng(&mut rng, &params);

    Ok(IssuerKeyPair {
        sk_hex: serialize_to_hex(&keypair.secret_key)?,
        pk_hex: serialize_to_hex(&keypair.public_key)?,
        params_hex: serialize_to_hex(&params)?,
    })
}

/// Issue a verifiable credential using BBS+ signatures.
#[pyfunction]
pub fn issue_credential(sk_hex: &str, params_hex: &str, messages: Vec<String>) -> PyResult<Credential> {
    if messages.is_empty() {
        return Err(PyValueError::new_err("messages vector cannot be empty"));
    }

    let mut rng = OsRng;
    let secret_key: SecretKey<Fr> = deserialize_from_hex(sk_hex)?;
    let params: SignatureParamsG1<Bls12_381> = deserialize_from_hex(params_hex)?;
    let messages_fr = encode_messages(&messages);
    let signature = SignatureG1::<Bls12_381>::new(&mut rng, &messages_fr, &secret_key, &params)
        .map_err(|err| PyValueError::new_err(format!("{err:?}")))?;

    Ok(Credential {
        signature_hex: serialize_to_hex(&signature)?,
        messages,
        params_hex: serialize_to_hex(&params)?,
    })
}

/// Create a per-session Pedersen pseudonym linked to the hidden device identifier.
#[pyfunction]
#[pyo3(signature = (device_id_hex, blinding_hex=None))]
pub fn create_pedersen_pseudonym(device_id_hex: &str, blinding_hex: Option<&str>) -> PyResult<PedersenCommitment> {
    let device_bytes = hex_to_vec(device_id_hex)?;
    let device_scalar = Fr::from_le_bytes_mod_order(&device_bytes);

    let blinding_scalar = match blinding_hex {
        Some(hex) => deserialize_scalar(hex)?,
        None => Fr::rand(&mut OsRng),
    };

    let mut commitment = *PEDERSEN_G;
    commitment *= device_scalar;
    let mut h_part = *PEDERSEN_H;
    h_part *= blinding_scalar;
    commitment += h_part;

    let commitment_hex = serialize_to_hex(&G1Affine::from(commitment))?;
    let blinding_hex_out = match blinding_hex {
        Some(existing) => existing.to_string(),
        None => serialize_to_hex(&blinding_scalar)?,
    };

    Ok(PedersenCommitment {
        commitment_hex,
        blinding_hex: blinding_hex_out,
    })
}

/// Build the composite equality + commitment proof shown to the Band Manager.
#[pyfunction]
#[pyo3(signature = (
    vc_a,
    vc_b,
    revealed_a,
    revealed_b,
    session_nonce,
    pk_a_hex,
    pk_b_hex,
    device_index
))]
pub fn prove_session_presentation(
    vc_a: &Credential,
    vc_b: &Credential,
    revealed_a: Vec<(usize, String)>,
    revealed_b: Vec<(usize, String)>,
    session_nonce: &str,
    pk_a_hex: &str,
    pk_b_hex: &str,
    device_index: usize,
) -> PyResult<CompositeProof> {
    let _pk_a: PublicKeyG2<Bls12_381> = deserialize_from_hex(pk_a_hex)?;
    let _pk_b: PublicKeyG2<Bls12_381> = deserialize_from_hex(pk_b_hex)?;

    let params_a: SignatureParamsG1<Bls12_381> = deserialize_from_hex(&vc_a.params_hex)?;
    let params_b: SignatureParamsG1<Bls12_381> = deserialize_from_hex(&vc_b.params_hex)?;

    let signature_a: SignatureG1<Bls12_381> = deserialize_from_hex(&vc_a.signature_hex)?;
    let signature_b: SignatureG1<Bls12_381> = deserialize_from_hex(&vc_b.signature_hex)?;

    let (revealed_map_a, unrevealed_map_a) = partition_messages(&vc_a.messages, &revealed_a)?;
    let (revealed_map_b, unrevealed_map_b) = partition_messages(&vc_b.messages, &revealed_b)?;

    ensure_hidden_index(device_index, vc_a.messages.len(), &revealed_map_a)?;
    ensure_hidden_index(device_index, vc_b.messages.len(), &revealed_map_b)?;

    let device_scalar_a = encode_message(&vc_a.messages[device_index]);
    let device_scalar_b = encode_message(&vc_b.messages[device_index]);
    if device_scalar_a != device_scalar_b {
        return Err(PyValueError::new_err(
            "device_id mismatch across credentials; cannot prove equality",
        ));
    }

    let statement_a = BbsProverStatement::new_statement_from_params(
        params_a.clone(),
        revealed_map_a.clone(),
    );
    let statement_b = BbsProverStatement::new_statement_from_params(
        params_b.clone(),
        revealed_map_b.clone(),
    );

    let witness_a = Witness::PoKBBSSignatureG1(BbsSignatureWitness {
        signature: signature_a,
        unrevealed_messages: unrevealed_map_a.clone(),
    });
    let witness_b = Witness::PoKBBSSignatureG1(BbsSignatureWitness {
        signature: signature_b,
        unrevealed_messages: unrevealed_map_b.clone(),
    });

    let mut statements = Statements::<Bls12_381>::new();
    statements.add(statement_a);
    statements.add(statement_b);

    let mut witnesses = Witnesses::new();
    witnesses.add(witness_a);
    witnesses.add(witness_b);

    let mut meta_statements = MetaStatements::new();
    let equality_refs = vec![(0, device_index), (1, device_index)]
        .into_iter()
        .collect::<BTreeSet<_>>();
    meta_statements.add(MetaStatement::WitnessEquality(EqualWitnesses(equality_refs)));

    let nonce_bytes = session_nonce_bytes(session_nonce)?;
    let proof_spec = ProofSpec::new(statements, meta_statements, vec![], None);
    proof_spec
        .validate()
        .map_err(|e| PyValueError::new_err(format!("invalid proof spec: {e:?}")))?;

    let mut rng = StdRng::from_entropy();
    let (proof, _) = Proof::new::<StdRng, Blake2b512>(
        &mut rng,
        proof_spec,
        witnesses,
        Some(nonce_bytes.clone()),
        Default::default(),
    )
    .map_err(|e| PyValueError::new_err(format!("proof construction failed: {e:?}")))?;

    Ok(CompositeProof {
        proof_hex: serialize_to_hex(&proof)?,
        revealed_a,
        revealed_b,
    })
}

/// Verify the composite proof (for BM/unit tests).
#[pyfunction]
#[pyo3(signature = (
    proof,
    session_nonce,
    params_a_hex,
    pk_a_hex,
    params_b_hex,
    pk_b_hex,
    device_index
))]
pub fn verify_session_presentation(
    proof: &CompositeProof,
    session_nonce: &str,
    params_a_hex: &str,
    pk_a_hex: &str,
    params_b_hex: &str,
    pk_b_hex: &str,
    device_index: usize,
) -> PyResult<bool> {
    let pk_a: PublicKeyG2<Bls12_381> = deserialize_from_hex(pk_a_hex)?;
    let pk_b: PublicKeyG2<Bls12_381> = deserialize_from_hex(pk_b_hex)?;

    let params_a: SignatureParamsG1<Bls12_381> = deserialize_from_hex(params_a_hex)?;
    let params_b: SignatureParamsG1<Bls12_381> = deserialize_from_hex(params_b_hex)?;

    let proof_obj: Proof<Bls12_381> = deserialize_from_hex(&proof.proof_hex)?;

    let revealed_map_a = partition_messages_from_revealed(&proof.revealed_a)?;
    let revealed_map_b = partition_messages_from_revealed(&proof.revealed_b)?;

    ensure_hidden_index(
        device_index,
        params_a.supported_message_count(),
        &revealed_map_a,
    )?;
    ensure_hidden_index(
        device_index,
        params_b.supported_message_count(),
        &revealed_map_b,
    )?;

    let statement_a =
        BbsVerifierStatement::new_statement_from_params(params_a.clone(), pk_a, revealed_map_a);
    let statement_b =
        BbsVerifierStatement::new_statement_from_params(params_b.clone(), pk_b, revealed_map_b);

    let mut statements = Statements::<Bls12_381>::new();
    statements.add(statement_a);
    statements.add(statement_b);

    let mut meta_statements = MetaStatements::new();
    let equality_refs = vec![(0, device_index), (1, device_index)]
        .into_iter()
        .collect::<BTreeSet<_>>();
    meta_statements.add(MetaStatement::WitnessEquality(EqualWitnesses(equality_refs)));

    let proof_spec = ProofSpec::new(statements, meta_statements, vec![], None);
    proof_spec
        .validate()
        .map_err(|e| PyValueError::new_err(format!("invalid proof spec: {e:?}")))?;

    let nonce_bytes = session_nonce_bytes(session_nonce)?;
    let mut rng = StdRng::from_entropy();
    match proof_obj.verify::<StdRng, Blake2b512>(
        &mut rng,
        proof_spec,
        Some(nonce_bytes),
        Default::default(),
    ) {
        Ok(_) => Ok(true),
        Err(_) => Ok(false),
    }
}

/// PyO3 module initialization.
#[pymodule]
fn crypto_bindings(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<IssuerKeyPair>()?;
    m.add_class::<Credential>()?;
    m.add_class::<PedersenCommitment>()?;
    m.add_class::<CompositeProof>()?;

    m.add_function(wrap_pyfunction!(keygen, m)?)?;
    m.add_function(wrap_pyfunction!(issue_credential, m)?)?;
    m.add_function(wrap_pyfunction!(prove_session_presentation, m)?)?;
    m.add_function(wrap_pyfunction!(verify_session_presentation, m)?)?;
    Ok(())
}

// ----------------------
// Helper utilities
// ----------------------

fn serialize_to_hex<T: CanonicalSerialize>(value: &T) -> PyResult<String> {
    let mut buf = Vec::new();
    value
        .serialize_compressed(&mut buf)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(format!("0x{}", hex::encode(buf)))
}

fn deserialize_from_hex<T: CanonicalDeserialize>(hex_str: &str) -> PyResult<T> {
    let bytes = hex_to_vec(hex_str)?;
    T::deserialize_compressed(bytes.as_slice()).map_err(|e| PyValueError::new_err(e.to_string()))
}

fn deserialize_scalar(hex_str: &str) -> PyResult<Fr> {
    deserialize_from_hex::<Fr>(hex_str)
}

fn hex_to_vec(input: &str) -> PyResult<Vec<u8>> {
    hex::decode(strip_hex_prefix(input)).map_err(|e| PyValueError::new_err(e.to_string()))
}

fn strip_hex_prefix(input: &str) -> &str {
    input.strip_prefix("0x").unwrap_or(input)
}

fn encode_messages(messages: &[String]) -> Vec<Fr> {
    messages.iter().map(|m| encode_message(m)).collect()
}

fn encode_message(message: &str) -> Fr {
    Fr::from_le_bytes_mod_order(message.as_bytes())
}

fn partition_messages(
    messages: &[String],
    revealed: &[(usize, String)],
) -> PyResult<(BTreeMap<usize, Fr>, BTreeMap<usize, Fr>)> {
    let mut revealed_indices = BTreeSet::new();
    let mut revealed_map = BTreeMap::new();
    for (idx, claimed_value) in revealed {
        if !revealed_indices.insert(*idx) {
            return Err(PyValueError::new_err("duplicate index in revealed set"));
        }
        let actual = messages
            .get(*idx)
            .ok_or_else(|| PyValueError::new_err("revealed index out of range"))?;
        if actual != claimed_value {
            return Err(PyValueError::new_err(format!(
                "revealed value mismatch at index {idx}"
            )));
        }
        revealed_map.insert(*idx, encode_message(actual));
    }

    let mut unrevealed_map = BTreeMap::new();
    for (idx, msg) in messages.iter().enumerate() {
        if !revealed_indices.contains(&idx) {
            unrevealed_map.insert(idx, encode_message(msg));
        }
    }
    Ok((revealed_map, unrevealed_map))
}

fn partition_messages_from_revealed(
    revealed: &[(usize, String)],
) -> PyResult<BTreeMap<usize, Fr>> {
    let mut revealed_indices = BTreeSet::new();
    let mut revealed_map = BTreeMap::new();
    for (idx, value) in revealed {
        if !revealed_indices.insert(*idx) {
            return Err(PyValueError::new_err("duplicate index in revealed set"));
        }
        revealed_map.insert(*idx, encode_message(value));
    }
    Ok(revealed_map)
}

fn ensure_hidden_index(
    idx: usize,
    message_count: usize,
    revealed_map: &BTreeMap<usize, Fr>,
) -> PyResult<()> {
    if idx >= message_count {
        return Err(PyValueError::new_err("device index out of bounds"));
    }
    if revealed_map.contains_key(&idx) {
        return Err(PyValueError::new_err(
            "device index must remain hidden (not in revealed set)",
        ));
    }
    Ok(())
}

fn session_nonce_bytes(input: &str) -> PyResult<Vec<u8>> {
    if input.trim().is_empty() {
        return Err(PyValueError::new_err("session nonce cannot be empty"));
    }
    if input.starts_with("0x") {
        hex::decode(strip_hex_prefix(input)).map_err(|e| PyValueError::new_err(e.to_string()))
    } else {
        Ok(input.as_bytes().to_vec())
    }
}

fn derive_alt_generator(label: &[u8]) -> G1Projective {
    let mut h = G1Projective::generator();
    let digest = Sha256::digest(label);
    let scalar = Fr::from_le_bytes_mod_order(&digest);
    h *= scalar;
    h
}
