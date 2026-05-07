# Proposal: Pin Rust toolchain via rust-toolchain.toml (R1)

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Author**: claude (remote agent), 2026-05-07.
>
> **Branch**: `claude/r1-rust-toolchain-pin-design`. Sprint base: `codex/fix-clippy-run-24549051096`.
>
> **Open follow-up**: R1 in `docs/AGENT_STATE.md` §"Cross-cutting" (severity **medium**).

---

## 1. Problem

`rustfmt` and `clippy` are versioned with the Rust toolchain. When the
operator's Mac, GitHub Actions CI, and the remote-agent environments
(Codex Cloud, Claude Code) each pick up whatever toolchain their host
happens to have installed, the same workspace yields different
fmt/clippy verdicts in different places. The operator's pre-push hook
runs cargo against the operator's locally-installed toolchain; CI runs
cargo against `dtolnay/rust-toolchain@stable` (whatever "stable" was at
the time CI ran); a remote agent's review run, when one happens, runs
against yet another version.

`.github/workflows/ci.yml` currently says:

```yaml
- name: Setup Rust
  uses: dtolnay/rust-toolchain@stable
  with:
    components: rustfmt, clippy
```

There is no `rust-toolchain` or `rust-toolchain.toml` file at the repo
root today; the workspace `Cargo.toml` declares `edition = "2021"` but
no `rust-version` MSRV. The operator's `~/.cargo` and `~/.rustup` state
is not version-anchored to anything in this repository.

### The a82e8f0 incident as the canonical example

Commit `a82e8f0` ("chore(execution,strategy): silence
`clippy::unnecessary_sort_by` on sprint base") records the symptom
directly in its message:

> Two mechanical clippy::unnecessary_sort_by violations were failing
> GitHub Actions' rust job on the sprint base while the operator's
> local cargo clippy passed. Lint URL points to rust-clippy/rust-1.95.0,
> which suggests the operator's Mac is on a pre-1.95 clippy that
> doesn't enforce this lint. CI ran on stable which does.

This is the exact failure mode this proposal addresses: a lint that
exists in clippy ≥ 1.95.0 but not in the operator's local clippy,
causing the pre-push hook to report green while CI reports red. The
operator merged `a82e8f0` to silence the lint on sprint base, but
nothing about that fix prevents the next clippy release from doing
the same thing again.

### Why R2-impl does not close this class

R2-impl (`d171035`, PR #164) modifies `.githooks/pre-push` to
autostash unstaged tracked changes and untracked files before
invoking `scripts/check-rust-ci.sh`, so the hook now tests the
**bytes that will be pushed** instead of the dirty working tree.
That closes the most common manifestation of operator/CI divergence
— the dirty-drag-along bug class — but it does **not** close the
underlying environment-divergence question.

Specifically, R2-impl makes the hook test `(staged tree) × (operator
toolchain)`. CI tests `(committed tree) × (CI's @stable toolchain)`.
If `(operator toolchain) ≠ (CI's @stable toolchain)`, the verdicts
can still diverge on a clean staged tree. The a82e8f0 incident sits
in that residual gap; it would have surfaced even with R2-impl in
place because the operator's clippy lacked the `unnecessary_sort_by`
lint entirely.

R1 closes the residual gap by pinning the toolchain itself, so the
two factors degenerate to one: every environment runs the same
fmt/clippy version against the same staged tree.

---

## 2. Constraints and what "good" looks like

The fix must satisfy all of:

1. **Operator Mac, GitHub Actions CI, and remote-agent environments
   (Codex Cloud, Claude Code) all use the same `rustfmt` + `clippy`
   version when they run cargo against this repo.** Specifically, the
   operator's pre-push hook and CI's clippy step must agree
   bit-for-bit on whether a given staged tree is clippy-clean.

2. **`dtolnay/rust-toolchain@stable` in `.github/workflows/ci.yml`
   continues to work without modification.** The action honors
   `rust-toolchain.toml` when present (it will install the channel
   listed there rather than the action ref's `@stable` default), so
   no workflow edit is required.

3. **Contributor onboarding cost stays low.** Cloning the repo and
   running cargo "just works": rustup auto-installs missing
   toolchains when a `rust-toolchain.toml` is present. No manual
   `rustup install <version>` step.

4. **Updating Rust version is operator-driven, predictable, and does
   not require coordinating across multiple machines.** The bump is
   a single-line edit to `rust-toolchain.toml`; once committed, every
   environment picks it up on the next cargo invocation.

5. **Remote-agent flow is unchanged.** Per playbook §3b
   (cargo-blocked workaround at `a2fa027`), Codex and Claude cannot
   install cargo and do not run cargo locally. The pin is therefore
   irrelevant in their tree but must not break their hydration
   sequence — i.e. the file must not introduce a syntax that breaks
   the playbook §1 self-preflight or any markdown-level read.

6. **The pre-push hook (`.githooks/pre-push`) and its companion test
   script (`scripts/test-pre-push.sh`) keep working without edits.**
   The hook calls `scripts/check-rust-ci.sh`, which calls `cargo`,
   which respects `rust-toolchain.toml`. The R2-impl test script
   substitutes a fake `check-rust-ci.sh` in temporary git repos and
   never invokes real cargo, so a toolchain pin in the source repo
   does not affect those tests.

---

## 3. Options

For each option, the rubric is:

- **Maintenance burden** — how often does the operator have to update?
- **Clippy lint volatility** — what happens when a new lint lands?
- **Contributor onboarding friction** — does fresh-clone + cargo "just
  work" or does the contributor have to `rustup install`?
- **Compatibility with `dtolnay/rust-toolchain@stable`** — does CI keep
  working unmodified?
- **rustup autoinstall behavior on operator Mac** — what does the
  operator's macOS rustup do when `rust-toolchain.toml` channel
  changes?
- **Effect on `.githooks/pre-push`** — does the hook need any change?

### Option A — Pin to a specific patch version (e.g. `channel = "1.95.0"`)

```
[toolchain]
channel = "1.95.0"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

**Maintenance burden.** High. Every time the operator wants a new
Rust release (security fix in compiler, perf improvement, new lint
they want to opt into, new edition), they have to manually edit the
file and commit. There is no auto-bump.

**Clippy lint volatility.** Lowest. `cargo clippy` against the same
staged tree always produces the same verdict everywhere (operator,
CI, remote agent if it ever runs cargo) because the clippy version
is byte-identical. New lints from later Rust releases cannot
silently break CI; the operator opts in to each version bump
deliberately.

**Contributor onboarding friction.** Lowest practical: rustup auto-
installs `1.95.0` on first cargo invocation in the repo if it is
missing locally. Cost: one extra ~150 MB toolchain download on first
clone. Subsequent clones share the global `~/.rustup/toolchains/`
cache.

**Compatibility with `dtolnay/rust-toolchain@stable`.** Confirmed
compatible. The action documents that it honors `rust-toolchain.toml`
when present and installs the channel listed there. The `@stable`
suffix on the action is the action's own git ref, not a Rust
channel selector. CI behavior changes: the installed toolchain is
1.95.0 instead of whatever-stable-is-this-week. No `ci.yml` edit is
required.

**rustup autoinstall behavior on operator Mac.** When the operator
pulls a commit that changes `rust-toolchain.toml` channel from
"1.95.0" to (say) "1.96.0", the next cargo invocation triggers
rustup to download 1.96.0 transparently, with progress output. No
operator action required for the bump itself (one-time download,
~minutes on first install of any given version).

**Effect on `.githooks/pre-push`.** None. The hook calls
`scripts/check-rust-ci.sh` which calls `cargo`. cargo reads
`rust-toolchain.toml` automatically. R2-impl's `scripts/test-pre-push.sh`
operates in temp git repos with a fake `scripts/check-rust-ci.sh`
that never invokes real cargo — those tests are not affected by the
real repo's toolchain pin.

### Option B — Pin to a minor channel (e.g. `channel = "1.95"`)

```
[toolchain]
channel = "1.95"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

**Maintenance burden.** Low. The operator chooses when to advance
the minor (1.95 → 1.96 → ...), but patch updates within a minor
(1.95.0 → 1.95.1 → 1.95.2) flow in automatically as upstream ships
them. Patch releases are usually small bug fixes and almost never
add new clippy lints, so the implicit update is low-risk.

**Clippy lint volatility.** Low — but not zero. New lints typically
land in minor releases (1.96 → 1.97), not patch releases. Pinning
to a minor effectively says "the operator approves this set of
clippy lints for the duration of this minor; bump me to choose new
ones." Within a minor, `cargo clippy` against the same staged tree
should produce the same verdict everywhere. A small risk remains:
a clippy bug fix in a patch release could change a lint's output
from a false positive to a true positive (or vice versa). In
practice, those are rare and usually appreciated.

**Contributor onboarding friction.** Same as Option A. rustup
auto-installs the latest 1.95.x patch on first cargo invocation if
no 1.95.x is present locally.

**Compatibility with `dtolnay/rust-toolchain@stable`.** Confirmed
compatible (same mechanism as Option A — action reads the file).
Subtle behavior: CI runners typically refresh toolchain caches per
job, so they pick up the latest 1.95.x patch. Operator Mac does
the same when their local 1.95.x ages out (next `rustup update`
inside the 1.95 channel). The two can drift by one patch in the
window between an upstream patch release and the next `rustup
update` on either side. In practice the drift window is days, not
weeks, and patch-level clippy differences are exceedingly rare.

**rustup autoinstall behavior on operator Mac.** Same as Option A
on a channel bump. No operator action on patch updates within the
channel — they happen transparently on `rustup update`.

**Effect on `.githooks/pre-push`.** None (same reasoning as
Option A).

### Option C — Pin to "stable"

```
[toolchain]
channel = "stable"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

**Maintenance burden.** Zero from the operator's side. Every
machine just rolls forward with upstream stable.

**Clippy lint volatility.** Highest. This is essentially the status
quo dressed up as a pin: every time clippy releases a new lint,
some environment somewhere will see it before another does. The
a82e8f0 class of incident is **not prevented** by this option —
the operator's Mac stable could still lag CI's stable by days or
weeks depending on `rustup update` cadence on each side. The pin
documents intent ("we track latest stable") but does not lock.

**Contributor onboarding friction.** Same as A/B. rustup ensures a
stable toolchain is present.

**Compatibility with `dtolnay/rust-toolchain@stable`.** Trivially
compatible — both sides agree on "stable", which is what CI does
today.

**rustup autoinstall behavior on operator Mac.** Identical to
today. `rustup update stable` is the only operator action, on
whatever cadence they choose.

**Effect on `.githooks/pre-push`.** None.

### Option D — Pin a specific patch with an explicit MSRV

```
[toolchain]
channel = "1.95.0"
components = ["rustfmt", "clippy"]
profile = "minimal"
```

Combined with `rust-version = "1.95"` added to `[workspace.package]`
in `Cargo.toml` to declare the workspace MSRV alongside the
toolchain pin.

**Maintenance burden.** Same as Option A plus a small additional
edit on each minor bump.

**Clippy lint volatility.** Same as Option A.

**Contributor onboarding friction.** Same as Option A. The MSRV
field is informational for downstream consumers (none today; this
is not a published library workspace) and would surface a clearer
error if a contributor tried to build with a too-old toolchain.

**Compatibility with `dtolnay/rust-toolchain@stable`.** Same as
Option A.

**rustup autoinstall behavior on operator Mac.** Same as Option A.

**Effect on `.githooks/pre-push`.** None.

**Why call this out separately from Option A.** It is essentially
Option A with a one-line `Cargo.toml` annotation. The annotation is
zero-risk and zero-cost; the question is whether the workspace
benefits from declaring an MSRV today (it is not published, has no
downstream consumers, and is not a library), or whether the
annotation is unnecessary noise. This proposal treats Option D as
an **additive variant** of Option A rather than a separate path.

### Options considered and rejected without full evaluation

- **Nightly with date pin** (`channel = "nightly-2026-05-01"`).
  Rejected. The workspace does not use any nightly features today
  (a quick `grep -r '#!\[feature' crates services` would catch
  any). Nightly buys nothing and pays in instability.
- **MSRV-style minimum** (allow any toolchain ≥ 1.95). Rejected.
  This is what `rust-version` in `Cargo.toml` already documents,
  but it does not pin — every environment can still pick a
  different version above the floor. Does not solve the problem.
- **Multi-channel matrix** (CI runs N channels, operator pins one).
  Rejected. Cost is N× CI minutes for no benefit on a workspace
  that has no MSRV-compatibility obligations.

---

## 4. Recommendation: Option B (`channel = "1.95"`), additive Option D

**Land Option B first.** The operator's Mac pins to the same minor
channel as CI; patch updates flow in transparently; the operator
deliberately drives minor bumps. This catches the a82e8f0 class
(new-lint-in-1.95.0 surfacing on CI but not the operator's pre-1.95
local clippy) because both environments are at 1.95.x going
forward. It avoids Option A's per-patch maintenance churn, which
adds bump commits without adding safety against the actual incident
class.

If, in practice, patch-level drift between operator Mac and CI
within the same minor produces incidents — i.e. clippy patch-release
behavior differs across `1.95.0` and `1.95.2`, and the difference
matters — escalate to Option A (specific patch). The operator can
flip the channel string and commit. **Do not pre-build Option A.**
The most likely outcome is that minor pinning is sufficient and
Option A's maintenance tax is never paid for.

Option D's `rust-version = "1.95"` Cargo.toml annotation is
**recommended as additive** — it is one line, costs nothing, and
gives a clearer error message to any future contributor whose
toolchain somehow falls below the floor (e.g. a CI matrix
expansion, a downstream fork). The operator may iterate on
including or excluding it in the §10 binding decisions.

Option C is rejected because it does not lock; it is the status
quo with a `rust-toolchain.toml` file added for ceremony. The R1
row exists specifically because the status quo failed at a82e8f0.

### Why not Option A as the first move

Option A is correct under one specific failure mode: a clippy
patch release within a minor changes lint behavior on the same
staged tree. The historical evidence in this repo (one incident
in 24 hours, at the minor boundary 1.95.0) does not support that
patch-level drift is the dominant problem. Pinning to the minor
gets us the same a82e8f0-class protection at lower maintenance
cost. If patch drift turns out to matter, the diff to Option A is
one character (`"1.95"` → `"1.95.0"`) plus a follow-up commit
selecting the actual patch.

---

## 5. Acceptance criteria for the implementation PR

The implementation PR (a separate PR after this proposal merges)
MUST:

### 5.1 Files changed

- **`rust-toolchain.toml`** (new file at repo root). Exact contents
  per the §10 binding decision on channel string. The minimal
  recommended shape is:

  ```toml
  [toolchain]
  channel = "1.95"
  components = ["rustfmt", "clippy"]
  profile = "minimal"
  ```

  `profile = "minimal"` keeps the rustup install footprint small;
  `components` adds rustfmt and clippy explicitly because the
  default minimal profile does not include them. The operator may
  iterate on the exact channel string in §10.

- **`docs/playbooks/remote-agent-bootstrap.md`** §3b — one short
  note that `rust-toolchain.toml` pins the rustfmt/clippy version
  used by `scripts/check-rust-ci.sh`, so the operator's local
  cargo and CI's cargo agree by construction.

- **`docs/14-testing-standards.md`** — one short note in the
  appropriate Rust subsection (the file currently has no
  toolchain reference) that the workspace pins via
  `rust-toolchain.toml` and that local development should use
  `rustup` to honor the pin.

- **`CHANGELOG.md`** `## Unreleased` — one-line entry under
  operator-tooling.

- **`docs/AGENT_STATE.md`** — flip R1 status to **resolved** with
  the implementation commit SHA in the §"Cross-cutting" table.
  No re-pin required unless other state moves at the same time.

### 5.2 Files NOT changed (acceptance criterion)

The implementation PR MUST verify (and state in its description)
that the following files do not require modification:

- **`.github/workflows/ci.yml`** — no edit. `dtolnay/rust-toolchain@stable`
  reads `rust-toolchain.toml` and installs the pinned channel. The
  `@stable` suffix is the action's own ref, not a Rust channel
  selector.

- **`scripts/check-rust-ci.sh`** — no edit. The script invokes
  `cargo fmt`, `cargo clippy`, `cargo test` directly; cargo
  respects `rust-toolchain.toml` automatically.

- **`.githooks/pre-push`** — no edit. The hook invokes
  `scripts/check-rust-ci.sh`. Same reasoning.

- **`scripts/test-pre-push.sh`** (R2-impl test harness) — no edit.
  The script substitutes a fake `scripts/check-rust-ci.sh` in
  temporary git repos under `mktemp -d` and never runs real cargo.
  The toolchain pin in the source repo does not affect those
  temp repos.

- **`Cargo.toml`** — no edit unless §10 selects Option D
  (additive `rust-version` field).

If any of these turn out to require a change, the implementation
PR escalates rather than silently editing them.

### 5.3 Operator local verification before merge

The implementation PR's description MUST include the result of
running, on the operator's Mac:

```bash
rustup show       # confirm 1.95.x is the active toolchain in repo dir
cargo --version   # confirm cargo binary version matches
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Expected: rustup auto-installs 1.95.x if not already present;
fmt/clippy/test all pass against the same staged tree CI is
testing. If clippy reports anything new that did not previously
fire on the operator's older toolchain, those are real and must
be fixed in the PR (not silenced) — that is exactly the class of
issue this pin is designed to surface, and burying them defeats
the purpose.

### 5.4 CI verification

GitHub Actions must run green on the implementation PR's branch.
Any new clippy lints that surface from the toolchain bump are
fixed in the same PR. The operator should expect a non-zero
chance of a small fixup commit on top of the pin commit if the
operator's previous local toolchain was significantly behind.

---

## 6. Effort estimate

| Component | LOC |
|---|---|
| `rust-toolchain.toml` (new file) | 4–6 |
| `docs/playbooks/remote-agent-bootstrap.md` §3b note | 3–5 |
| `docs/14-testing-standards.md` toolchain note | 3–5 |
| `CHANGELOG.md` entry | 1 |
| `docs/AGENT_STATE.md` R1 status flip | 1–2 |
| Optional: `Cargo.toml` `rust-version` (Option D) | 1 |
| Possible fixup: clippy lints surfaced by the bump | 0–unknown |
| **Total (excluding fixup)** | **~13–20 LOC** |

Implementation effort is small and almost entirely doc + config.
The dominant uncertainty is whether the bump surfaces new clippy
lints on existing code; if so, those are addressed in the same PR.
The historical evidence (a82e8f0 fixed two `unnecessary_sort_by`
sites with mechanical replacements) suggests new lints when they
arrive are usually mechanical to fix.

---

## 7. Preconditions

1. **Operator decides which channel to pin to** — one of options
   A/B/C/D in §3, with Option B recommended in §4. Operator may
   override the recommendation in §10.

2. **Operator confirms their Mac will accept rustup auto-install
   when the channel changes.** Typical setup; the operator's Mac
   already has rustup managing toolchains. The first cargo
   invocation after the pin lands triggers a one-time ~minutes
   download for any toolchain version not already present locally.

3. **Remote-agent environments must be able to install the pinned
   channel** — flagged for transparency but not a blocker. Per
   the cargo-blocked workaround at `a2fa027`, Codex and Claude
   cannot run cargo at all in their environments. Therefore the
   pin is irrelevant in their tree: they do not invoke cargo, do
   not need the toolchain installed, and do not check out and
   build the workspace. The pin file is read by them only as
   text (e.g. when reading the diff for review) and that is
   harmless. **This proposal confirms the pin does not break
   remote-agent flow.**

4. **No nightly-only feature usage in the workspace.** Confirmed
   by inspection: `Cargo.toml` declares `edition = "2021"` and
   the workspace builds on stable. The implementation PR should
   re-confirm with `grep -r '#!\[feature' crates services`
   yielding no Rust feature-gate attributes.

---

## 8. Incidents this proposal unblocks / prevents

The implementation PR following this proposal directly addresses
the recurrence pattern that landed `a82e8f0`:

- **`a82e8f0`** — `chore(execution,strategy): silence
  clippy::unnecessary_sort_by on sprint base`. The lint was
  introduced in clippy 1.95.0; the operator's Mac was on a pre-1.95
  clippy that did not enforce it. With Option B pinning to "1.95",
  both the operator's pre-push hook and CI would have run clippy
  1.95.x against the same staged tree and surfaced the lint at the
  same time. The fix would have landed in the original commit
  rather than a follow-up remediation.

- **Future incidents of the same class.** Any clippy lint that
  ships in a Rust release the operator's Mac has not yet pulled
  but CI has, and which fires on the workspace's existing code,
  produces this exact divergence. Pinning collapses the divergence.

- **CI reproduction for debugging.** When a future debugging
  session needs to reproduce a CI-only failure locally, the
  operator can run cargo against the pinned toolchain with
  confidence that the local result will match CI. Today, the
  reproduction step "use the same toolchain CI used" is implicit
  and easy to get wrong.

### What this proposal explicitly does NOT prevent

- **Lint changes within a patch release** under Option B (minor
  pin). Rare in practice; if they occur and matter, escalation
  path is to Option A (specific patch).
- **rustfmt edition-style changes** that ship as part of a Rust
  release. These would still apply uniformly across all
  environments (because they are version-locked), so any
  formatting change surfaces simultaneously rather than
  divergently — which is the point of the pin.
- **Cargo registry / index drift.** This is a separate concern
  governed by `Cargo.lock` and the workspace's dependency
  pinning; out of scope here.

---

## 9. Test scenarios the implementation PR MUST cover

The implementation PR's verification (in the PR description) MUST
demonstrate each of the following:

1. **Pin is effective on operator Mac.** `rustup show` from the
   repo directory lists the pinned channel as active. `cargo
   --version` reports the pinned toolchain's cargo.

2. **Fresh-clone "just works".** Demonstrated by the operator
   doing one of: (a) `git clone` into a scratch directory and
   running `cargo --version` from inside, observing rustup
   auto-install the pinned channel; or (b) confirming this is the
   expected rustup behavior and citing the rustup docs for the
   `rust-toolchain.toml` lookup, if the round-trip clone is too
   expensive to demonstrate.

3. **CI installs the pinned channel.** A CI run on the
   implementation PR's branch logs the toolchain version
   (visible in the `dtolnay/rust-toolchain` action's output and
   in the `cargo fmt` step's first lines) and matches the pin.

4. **`cargo fmt --all -- --check` passes** against the same
   staged tree on operator Mac and CI.

5. **`cargo clippy --workspace --all-targets -- -D warnings`
   passes** against the same staged tree on operator Mac and CI.
   If new lints surface from the bump, they are fixed in the same
   PR; the PR description lists each lint and its fix.

6. **`cargo test --workspace` passes** against the same staged
   tree on operator Mac and CI. The Postgres-backed integration
   harness from B6 (`STRATEGY_TEST_DATABASE_URL` gating) is
   unaffected by toolchain pinning.

7. **Pre-push hook continues to operate.** The operator runs a
   no-op `git push --dry-run` with the autostash hook installed
   and confirms the hook runs the pinned cargo. R2-impl's
   `scripts/test-pre-push.sh` continues to pass (it never
   invokes real cargo, so this is a sanity check only).

8. **Remote-agent flow is unchanged.** The playbook §1
   self-preflight produces no new failures. The remote agent's
   markdown reads of the proposal and the new toolchain file
   complete normally.

---

## 10. Open questions for operator approval

1. **Option B (`channel = "1.95"`), Option A (`channel = "1.95.0"`),
   or a different channel string entirely?** Recommendation §4 is
   B. Operator may override; the implementation PR uses the
   exact string the operator selects here.

2. **Include Option D's additive `rust-version = "1.95"` in
   `[workspace.package]` of `Cargo.toml`?** Recommendation §4 is
   yes (one line, zero risk). Operator may decline if they
   prefer to defer MSRV declaration until the workspace has a
   reason to publish.

3. **Should the implementation PR include `profile = "minimal"`
   in `rust-toolchain.toml`?** Recommendation: yes, it is the
   smallest install footprint and `components` adds rustfmt and
   clippy explicitly. Operator may prefer `profile = "default"`
   if they want extras like `rust-docs` available without a
   separate `rustup component add`.

4. **What is the operator's preferred re-pin cadence?** Not a
   blocking decision for this PR, but worth flagging: with
   Option B, the operator chooses when to bump 1.95 → 1.96. A
   loose convention ("bump on each Rust minor release at
   operator's discretion, no SLA") is sufficient given the
   workspace's lack of MSRV obligations. Operator may prefer a
   tighter cadence (every minor, on a calendar) or looser (only
   when a desired feature lands).

5. **Should the operator's Mac do a one-time `rustup default
   <pinned-version>` at the global scope, or rely on the
   per-repo pin alone?** Recommendation: rely on the per-repo
   pin. rustup's directory-aware behavior is the standard
   mechanism; setting a global default could mask the per-repo
   pin in unrelated workspaces. Operator may have a different
   preference based on their other Rust work.

---

## 11. Out of scope

- **R2 / R2-impl** — already shipped at `f87e291` (proposal) and
  `d171035` / PR #164 (implementation). R2 closes the
  staged-vs-working-tree divergence; R1 closes the
  toolchain-version divergence. Both surfaced from the same
  incident burst but are independent fixes with no shared code.

- **R3 (`SKIP_RUST_CHECKS` rotation)** — separate row in
  `AGENT_STATE.md` §"Cross-cutting", deferred until R2-impl lands.
  R1 does not interact with the escape-hatch interface.

- **Pinning Python or Node toolchains.** The CI `python` job uses
  `actions/setup-python@v5` with `python-version: "3.11"`,
  effectively a minor pin. Frontend Node version is governed by
  `apps/web/package.json` and `package-lock.json`. Both are
  separate concerns with their own version-drift surfaces; this
  proposal addresses Rust only.

- **Pinning rustup itself.** rustup is the bootstrap mechanism;
  pinning rustup would be circular. The proposal assumes the
  operator's rustup is reasonably current (the documented
  `rust-toolchain.toml` schema has been stable since rustup 1.23,
  shipped in 2020, well below any rustup version anyone on the
  project is running).

- **Workspace dependency version drift.** Governed by
  `Cargo.lock` and `[workspace.dependencies]`; separate concern.

- **Live execution paths.** Fail-closed by policy per
  `docs/12-risk-and-execution-policy.md`. R1 does not change
  execution behavior; tests continue to use SIM/manual modes only.

- **Remote-agent cargo capability.** Per `a2fa027`, Codex and
  Claude cannot install cargo and cannot run the cargo gate. R1
  does not change this; the pin is irrelevant in their
  environment because no cargo invocation occurs there.
