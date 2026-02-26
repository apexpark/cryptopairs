#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

git config core.hooksPath .githooks
echo "[hooks] Installed repository hooks path: .githooks"
echo "[hooks] pre-push now runs scripts/check-rust-ci.sh"
