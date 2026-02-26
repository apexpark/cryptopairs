#!/usr/bin/env bash
set -euo pipefail

echo "[rust-preflight] Running Rust CI preflight checks..."
echo "[rust-preflight] 1/3 cargo fmt --all -- --check"
cargo fmt --all -- --check

echo "[rust-preflight] 2/3 cargo clippy --workspace --all-targets -- -D warnings"
cargo clippy --workspace --all-targets -- -D warnings

echo "[rust-preflight] 3/3 cargo test --workspace"
cargo test --workspace

echo "[rust-preflight] All Rust preflight checks passed."
