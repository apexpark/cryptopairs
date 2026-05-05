# Proposal: Rust toolchain pin for rustfmt and clippy (R1)

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Author**: codex (remote agent), 2026-05-05.
>
> **Branch**: `codex/r1-rust-toolchain-pin-design`. Sprint base: `codex/fix-clippy-run-24549051096`.
>
> **Open follow-up**: R1 in `docs/AGENT_STATE.md` section "Cross-cutting" (severity medium).

---

## 1. Problem

The sprint base recently failed GitHub Actions on a clippy lint that the
operator Mac did not emit locally. The concrete incident was commit
`a82e8f0`:

- `clippy::unnecessary_sort_by` failed CI's Rust job on the sprint base.
- The operator Mac's older clippy passed locally.
- The fix mechanically rewrote two descending sorts from `sort_by(...)` to
  `sort_by_key(|right| std::cmp::Reverse(...))` in:
  - `services/execution-service/src/main.rs`
  - `services/strategy-service/src/main.rs`

The repository currently has no `rust-toolchain.toml` or `rust-toolchain`
file. `ci.yml` uses `dtolnay/rust-toolchain@stable` with `rustfmt` and
`clippy`, while the operator Mac uses whatever Rust/clippy is installed
locally. That leaves rustfmt and clippy as moving, environment-dependent
inputs. For a safety-oriented trading system, the Rust preflight should be
deterministic: the same commit should see the same formatter, lint set, and
test compiler locally and in CI.

This proposal weighs channel-pinning choices for a follow-up implementation
PR. It is markdown-only per playbook section 5: no code, no `Cargo.toml`, no
CI edit, and no hook edit in this PR.

---

## 2. Constraints

The implementation should:

1. Make `cargo fmt`, `cargo clippy`, and `cargo test` use the same toolchain
   on the operator Mac and in GitHub Actions.
2. Keep `scripts/check-rust-ci.sh` as the canonical Rust gate. It currently
   just invokes cargo/rustfmt/clippy; those tools already respect rustup
   directory toolchain files.
3. Avoid new dependencies and avoid `Cargo.toml` / `Cargo.lock` churn.
4. Preserve playbook section 3b: remote agents do not install cargo and
   delegate cargo-dependent checks to the local agent plus CI.
5. Be explicit about the cost of future toolchain bumps.

External behavior confirmed from primary sources:

- Rustup supports `rust-toolchain.toml` with `[toolchain]`, `channel`,
  `components`, and `profile` fields, and `channel` accepts either
  `stable`, a major/minor version such as `1.95`, a full version such as
  `1.95.0`, or a dated nightly such as `nightly-2020-07-10`.
- Rustup chooses toolchains by override precedence, with
  `rust-toolchain.toml` ahead of the default toolchain.
- Rustup 1.28.1 restored automatic installation of the active toolchain by
  default, with opt-out via `RUSTUP_AUTO_INSTALL=0`.
- `dtolnay/rust-toolchain` selects an installed toolchain from the action
  revision or its `toolchain` input, and can install components such as
  `clippy` and `rustfmt`.

---

## 3. Options

### Option A - Pin a specific patch version, e.g. `1.95.0`

Repository file:

```toml
[toolchain]
channel = "1.95.0"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

**Trade-offs**

| Dimension | Result |
|---|---|
| Reproducibility | Highest. Every rustup-managed environment resolves the same compiler, rustfmt, and clippy version until the file changes. |
| Maintenance burden | Manual bumps. A future Rust release, patch release, or clippy false-positive fix requires an explicit PR. |
| Clippy-lint volatility | Lowest between bumps. New lints cannot appear just because `stable` moved. |
| Contributor onboarding | First cargo command may download `1.95.0` plus `rustfmt` and `clippy`. After that, no extra workflow. |
| CI compatibility | Compatible with existing cargo steps. `dtolnay/rust-toolchain@stable` may redundantly install current stable first, but the cargo/rustfmt/clippy proxies should select `rust-toolchain.toml` afterward. |
| Operator Mac autoinstall | With rustup auto-install enabled, the first cargo/rustfmt/clippy command in the repo installs `1.95.0` if missing. With `RUSTUP_AUTO_INSTALL=0` or an affected rustup version, the command fails closed and the operator runs `rustup toolchain install`. |

**Pros**

- Directly addresses the `a82e8f0` failure class: local clippy and CI clippy
  become the same clippy.
- Makes formatter drift visible as a deliberate bump PR, not a surprise
  during unrelated work.
- Does not require any `Cargo.toml` dependency or lockfile change.
- Fits the repo's safety posture: toolchain movement is reviewed, auditable,
  and reversible.

**Cons**

- Manual upkeep. If Rust `1.95.1` ships with a security or tooling fix, the
  repo stays on `1.95.0` until someone bumps it.
- Contributors pay a one-time toolchain download when the pin changes.
- Existing CI action line is a bit semantically odd: `@stable` installs
  stable, while the toolchain file pins the cargo commands. This should be
  accepted only if the first implementation CI run proves the effective cargo
  toolchain is the pinned one.

### Option B - Pin a minor channel, e.g. `1.95`

Repository file:

```toml
[toolchain]
channel = "1.95"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

**Trade-offs**

| Dimension | Result |
|---|---|
| Reproducibility | Medium. The repo stays on the 1.95 release line, but patch releases can change the effective toolchain. |
| Maintenance burden | Lower than Option A for patch releases; still requires a PR to move to `1.96`. |
| Clippy-lint volatility | Lower than `stable`, higher than `1.95.0`. Patch releases can still carry clippy changes or false-positive fixes. |
| Contributor onboarding | Similar to Option A. First use may install the latest available 1.95 patch. |
| CI compatibility | Same as Option A. Cargo/rustfmt/clippy should select the file; action-level stable install may be redundant later. |
| Operator Mac autoinstall | When a new `1.95.x` exists, rustup may install or update to that patch on first use. If auto-install is disabled, the operator runs `rustup toolchain install`. |

**Pros**

- Keeps the repo on a release line while accepting patch fixes
  semi-automatically.
- Less manual burden than exact patch pinning.
- Still avoids drift to a new minor release with a broader compiler/lint set.

**Cons**

- Does not fully close the reproducibility gap. A patch release can change
  clippy behavior between two runs of the same commit.
- Audit trail is weaker than Option A because the commit did not change while
  the exact installed patch may have.
- The R1 incident is specifically about a lint-version mismatch; allowing any
  floating patch leaves a smaller version of that same problem.

### Option C - Pin `stable`

Repository file:

```toml
[toolchain]
channel = "stable"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

**Trade-offs**

| Dimension | Result |
|---|---|
| Reproducibility | Low. `stable` moves on the Rust release train. |
| Maintenance burden | Lowest. No routine bump PRs. |
| Clippy-lint volatility | Highest. New stable releases can add or strengthen lints without any repo change. |
| Contributor onboarding | Easiest if contributors already track stable. |
| CI compatibility | Matches the existing `dtolnay/rust-toolchain@stable` action most directly. |
| Operator Mac autoinstall | Rustup updates or installs stable according to the operator's local rustup state. An older already-installed stable can still differ until updated. |

**Pros**

- Documents intent to use stable Rust.
- Low friction for contributors.
- No routine maintenance PRs.

**Cons**

- Does not solve R1. It declares a channel but does not lock the CI/operator
  version gap that produced `a82e8f0`.
- Same commit can lint differently before and after a Rust stable release.
- "Stable" is a policy statement, not an audit anchor.

### Option D - MSRV-style minimum plus CI current stable

This would document a minimum supported Rust version, usually in docs or
`Cargo.toml` via `rust-version`, while CI continues to test current stable.

**Trade-offs**

| Dimension | Result |
|---|---|
| Reproducibility | Low for rustfmt/clippy. MSRV controls compile compatibility, not lint/format determinism. |
| Maintenance burden | Medium. MSRV changes need review, but current-stable CI still moves. |
| Clippy-lint volatility | High unless clippy is separately pinned. |
| Contributor onboarding | Familiar for Rust libraries; less useful for this app workspace. |
| CI compatibility | Compatible with current CI, but it does not change current CI drift. |
| Operator Mac autoinstall | Depends on whatever channel the operator runs; no repo-level pin forces convergence. |

**Pros**

- Useful if the project wants to promise a minimum compiler for downstream
  crates.
- Can be combined with a pinned toolchain later.

**Cons**

- It does not pin rustfmt or clippy.
- This repository is an application workspace, not a public library with an
  MSRV promise as the primary consumer contract.
- It does not address the `clippy::unnecessary_sort_by` incident.

### Option E - Dated nightly, e.g. `nightly-2026-04-16`

Repository file:

```toml
[toolchain]
channel = "nightly-2026-04-16"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

**Trade-offs**

| Dimension | Result |
|---|---|
| Reproducibility | High for the date. |
| Maintenance burden | High. Nightly component availability and future bumps need care. |
| Clippy-lint volatility | Low between date bumps, but nightly lint behavior is less conservative. |
| Contributor onboarding | Higher friction: larger downloads, more surprise from nightly-only tool behavior. |
| CI compatibility | Requires stronger CI scrutiny because nightly component availability can vary by date. |
| Operator Mac autoinstall | First use installs that nightly date if available; failures are more likely than stable patch pins if a component is unavailable for a target/date. |

**Pros**

- Useful when a project needs an unstable compiler feature or nightly-only
  rustfmt behavior.

**Cons**

- This repo has no verified need for nightly in R1.
- It increases, rather than reduces, toolchain risk for safety-critical
  preflight.
- Clippy on nightly is not the right stability target for CI gates that fail
  builds with `-D warnings`.

---

## 4. Recommendation

Choose **Option A: exact patch pin** with `channel = "1.95.0"`,
`components = ["rustfmt", "clippy"]`, and `profile = "minimal"`.

Rationale:

1. R1 is about eliminating a known clippy-version split, not merely
   documenting Rust-channel intent.
2. Exact patch pinning makes the toolchain an auditable repository input.
   Any future lint churn enters through an intentional bump PR.
3. The manual bump burden is acceptable because Rust toolchain changes can
   break a `-D warnings` gate even when production logic is untouched.
4. `profile = "minimal"` keeps onboarding/download cost lower while
   explicitly adding the two components this repo's gate needs: `rustfmt` and
   `clippy`.
5. The pin is easy to revert or advance if CI/local verification reveals a
   toolchain-specific issue.

Option B is defensible if the operator prefers automatic patch uptake over
byte-for-byte reproducibility, but it leaves residual clippy drift. Option C
is rejected because it preserves the core failure mode. Options D and E solve
different problems.

---

## 5. Follow-up implementation PR

The implementation PR after operator approval should add exactly this file at
repo root:

```toml
[toolchain]
channel = "1.95.0"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

Required files:

- `rust-toolchain.toml` - new repo-root toolchain source of truth.
- `CHANGELOG.md` - one `Unreleased` operator-tooling entry.
- `docs/AGENT_STATE.md` - mark R1 resolved and record the implementation
  commit/PR.

Expected files not changed:

- `Cargo.toml` and `Cargo.lock` - no dependency or crate metadata change.
- `.githooks/pre-push` - the hook only calls `scripts/check-rust-ci.sh`; cargo
  resolves the repo toolchain through rustup.
- `scripts/check-rust-ci.sh` - no command change required.
- `.github/workflows/ci.yml` - no required change for the first
  implementation slice.

### CI detail

The current `rust` job does this:

```yaml
- name: Setup Rust
  uses: dtolnay/rust-toolchain@stable
  with:
    components: rustfmt, clippy
```

Then it runs `cargo fmt`, `cargo clippy`, and `cargo test`.

The recommended first implementation leaves this unchanged. The cargo,
rustfmt, and clippy commands should select the repo-root `rust-toolchain.toml`
via rustup's override precedence. If the first implementation CI run shows
that the action-level stable install prevents the pinned toolchain from being
used, the minimal follow-up CI change is:

```yaml
- name: Setup Rust
  uses: dtolnay/rust-toolchain@master
  with:
    toolchain: 1.95.0
    components: rustfmt, clippy
```

Do not make that CI change preemptively in Slice A; prove whether the simpler
repo-root file is enough first. If a CI change is needed, it should stay in
the implementation PR and be called out explicitly.

### Pre-push detail

`.githooks/pre-push` invokes `scripts/check-rust-ci.sh`, and the script invokes
cargo/rustfmt/clippy without `+toolchain` overrides. That is the desired shape:
rustup will resolve `rust-toolchain.toml` from the repository root and run the
pinned toolchain. No hook change is required for R1.

### Operator Mac detail

When the operator first runs `cargo`, `cargo fmt`, `cargo clippy`, or the
pre-push hook after the pin lands:

- If the pinned toolchain is already installed, the command proceeds normally.
- If it is missing and rustup auto-install is enabled, rustup installs the
  pinned toolchain and requested components.
- If auto-install is disabled (`RUSTUP_AUTO_INSTALL=0`) or the installed rustup
  refuses automatic installation, the command fails closed. The recovery is:

```bash
rustup toolchain install
```

Run from the repo root, that command installs the active toolchain described
by `rust-toolchain.toml`.

---

## 6. Acceptance criteria for the implementation PR

The implementation PR MUST:

1. Add only `rust-toolchain.toml`, `CHANGELOG.md`, and `docs/AGENT_STATE.md`
   unless CI proves a `.github/workflows/ci.yml` adjustment is necessary.
2. Keep `Cargo.toml` and `Cargo.lock` unchanged.
3. Show effective toolchain identity in verification evidence:
   - `rustup show active-toolchain`
   - `rustc --version`
   - `cargo fmt --all -- --check`
   - `cargo clippy --workspace --all-targets -- -D warnings`
   - `cargo test --workspace`
4. Pass local-agent Rust verification via `scripts/check-rust-ci.sh` and
   GitHub Actions Rust job at the implementation head SHA.
5. Confirm that the pre-push hook still calls the same script and requires no
   R1-specific hook change.
6. Update `docs/AGENT_STATE.md` with the R1 resolved delta and keep the
   R2/R2-impl rows untouched unless their own PR lands first.

Remote agents still do not run cargo or install the toolchain; they report
the Rust check status as delegated per playbook section 3b.

---

## 7. Effort estimate

| Component | Estimate |
|---|---:|
| `rust-toolchain.toml` | 4 LOC |
| `CHANGELOG.md` entry | 1-3 LOC |
| `docs/AGENT_STATE.md` R1 resolution delta | 1-4 LOC |
| Optional CI logging or action tweak if first run proves necessary | 3-8 LOC |
| Verification collection | 10-20 minutes local-agent/CI wall time |

Expected implementation PR size: tiny, roughly 6-15 changed lines if CI does
not need adjustment.

---

## 8. Out of scope

- Changing `Cargo.toml`, `Cargo.lock`, crate MSRV, or dependency policy.
- Changing `.githooks/pre-push`; R2-impl owns staged-vs-working-tree hook
  semantics.
- Suppressing or allowing individual clippy lints. R1 pins the lint engine;
  it does not decide lint policy.
- Moving CI away from `-D warnings`.
- Host-runtime verification. This is tooling only and has no SSH component.

---

## 9. References

- `docs/AGENT_STATE.md` R1 row - toolchain pin follow-up and incident summary.
- `git show a82e8f0` - exact `clippy::unnecessary_sort_by` remediation.
- `.github/workflows/ci.yml` - current `dtolnay/rust-toolchain@stable` setup.
- `.githooks/pre-push` and `scripts/check-rust-ci.sh` - local Rust gate.
- Rustup toolchain specification:
  <https://rust-lang.github.io/rustup/concepts/toolchains.html>
- Rustup override and `rust-toolchain.toml` documentation:
  <https://rust-lang.github.io/rustup/overrides.html#the-toolchain-file>
- Rustup changelog, 1.28.1 auto-install restoration:
  <https://github.com/rust-lang/rustup/blob/main/CHANGELOG.md#1281---2025-03-05>
- `dtolnay/rust-toolchain` README:
  <https://github.com/dtolnay/rust-toolchain>
- Rust 1.95.0 release announcement:
  <https://blog.rust-lang.org/2026/04/16/Rust-1.95.0/>
