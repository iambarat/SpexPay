# PAYG Spectrum Sharing – Crypto/ZK Workflow (VC Issuance → Proof → BM Verify)

This document captures the reproducible steps to build and exercise the crypto layer only (VC issuance, proof generation/verification). It does **not** cover the on-chain escrow; focus is on Issuer A/B → User → Band Manager.

## Prerequisites
- Rust toolchain (rustc 1.91.0 noted).
- Python 3.12 with venv at `../spec-venv` (already present).
- Foundry not required for the crypto portion.

## Environment Setup
From repo root (`payg-spectrum-sharing`):
```bash
# Activate Python venv
source '../spec-venv/bin/activate'
```

## Build Rust → Python bindings
Located at `crypto/crypto_bindings`.
```bash
cd crypto/crypto_bindings
cargo check                     # sanity compile
maturin develop                 # build/install PyO3 module into the venv
```
What this does:
- Compiles the Rust bindings (`crypto_bindings` module) that expose BBS+ issuance and the composite proof (hidden `device_id` equality across VC-A and VC-B).
- Installs the module into the active Python environment.

## Quick ZK smoke test (single run or batch)
Script: `scripts/zk_smoke.py` (defaults: 10 runs, writes `data/results/zk_runs.csv`).
```bash
cd /home/bota/Drive/payg\ project/payg-spectrum-sharing
python scripts/zk_smoke.py --runs 1 --csv data/results/zk_runs.csv
```
What it does:
- Issuer A/B keygen + VC issuance with paper schema:
  - VC-A: `[device_id, tier, class, expA]`
  - VC-B: `[device_id, s_id, L, y0, band, max_eirp, bm_addr, expB, unit_price]`
- User proves hidden `device_id` equality across VC-A/VC-B.
- BM verifies the proof.
- Logs timings (issue/prove/verify) and proof size to CSV.

Make target for batch (10 runs by default):
```bash
make smoke
```

## Scenario runner (config-driven batches)
Script: `scripts/run_scenarios.py`.
Example config: `configs/zk_scenarios.json`.
Run:
```bash
python scripts/run_scenarios.py --config configs/zk_scenarios.json
```
What it does:
- Iterates scenarios/runs from JSON, executes proof/verify, appends metrics to `data/results/zk_scenarios.csv`.

## BM/User harness (off-chain verifier only)
Module: `scripts/harness.py`.
Helpers:
- `issue_credentials(attrs_a, attrs_b, device_index=0)`
- `prove_presentation(cred_a, cred_b, device_index=0, session_nonce=None)`
- `bm_verify(proof_result, cred_a, cred_b, device_index=0)`

Single-session demo:
```bash
python scripts/harness.py
```
Multi-session runner (logs to `data/results/bm_user_sessions.csv`):
```bash
make bm-users        # 10 sessions by default
# or custom
python scripts/harness_multi.py --sessions 20 --csv data/results/bm_user_sessions.csv
```

## Analysis of ZK metrics
Script: `scripts/zk_analysis.py` (works even without pandas/matplotlib; falls back to text summaries).
Default input now: `data/results/zk_runs.csv`.
```bash
python scripts/zk_analysis.py --input data/results/zk_runs.csv
```
Outputs:
- Summary stats (mean/p50/p90/p99) for prove/verify times and proof size.
- If matplotlib installed, saves histograms/scatter and a PDF table in `figures/`.

## Expected Outputs (current defaults)
- Proof size: ~897–1002 bytes (after removing Pedersen pseudonym).
- Timings (approx, vary per run): issue_a/b ~9–11 ms, prove ~44–47 ms, verify ~85–90 ms.
- CSVs:
  - `data/results/zk_runs.csv` (batched smoke runs)
  - `data/results/zk_scenarios.csv` (config-driven)
  - `data/results/bm_user_sessions.csv` (multi-session harness)

## Notes
- Proof now only enforces hidden `device_id` equality across VC-A and VC-B (no Pedersen pseudonym).
- Use `device_index=0` for the hidden field in both credentials.
- Nonces can be ASCII or hex; `session_nonce` binds the proof to a context.

## Smart Contract Layer (Escrow + Hash-Chain Claims)
> Use Foundry binaries (not `/usr/bin/forge`). In each shell:
```bash
export PATH="$HOME/.foundry/bin:$PATH"
export SVM_HOME="/home/bota/Drive/payg project/payg-spectrum-sharing/.svm"
```

### Contracts and Tests
- Location: `contracts/` (Escrow + MockERC20).
- Foundry config: `contracts/foundry.toml`.
- Tests: `contracts/test/Escrow.t.sol` cover:
- Happy path (open → claim → close),
- Replay/non-monotonic and over-claim rejection,
- Exact deposit funding,
- IssuerB-only close.
Run with gas report:
```bash
cd "/home/bota/Drive/payg project/payg-spectrum-sharing/contracts"
forge test --gas-report
```

### Manual Interaction on Anvil
1) Start Anvil (new terminal):
```bash
export PATH="$HOME/.foundry/bin:$PATH"
anvil --port 8545 --silent
```
2) Deploy MockERC20 (IssuerB key):
```bash
# NOTE: place global flags (*rpc-url*, *private-key*, *broadcast*) before the contract spec
# so they are parsed as global options.
forge create \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast --json \
  src/MockERC20.sol:MockERC20 \
  --constructor-args "Mock" "MCK"
```


Note deployed address as `TOKEN`. \
3) Deploy Escrow:
```bash
# place global flags before the contract spec (see above)
forge create \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast --json \
  src/Escrow.sol:Escrow
```

Note deployed address as `ESCROW`. 

```bash
# Export addresses
export TOKEN=0x...   # from above
export ESCROW=0x...

# Sanity check token exists
cast call $TOKEN "name()" --rpc-url http://127.0.0.1:8545

```

4) Mint & approve (IssuerB):
```bash
cast send $TOKEN "mint(address,uint256)" 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 1000000000000000000000 \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

cast send $TOKEN "approve(address,uint256)" $ESCROW 1000000000000000000000 \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```
<!-- 
6) openSession (IssuerB):
```bash
cast send $ESCROW \
  "openSession(bytes32,address,address,bytes,uint64,uint64,uint256,uint256,bytes32)" \
  $sid_hex 0x70997970C51812dc3A010C7d01b50e0d17dc79C8 $TOKEN 0x01 \
  5 0 1000000000000000000 5000000000000000000 $y0_hex \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```
7) claim (BM) up to i=5:
```bash
cast send $ESCROW "claim(bytes32,uint64,bytes32)" \
  $sid_hex 5 $y5_hex \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
``` -->
8) closeSession (IssuerB):
```bash
cast send $ESCROW "closeSession(bytes32)" $sid_hex \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

What this achieves:
- IssuerB opens a session with deposit ≥ price*L, seeds hash-chain root y0.
- BM claims beats with (i, yi); contract recomputes hash chain to lastY and pays.
- Only IssuerB can close; any leftover deposit is refunded.

## Hash-Chain Generation (User side)
Use `scripts/build_hash_chain.py` to derive `sid`, `y_L`, … `y_0` and heartbeat payloads (i||y_i):
```bash
python scripts/build_hash_chain.py --L 5 --output data/hash_chain.json
# optionally: --sid 0x<32-byte sid from Issuer B>
```
Output example (JSON):
```json
{
  "L": 5,
  "sid_hex": "0x...",
  "y_values": {
    "y_0": "0x...",
    "y_1": "0x...",
    "...": "...",
    "y_5": "0x..."
  },
  "heartbeats": {
    "heartbeat_1": "0x<i||y1>",
    "...": "...",
    "heartbeat_5": "0x<i||y5>"
  }
}
```
Issuer B receives `sid`, `L`, and `y0` from the user and uses them in `openSession`. The user later sends `heartbeat_i = (i || y_i)` to the BM; BM/contract verify with `y_{i-1} = sha256(sid || (i-1) || y_i)`.

### Using hash_chain.json to openSession (with placeholders)
After running `scripts/build_hash_chain.py --L <L> --output data/hash_chain.json`:
- Extract `sid_hex` and `y_0` (root) from `data/hash_chain.json` (e.g., with `jq`):
  ```bash
  sid_hex=$(jq -r '.sid_hex' data/hash_chain.json)
  y0_hex=$(jq -r '.y_values.y_0' data/hash_chain.json)
  ```
- Choose `L`, `price_per_beat`, and `deposit` (must be ≥ price_per_beat * L).
- Call `openSession` (IssuerB):

```bash
# Ensure Foundry in PATH and anvil is running on 8545
export PATH="$HOME/.foundry/bin:$PATH"

# Load sid/y0 from the JSON
sid_hex=$(jq -r '.sid_hex' data/hash_chain.json)
y0_hex=$(jq -r '.y_values.y_0' data/hash_chain.json)

# Set BM address, price, deposit, and L (from your hash_chain.json)
BM_ADDR=0x70997970C51812dc3A010C7d01b50e0d17dc79C8   # example BM
L=10                                                 # must match your JSON
PRICE_PER_BEAT_WEI=1000000000000000000              # 1 ETH as example
DEPOSIT_WEI=5000000000000000000                     # must be >= PRICE * L
PK_SESSION=0x01                                     # placeholder session key bytes

# Call openSession as IssuerB (using your TOKEN/ESCROW env vars)
cast send $ESCROW \
  "openSession(bytes32,address,address,bytes,uint64,uint64,uint256,uint256,bytes32)" \
  $sid_hex $BM_ADDR $TOKEN $PK_SESSION \
  $L 0 $PRICE_PER_BEAT_WEI $DEPOSIT_WEI $y0_hex \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

```




<!-- 
```bash
  cast send $ESCROW \
    "openSession(bytes32,address,address,bytes,uint64,uint64,uint256,uint256,bytes32)" \
    $sid_hex <BM_ADDR> $TOKEN 0x01 \
    <L> 0 <price_per_beat_wei> <deposit_wei> $y0_hex \
    --rpc-url http://127.0.0.1:8545 \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
  ``` -->
- BM can claim with any `i` and matching `y_i` from the JSON:
  ```bash
  cast send $ESCROW "claim(bytes32,uint64,bytes32)" \
    $sid_hex <i> $(jq -r ".y_values.y_${i}" data/hash_chain.json) \
    --rpc-url http://127.0.0.1:8545 \
    --private-key <BM_PRIVATE_KEY>
  ```

## Automated multi-node demo (IssuerB, User, BM)
This automates the off-chain heartbeat flow and on-chain claims using three long-running scripts.

### 0) Prereqs (one-time)
- Foundry in PATH: `export PATH="$HOME/.foundry/bin:$PATH"`
- Anvil running: `anvil --port 8545 --silent`
- Deploy contracts and export addresses:
  ```bash
  cd contracts
  forge create --rpc-url http://127.0.0.1:8545 \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
    --broadcast src/MockERC20.sol:MockERC20 --constructor-args "Mock" "MCK"
  export TOKEN=<address from deploy>

  forge create --rpc-url http://127.0.0.1:8545 \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
    --broadcast src/Escrow.sol:Escrow
  export ESCROW=<address from deploy>
  ```
- Fund/approve IssuerB in MockERC20 (same key as above):
  ```bash
  cast send $TOKEN "mint(address,uint256)" 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 1500 \
    --rpc-url http://127.0.0.1:8545 \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
  cast send $TOKEN "approve(address,uint256)" $ESCROW 1000 \
    --rpc-url http://127.0.0.1:8545 \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
  ```

### 1) User: build hash chain (one shot)
```bash
cd /home/bota/Drive/payg\ project/payg-spectrum-sharing
python scripts/build_hash_chain.py --L 20 --output data/hash_chain.json
# optional: --sid 0x<32 bytes> to supply sid from IssuerB
```
This produces `data/hash_chain.json` with `sid_hex`, `y_0`, …, `y_L`, and heartbeat payloads.

### 2) IssuerB node (terminal A)
Opens the session on-chain using `sid`/`y0` from the JSON.
```bash
cd /home/bota/Drive/payg\ project/payg-spectrum-sharing
export TOKEN=<mock token address>
export ESCROW=<escrow address>
export ISSUERB_PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80   # or your own
python scripts/nodes/issuer_b_node.py \
  --L 20 \
  --expB expB=$(date -d '+1 day' +%s) \
  --price 1000000000000000000 \
  --deposit 20000000000000000000 \
  --bm 0x70997970C51812dc3A010C7d01b50e0d17dc79C8   # BM address (Anvil account index 1)
```
What it does: reads `sid_hex`/`y_0` from `data/hash_chain.json` and calls `openSession(...)` on Escrow.

### 3) User node (terminal B)
Streams heartbeats every 30s to a JSONL file.
```bash
cd /home/bota/Drive/payg\ project/payg-spectrum-sharing
python scripts/nodes/user_node.py --L 20 --period 30 --output data/heartbeats.jsonl
```
What it does: reads `data/hash_chain.json` and appends `{"i": i, "y_i": "...", "sid": "...", "ts": ...}` lines.

### 4) BM node (terminal C)
Watches the heartbeat file and claims up to the latest heartbeat (contract verifies the whole gap against the stored last claim).
```bash
cd /home/bota/Drive/payg\ project/payg-spectrum-sharing
export ESCROW=<escrow address>
export BM_PK=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d   # pk for BM address 0x7099.. (Anvil account index 1)
python scripts/nodes/bm_node.py --heartbeats data/heartbeats.jsonl --rpc-url http://127.0.0.1:8545
# One-shot claim modes:
#   Claim up to latest beat seen so far, then exit:
#     python scripts/nodes/bm_node.py --claim-mode all
#   Claim only the latest beat (same as above but ignores older lines):
#     python scripts/nodes/bm_node.py --claim-mode latest
# Receipts for each claim (tx hash, sid, i) are appended to data/claims.jsonl by default.
```
What it does: tails `data/heartbeats.jsonl`; when new beats appear it claims **once** using the newest `i,y_i` (the contract walks the hash chain back to the last claimed heartbeat). Each claim writes a receipt to `data/claims.jsonl`.

### 5) Close (optional, IssuerB)
After all beats (or early), close the session:
```bash
cast send $ESCROW "closeSession(bytes32)" $(jq -r '.sid_hex' data/hash_chain.json) \
  --rpc-url http://127.0.0.1:8545 \
  --private-key $ISSUERB_PK
```

This three-node setup simulates the live flow: IssuerB opens the session, User emits heartbeats on a timer, and BM claims automatically.

## Inspect escrow state (beats claimed & spend)
- Read the full session struct (field order shown below):
  ```bash
  sid_hex=$(jq -r '.sid_hex' data/hash_chain.json)
  cast call $ESCROW \
    "sessions(bytes32)(address,address,address,bytes,uint64,bytes32,uint64,uint64,uint256,uint256,bool)" \
    $sid_hex \
    --rpc-url http://127.0.0.1:8545
  ```
  Tuple order: issuerB, bm, asset, pkSession, **lastI**, lastY, L, expB, **pricePerBeat**, **deposit (remaining)**, closed.
- Compute beats claimed / spent / remaining (replace RPC if needed):
  ```bash
  state=($(cast call $ESCROW \
    "sessions(bytes32)(address,address,address,bytes,uint64,bytes32,uint64,uint64,uint256,uint256,bool)" \
    $sid_hex --rpc-url http://127.0.0.1:8545))
  lastI=${state[4]}
  price=${state[8]}
  remaining=${state[9]}
  beats_claimed=$lastI
  spent=$(python - <<PY
  price=int("$price"); lastI=int("$lastI"); print(price*lastI)
  PY
  )
  echo "beats_claimed=$beats_claimed"
  echo "spent_wei=$spent"
  echo "remaining_deposit_wei=$remaining"
  ```
- Check token balances for escrow/BM:
  ```bash
  cast call $TOKEN "balanceOf(address)" $ESCROW --rpc-url http://127.0.0.1:8545   # deposit remaining
  cast call $TOKEN "balanceOf(address)" 0x70997970C51812dc3A010C7d01b50e0d17dc79C8 --rpc-url http://127.0.0.1:8545   # BM payout
  ```
