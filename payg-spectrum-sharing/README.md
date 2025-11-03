### This readme file contains detailed mechanism and workflow of Pay-as-you-go Dynamic Spectrum Sharing Model
### 1. System prerequisites

```bash
sudo apt update
sudo apt install -y build-essential pkg-config libssl-dev cmake curl git python3-dev python3-venv
```
### 2. Install Rust toolchain (for Dock + bindings)

```bash
# Install rustup + stable toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"

rustc -V
cargo -V

```

### 3. Create a Python package that wraps Dock's BBS+ (PyO3 + maturin)

```bash
pip install maturin

mkdir -p crypto/crypto_bindings && cd crypto/crypto_bindings
maturin init --bindings pyo3 --name -payg_bbs
```