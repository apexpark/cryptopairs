#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_SOURCE="$ROOT_DIR/.githooks/pre-push"
TMP_ROOT="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "[test-pre-push] FAIL: $*" >&2
  exit 1
}

write_fake_check_script() {
  mkdir -p scripts
  cat > scripts/check-rust-ci.sh <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${FAKE_RUST_CHECK_MARKER:-}" ]]; then
  mkdir -p "$(dirname "$FAKE_RUST_CHECK_MARKER")"
  printf "ran\n" > "$FAKE_RUST_CHECK_MARKER"
fi

if [[ -f .check/expected-tracked ]]; then
  if ! cmp -s .check/expected-tracked tracked.txt; then
    echo "[fake-rust-check] tracked.txt did not match the expected staged tree" >&2
    exit 20
  fi
fi

if [[ -f .check/absent-paths ]]; then
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if [[ -e "$path" ]]; then
      echo "[fake-rust-check] $path should not be visible during the hook run" >&2
      exit 21
    fi
  done < .check/absent-paths
fi

if [[ -f .check/signal-int ]]; then
  kill -INT "$PPID"
  exit 130
fi

if [[ -f .check/exit-code ]]; then
  exit "$(cat .check/exit-code)"
fi
SCRIPT
  chmod +x scripts/check-rust-ci.sh
}

setup_repo() {
  local scenario="$1"
  local expected_tracked="$2"
  local absent_paths="${3:-}"
  local exit_code="${4:-}"
  local signal_int="${5:-0}"

  SCENARIO_ROOT="$(mktemp -d "$TMP_ROOT/${scenario}.XXXXXX")"
  REPO_DIR="$SCENARIO_ROOT/repo"
  SNAPSHOT_DIR="$SCENARIO_ROOT/snapshots"
  mkdir -p "$REPO_DIR" "$SNAPSHOT_DIR"

  cd "$REPO_DIR"
  git init -q
  git config user.email "codex@example.invalid"
  git config user.name "Codex Test"

  mkdir -p .githooks .check
  cp "$HOOK_SOURCE" .githooks/pre-push
  chmod +x .githooks/pre-push
  write_fake_check_script

  printf "%s\n" "base" > tracked.txt
  printf "%s\n" "$expected_tracked" > .check/expected-tracked

  if [[ -n "$absent_paths" ]]; then
    printf "%s\n" "$absent_paths" > .check/absent-paths
  fi

  if [[ -n "$exit_code" ]]; then
    printf "%s\n" "$exit_code" > .check/exit-code
  fi

  if [[ "$signal_int" == "1" ]]; then
    : > .check/signal-int
  fi

  git add .githooks/pre-push scripts/check-rust-ci.sh .check tracked.txt
  git commit -q -m "initial"
}

snapshot_state() {
  local output_dir="$1"
  mkdir -p "$output_dir"
  git status --short --untracked-files=all > "$output_dir/status"
  git diff --binary > "$output_dir/diff"
  git diff --cached --binary > "$output_dir/diff-cached"
}

assert_file_equal() {
  local expected="$1"
  local actual="$2"
  local label="$3"

  if ! diff -u "$expected" "$actual"; then
    fail "$label changed after hook returned"
  fi
}

assert_state_restored() {
  snapshot_state "$SNAPSHOT_DIR/after"
  assert_file_equal "$SNAPSHOT_DIR/before/status" "$SNAPSHOT_DIR/after/status" "git status"
  assert_file_equal "$SNAPSHOT_DIR/before/diff" "$SNAPSHOT_DIR/after/diff" "git diff"
  assert_file_equal "$SNAPSHOT_DIR/before/diff-cached" "$SNAPSHOT_DIR/after/diff-cached" "git diff --cached"
}

assert_stash_empty() {
  local stash_list
  stash_list="$(git stash list)"

  if [[ -n "$stash_list" ]]; then
    echo "$stash_list" >&2
    fail "git stash list was not empty after hook returned"
  fi
}

run_hook_and_assert() {
  local scenario="$1"
  local expected_status="$2"
  local expected_check_ran="${3:-1}"
  local output_file="$SCENARIO_ROOT/hook-output.txt"
  local check_marker="$SCENARIO_ROOT/check-ran"
  local status

  snapshot_state "$SNAPSHOT_DIR/before"

  set +e
  FAKE_RUST_CHECK_MARKER="$check_marker" bash .githooks/pre-push origin /tmp/pre-push-test.git > "$output_file" 2>&1
  status=$?
  set -e

  if [[ "$status" -ne "$expected_status" ]]; then
    cat "$output_file" >&2
    fail "$scenario expected exit $expected_status, got $status"
  fi

  if [[ "$expected_check_ran" == "1" && ! -f "$check_marker" ]]; then
    cat "$output_file" >&2
    fail "$scenario expected the fake Rust check to run"
  fi

  if [[ "$expected_check_ran" == "0" && -f "$check_marker" ]]; then
    cat "$output_file" >&2
    fail "$scenario expected the fake Rust check not to run"
  fi

  assert_state_restored
  assert_stash_empty
  echo "[test-pre-push] PASS: $scenario"
}

scenario_clean_tree() {
  setup_repo "clean-tree" "base"
  run_hook_and_assert "clean tree" 0
}

scenario_staged_only() {
  setup_repo "staged-only" "staged"
  printf "%s\n" "staged" > tracked.txt
  git add tracked.txt
  run_hook_and_assert "staged-only changes" 0
}

scenario_unstaged_only() {
  setup_repo "unstaged-only" "base"
  printf "%s\n" "unstaged" > tracked.txt
  run_hook_and_assert "unstaged-only changes" 0
}

scenario_untracked_present() {
  setup_repo "untracked-present" "base" "untracked.txt"
  printf "%s\n" "untracked" > untracked.txt
  run_hook_and_assert "untracked file present" 0
}

scenario_staged_and_unstaged() {
  setup_repo "staged-and-unstaged" "staged"
  printf "%s\n" "staged" > tracked.txt
  git add tracked.txt
  printf "%s\n" "unstaged" > tracked.txt
  run_hook_and_assert "both staged and unstaged changes" 0
}

scenario_sigint_during_check() {
  setup_repo "sigint-during-check" "base" "" "" "1"
  printf "%s\n" "unstaged" > tracked.txt
  run_hook_and_assert "SIGINT during cargo" 130
}

scenario_check_failure() {
  setup_repo "check-failure" "base" "" "42"
  printf "%s\n" "unstaged" > tracked.txt
  run_hook_and_assert "cargo failure" 42
}

assert_output_contains() {
  local expected="$1"
  local output_file="$SCENARIO_ROOT/hook-output.txt"
  local label="$2"

  if ! grep -Fq "$expected" "$output_file"; then
    cat "$output_file" >&2
    fail "$label output did not contain: $expected"
  fi
}

scenario_rust_preflight_override_valid() {
  setup_repo "rust-preflight-override-valid" "base"
  RUST_PREFLIGHT_OVERRIDE="docs-only" run_hook_and_assert "RUST_PREFLIGHT_OVERRIDE valid reason" 0 0
  assert_output_contains "[pre-push] RUST_PREFLIGHT_OVERRIDE set; skipping Rust CI preflight. Reason: docs-only" "RUST_PREFLIGHT_OVERRIDE valid reason"
}

scenario_skip_rust_checks_rejected() {
  setup_repo "skip-rust-checks-rejected" "base"
  SKIP_RUST_CHECKS=1 run_hook_and_assert "SKIP_RUST_CHECKS rejection" 1 0
  assert_output_contains "[pre-push] SKIP_RUST_CHECKS=1 is no longer supported; use RUST_PREFLIGHT_OVERRIDE='<reason>'." "SKIP_RUST_CHECKS rejection"
}

scenario_rust_preflight_override_boolean_rejected() {
  local boolean_value

  for boolean_value in 1 true TRUE yes YES; do
    setup_repo "rust-preflight-override-boolean-rejected-$boolean_value" "base"
    RUST_PREFLIGHT_OVERRIDE="$boolean_value" run_hook_and_assert "RUST_PREFLIGHT_OVERRIDE boolean rejection ($boolean_value)" 1 0
    assert_output_contains "[pre-push] RUST_PREFLIGHT_OVERRIDE must be a reason, not a boolean." "RUST_PREFLIGHT_OVERRIDE boolean rejection ($boolean_value)"
  done
}

scenario_rust_preflight_override_empty_runs_check() {
  setup_repo "rust-preflight-override-empty-runs-check" "base"
  RUST_PREFLIGHT_OVERRIDE="" run_hook_and_assert "empty RUST_PREFLIGHT_OVERRIDE runs checks" 0 1
}

scenario_clean_tree
scenario_staged_only
scenario_unstaged_only
scenario_untracked_present
scenario_staged_and_unstaged
scenario_sigint_during_check
scenario_check_failure
scenario_rust_preflight_override_valid
scenario_skip_rust_checks_rejected
scenario_rust_preflight_override_boolean_rejected
scenario_rust_preflight_override_empty_runs_check

echo "[test-pre-push] All scenarios passed."
