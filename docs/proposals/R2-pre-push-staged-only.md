# Proposal: Pre-push hook tests staged/committed state, not working tree (R2)

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Author**: claude (remote agent), 2026-05-05.
>
> **Branch**: `claude/r2-pre-push-staged-only-design`. Sprint base: `codex/fix-clippy-run-24549051096`.
>
> **Open follow-up**: R2 in `docs/AGENT_STATE.md` §"Cross-cutting" (severity **HIGH**).

---

## 1. Problem

`.githooks/pre-push` invokes `scripts/check-rust-ci.sh`, which runs
`cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`,
and `cargo test --workspace`. The hook runs against the operator's working
tree as it sits on disk — staged changes, unstaged changes, and untracked
files are all visible to the cargo invocations. What gets pushed to `origin`
is the staged/committed state, which can diverge from the working tree.

When that divergence is benign the divergence is invisible. When the working
tree contains the fix for a problem present in the committed state, the hook
reports green but `origin` is broken. CI (the documented backstop in playbook
§3b) catches it, but only multiple minutes after the push, by which time
remote agents may already be hydrating against a broken sprint base.

This recurred three times in 24 hours on the `codex/fix-clippy-run-24549051096`
sprint base:

1. **`retention_cutoff_ts` import** — restored at commit
   `05bca71` ("chore(strategy): restore retention_cutoff_ts test import + cargo fmt reflow").
   The committed tree was missing a `use` line that the operator's working
   tree carried; pre-push compiled clean against the working tree.
2. **`clippy::unnecessary_sort_by`** — silenced at commit
   `a82e8f0` ("chore(execution,strategy): silence clippy::unnecessary_sort_by on
   sprint base") in `execution-service` and `strategy-service`. The lint
   triggered against the committed tree on CI; the operator's working tree
   diverged enough that local clippy did not emit the warning.
3. **The Slice A/B "dirty drag-along" period** — across the Slice A
   (`2771479`) and Slice B (`e60e634`) commits, the operator carried a
   persistent dirty working tree (4k z-chart UI in `apps/web/src/`, docs-meta
   cleanup, retention sprint state). Cross-talk between staged and unstaged
   state means the actual sequence of broken pushes is hard to attribute to
   single commits — the two specific incidents above are simply the ones
   that landed dedicated remediation commits.

The R2 row in `AGENT_STATE.md` lists three fix candidates. This proposal
weighs each, recommends a path, and defines acceptance criteria for the
implementation PR. It is **markdown-only** per playbook §5 — no code,
`Cargo.toml`, or hook change lands in this PR.

---

## 2. Constraints and what "good" looks like

The fix must:

1. **Test the bytes that will be pushed** — the staged/committed tree, not
   the dirty working tree.
2. **Preserve operator work** across the hook lifecycle, including on hook
   failure and Ctrl-C. Losing unstaged or untracked work is unacceptable.
3. **Keep `scripts/check-rust-ci.sh` as the single canonical Rust gate**
   (playbook §3b: same script that local agent and CI run). Two divergent
   scripts is a worse failure mode than the one we are fixing.
4. **Stay fast on the happy path** — the hook is hot-path for every push
   the operator makes. Adding a multi-second delay every push will lead the
   operator to set `SKIP_RUST_CHECKS=1`, which is the failure mode we are
   trying to prevent.
5. **Respect the existing `SKIP_RUST_CHECKS=1` escape hatch** — playbook
   §3b states this is local-agent-only, must not be invoked by remote
   agents. It must continue to short-circuit before any new logic.
6. **Not perturb remote-agent flow** — playbook §3b already delegates
   cargo-dependent verification away from remote agents. Whatever lands here
   must not change what remote agents do, only what the operator's
   pre-push does.

---

## 3. Options

### Option A — Stash-then-pop in `.githooks/pre-push`

Wrap the existing `"$CHECK_SCRIPT"` invocation in
`git stash push --keep-index --include-untracked`, restore via
`trap 'git stash pop' EXIT INT TERM`. The canonical
`scripts/check-rust-ci.sh` is unchanged.

Sketch (semantics, not the final patch):

```
SKIP early-return as today.

if anything not in the index (unstaged tracked + untracked):
    git stash push --keep-index --include-untracked --quiet --message "pre-push autostash"
    STASH_PUSHED=1
    trap 'pop_stash_or_warn' EXIT INT TERM
fi

"$CHECK_SCRIPT"
```

`pop_stash_or_warn` does `git stash pop --quiet` if `STASH_PUSHED=1`,
emits a recovery message on conflict (the user's work is preserved in
`git stash list` even on pop failure).

**Pros**

- Smallest diff in this set: ~25–40 LOC in `.githooks/pre-push`, no new file,
  no Cargo or CI change.
- Single canonical script preserved (constraint §2.3).
- Stash semantics are well-understood by every developer in the project;
  the recovery story is "your work is in `git stash list`" — already
  familiar.
- Reuses operator's existing `target/` cache; happy-path slowdown is the
  cost of `git stash push` plus `git stash pop` on the dirty subset of
  the tree, typically sub-second on this repo size.
- `--keep-index --include-untracked` is exactly the semantic we need:
  index stays where it is, working tree is reset to match the index,
  stash holds the unstaged + untracked delta.

**Cons**

- Stash entries can collide on `pop` if the cargo step somehow modifies
  tracked files (e.g., a test rewrites a fixture). The repo's tests do not
  do this today, but the failure mode is real if a future test does. The
  trap must distinguish a clean pop from a conflicted pop and emit
  recovery text rather than silently leaving the operator with conflict
  markers.
- `git stash` of a large worktree (the 4k z-chart UI iteration carried
  ~100 modified TS lines) is fast but not free. Measured cost on similar
  repos: 0.1–0.5s round-trip. Acceptable.
- Submodule edge case: this repo currently has no submodules, but
  `git stash --include-untracked` does not stash submodule changes; if a
  submodule were added later, the hook would still test against any
  submodule dirt. Document as a known limitation and revisit if a
  submodule lands.
- `git stash push --keep-index` with a clean working tree is a no-op that
  prints "No local changes to save" and exits non-zero in some git
  versions. The hook must guard with a "do we actually need to stash?"
  check (`git diff --quiet` for unstaged + `git ls-files --others
  --exclude-standard` for untracked) and skip the trap entirely on a
  clean tree.

**Failure modes**

| Failure | Behavior |
|---|---|
| Cargo fails (clippy red, test fail) | `set -e` exits non-zero, EXIT trap fires, stash pop restores work, push aborts. Working tree returns to pre-hook state. |
| Operator hits Ctrl-C during cargo | INT trap fires (then EXIT), stash pop restores work, push aborts. |
| Stash pop hits a conflict | Trap detects non-zero exit from `git stash pop`, emits "Your work is preserved in `git stash list` as 'pre-push autostash'. Resolve with `git stash pop` and merge conflicts." Operator is never silently left with broken state. |
| Cargo segfaults / SIGKILL via OOM | `set -e` does not catch SIGKILL of the script itself; bash does deliver an EXIT trap on its own exit, including from a SIGKILL of a child. Stash pop runs. If bash itself is SIGKILL'd, the stash entry remains in `git stash list` for manual recovery — not silent loss. |
| Clean tree | No stash taken, no trap installed (or trap is a no-op). Hook behaves identically to today. |

**Operator UX impact**

- Happy-path slowdown: 0.1–0.5s per push.
- Hook failure: operator sees the cargo error, working tree is exactly as
  it was before the hook ran. No new operator action required.
- Ctrl-C: same as today (push aborted), working tree restored.
- Worst-case (stash pop conflict): operator sees one explicit recovery
  message naming the stash entry. Not silent.

### Option B — Separate `scripts/check-rust-ci-staged.sh` operating on a stashed checkout

Add a second script (or a flag on the existing one) that materializes the
staged tree into a temporary directory, runs cargo there, cleans up. The
hook calls the new path; the local agent's manual invocation
(`./scripts/check-rust-ci.sh` per playbook §3b) keeps testing the working
tree.

Sketch:

```
TMPDIR=$(mktemp -d)
git checkout-index --all --prefix="$TMPDIR/"
# also copy Cargo.lock, target/ symlink or shared CARGO_TARGET_DIR
(cd "$TMPDIR" && cargo fmt --check && cargo clippy ... && cargo test ...)
rm -rf "$TMPDIR"
```

**Pros**

- Working tree is **never** modified, even transiently. No stash, no risk
  of pop conflicts.
- The temp checkout is exactly the bytes that will be pushed; semantics are
  unambiguous.
- Operator can keep editing while the hook runs (though pushing while
  editing is not endorsed).

**Cons**

- Two scripts: `scripts/check-rust-ci.sh` (working-tree, used by
  local-agent during PR review) and `scripts/check-rust-ci-staged.sh`
  (staged-tree, used by hook). They will drift. Playbook §3b's "single
  canonical Rust gate" intent is weakened — the hook and local-agent
  paths now check different things.
- Cargo cache: a freshly checked-out tree at `$TMPDIR` has no `target/`
  cache. Either:
  - Run cargo with `CARGO_TARGET_DIR` pointing at the operator's main
    `target/`, sharing cache. Works, but couples the temp run to the main
    tree's cache state and any concurrent cargo invocation in the main
    tree (e.g., the operator's editor's rust-analyzer) will race for the
    cache lock.
  - Maintain a sibling `target-prepush/` cache. Doubles disk usage; first
    push after a clean has the full cold-cargo cost (minutes on this
    workspace).
- New script means new test scaffolding, new docs in
  `docs/playbooks/remote-agent-bootstrap.md` §3, and a new entry in any
  developer-onboarding instructions. ~80–150 LOC across the new script,
  hook, and docs.
- `git checkout-index --all --prefix="$TMPDIR/"` materializes the index
  contents, but does not include `Cargo.lock` if the operator hasn't
  staged a recent change to it. Edge case: lockfile dirt in the working
  tree but lockfile in index matches origin — the temp checkout would
  use the indexed lockfile, which is correct, but operator confusion
  ("which lockfile is being tested?") is more likely than with Option A.

**Failure modes**

| Failure | Behavior |
|---|---|
| Cargo fails | Script exits non-zero, push aborts. `$TMPDIR` cleanup via trap. Working tree never touched. |
| Ctrl-C | INT trap fires, `$TMPDIR` removed. Working tree never touched. |
| `mktemp` fails / disk full | Hard fail, push aborted. Operator sees error. |
| Concurrent rust-analyzer in main tree (with shared `CARGO_TARGET_DIR`) | Cargo lock contention — possible spurious slowdown or "blocking waiting for file lock on build directory" message. |
| `mktemp -d` succeeds but cleanup races a Ctrl-C | Stale `$TMPDIR` accumulates in `/tmp`. Cosmetic, not data loss. |

**Operator UX impact**

- Cold cache (first push after a clean): potentially 30s–several minutes
  of cargo rebuild in the temp tree. Will lead operator to use
  `SKIP_RUST_CHECKS=1`, defeating the purpose.
- Warm cache (subsequent pushes, shared `CARGO_TARGET_DIR`): 1–5s
  overhead from filesystem materialization plus whatever incremental
  cargo does.
- Working tree: untouched. No "did my hook just delete my unstaged work?"
  category of fear.

### Option C — Document as known limitation; rely on CI

No hook change. Update playbook §3b and any operator runbook to state
explicitly that the pre-push hook tests the working tree and is
informational only; CI is the canonical signal.

**Pros**

- Zero LOC. Zero risk of new bugs in the hook.
- Honest about the constraint.

**Cons**

- The bug stays. Three documented incidents in 24h is the explicit reason
  R2 is **HIGH** in `AGENT_STATE.md` — "block all other work on this
  slipping further."
- Multi-agent operating model relies on `origin` being a trustworthy
  hydration point. CI catches breakage minutes after the push; in the
  interim, remote agents pulling the sprint base ingest broken state.
  Playbook §1's preflight does not detect "sprint base compiles" — it
  only detects pin reachability.
- Cultural debt: "we know it's broken, just be careful" composes badly
  with multi-agent work where the operator is not the only one trusting
  the pre-push signal.

**Failure modes**

- Ongoing. Same shape as the three incidents already on the record.

**Operator UX impact**

- Pre-push stays as fast as today.
- Each broken push creates ~5–15 minutes of remediation (CI red,
  follow-up commit, sometimes a remote-agent rebase). Net cost is
  almost certainly higher than the per-push 0.1–0.5s of Option A.

---

## 4. Recommendation: Option A, with explicit Slice B escalation gate

**Land Option A first.** It is the smallest diff, preserves the
single-canonical-script invariant from playbook §3b, and the failure
modes are all bounded by `git stash list` (no silent data loss).

If Option A surfaces real-world issues — stash pop conflicts on routine
operator workflow, submodule edge cases, or noticeable slowdown on the
4k z-chart UI iteration's dirty tree — escalate to Option B as a
follow-up. **Do not pre-build Option B.** The most likely outcome is
that Option A is sufficient and Option B's two-script complexity is
never paid for.

Option C is rejected because it is the status quo; the R2 row exists
specifically because the status quo failed three times in a day.

### Why not Option B as the first move

The compounding cost of two scripts (drift between hook path and
local-agent path) is a recurring tax on every future Rust gate change.
The compounding cost of Option A (occasional stash pop recovery
message) is a per-incident tax that the operator will only pay if a
test rewrites a tracked file mid-run, which the current suite does
not do.

If we discover Option A is wrong, we have at most lost ~30 LOC of hook
code. If we build Option B first and it turns out we needed Option A,
we have lost ~150 LOC plus the ongoing maintenance of a divergent
script.

---

## 5. Acceptance criteria for the implementation PR

The implementation PR (a separate PR after this proposal merges) MUST:

### 5.1 Files changed

- `.githooks/pre-push` — wrap `"$CHECK_SCRIPT"` invocation in
  stash-then-pop with `trap` on `EXIT INT TERM`. Guard the stash with a
  "is the working tree actually dirty relative to index?" check so a
  clean tree is a no-op. Preserve `SKIP_RUST_CHECKS=1` early-return
  before any stash logic.
- `docs/playbooks/remote-agent-bootstrap.md` §3b — one-paragraph note
  that the pre-push hook now tests the staged tree, that
  `scripts/check-rust-ci.sh` invoked directly by the local agent still
  tests the working tree (this is the local-agent-on-PR-branch path),
  and that the two paths therefore have different semantics by design.
- `CHANGELOG.md` `## Unreleased` — one-line entry under operator-tooling.
- `docs/AGENT_STATE.md` — flip R2 status to **resolved** with the
  implementation commit SHA, drop "block all other work" line in §"Next
  Recommended Move".

### 5.2 Behavior asserted

The hook MUST:

- Run `scripts/check-rust-ci.sh` against the index (staged) tree, not
  the on-disk working tree, when the working tree differs from the
  index.
- Restore the operator's unstaged tracked changes and untracked files
  to their pre-hook state on every exit path: success, cargo failure,
  Ctrl-C, hook script error.
- On `git stash pop` conflict, emit a single explicit recovery message
  naming the stash entry (`pre-push autostash`) and exit non-zero.
  Operator is never left with silent conflict markers and unaware of
  the stash.
- Skip the stash dance entirely when the working tree is clean
  relative to the index (no unstaged tracked changes, no untracked
  non-ignored files). On a clean tree the hook MUST behave bit-for-bit
  identically to today.
- Honor `SKIP_RUST_CHECKS=1` before any stash operation. Operator
  setting the escape hatch must not see new behavior.

### 5.3 Operator local test plan

The PR description MUST include a script (or a copy-pasteable command
sequence) that the operator can run **before** merging to verify each
of the six scenarios in §5.4. The test plan exercises the hook
directly via `bash .githooks/pre-push <remote> <url>` rather than
through `git push`, so the operator can iterate without actually
pushing.

The test plan MUST cover:

1. Set up a temp git repo with the new hook installed.
2. Reproduce each of the six scenarios in §5.4.
3. Assert the hook exits with the expected status.
4. Assert the working tree is in the expected post-hook state.
5. Clean up the temp repo.

The PR description states the assertion commands explicitly so the
operator does not need to invent them.

---

## 6. Effort estimate

| Component | LOC |
|---|---|
| `.githooks/pre-push` change (stash dance + trap + clean-tree guard) | 25–40 |
| Test script accompanying the PR (or runnable manual checklist) | 40–80 |
| `docs/playbooks/remote-agent-bootstrap.md` §3b note | 5–10 |
| `CHANGELOG.md` entry | 1 |
| `docs/AGENT_STATE.md` R2 status flip + Next Recommended Move trim | 3–5 |
| **Total** | **~75–135 LOC** |

Implementation effort: a single focused PR. Verification is the dominant
cost — the six scenarios in §5.4 must each be demonstrated.

---

## 7. Preconditions

None expected. The hook already runs with `set -euo pipefail`; the
proposed change is additive (stash dance + trap installation) and does
not require a new dependency, a new bash version, or a new git
version. The git stash flags (`--keep-index --include-untracked
--quiet --message`) are all available in `git ≥ 2.13`, well below any
git version anyone on the project is running.

One soft precondition: this is operator-tooling and only affects the
operator's machine. Remote agents do not run the pre-push hook
(playbook §3b: cargo-dependent verification is delegated). CI does not
run the pre-push hook. Therefore the implementation PR's verification
is operator-driven, not CI-driven.

---

## 8. Incidents this proposal unblocks

The implementation PR following this proposal directly addresses the
recurrence pattern that landed all three of these remediation commits:

- **`05bca71`** — `chore(strategy): restore retention_cutoff_ts test
  import + cargo fmt reflow`. The committed tree was missing the
  `retention_cutoff_ts` import that the operator's working tree
  carried. With Option A in place, the pre-push hook would have
  stashed the working-tree-only import, run cargo against the
  committed tree, and reported the missing-import compile failure
  before the push.
- **`a82e8f0`** — `chore(execution,strategy): silence
  clippy::unnecessary_sort_by on sprint base`. Local clippy (against
  the working tree) did not emit the warning; CI clippy (against
  origin) did. With Option A, the hook would have run clippy against
  the committed tree and matched CI's signal pre-push.
- **The Slice A/B "dirty drag-along" period** — across `2771479`
  (Slice A) and `e60e634` (Slice B), the operator carried a
  persistent dirty working tree with unrelated work (4k z-chart UI,
  retention sprint state, docs-meta cleanup). Cross-talk between
  staged and unstaged state during this period is the structural
  reason both `05bca71` and `a82e8f0` were necessary; Option A
  removes the structural source of the cross-talk.

---

## 9. Test scenarios the implementation PR MUST cover

The implementation PR's test plan (in the PR description) MUST
demonstrate each of the following six scenarios. For every scenario
the assertions are: (1) hook exit status, (2) working-tree state
after the hook returns, (3) `git stash list` is empty after the hook
returns (no leaked stash entry on the happy path).

1. **Clean tree** — no staged changes, no unstaged tracked changes,
   no untracked non-ignored files. Hook MUST run cargo against the
   index (which equals working tree which equals HEAD) and exit clean
   on green cargo, fail clean on red cargo. No stash is taken.
2. **Staged-only changes** — changes are `git add`-ed, working tree
   matches index. Hook MUST run cargo against the index. No stash is
   taken (working tree matches index, nothing to stash). Behavior
   identical to today on this scenario.
3. **Unstaged-only changes** — changes exist in tracked files but are
   not staged; index matches HEAD. Hook MUST stash the unstaged
   changes via `--keep-index --include-untracked`, run cargo against
   the index (= HEAD), pop the stash on exit. After the hook, working
   tree MUST match its pre-hook state exactly (use `git diff` and
   `git status --short` for the assertion).
4. **Both staged and unstaged changes** — index has staged delta over
   HEAD; working tree has additional unstaged delta over the index.
   Hook MUST stash only the unstaged delta (this is the precise
   semantic of `--keep-index`), run cargo against the staged tree,
   pop the stash on exit. After the hook, both staged and unstaged
   states MUST be restored.
5. **Hook interrupted by Ctrl-C during cargo** — operator sends SIGINT
   while cargo is running. The INT trap (and EXIT trap) MUST fire,
   `git stash pop` MUST run, working tree MUST be restored. The
   assertion is performed by sending SIGINT programmatically to the
   hook subprocess in the test harness.
6. **Hook failure during cargo** — cargo clippy or cargo test exits
   non-zero. The EXIT trap MUST fire, `git stash pop` MUST run,
   working tree MUST be restored, hook MUST propagate the cargo
   non-zero exit code to its caller. The assertion exercises both
   fmt-check failure and clippy failure.

A seventh "stash pop conflict" scenario is *recommended* but not
*required* — engineering it requires a deliberately constructed test
where the cargo run mutates a tracked file the same way as the
unstaged delta, which the current test suite does not produce
naturally. If the implementation PR includes it as a guarded test,
that guards the "operator never sees silent conflict markers"
contract from §5.2 explicitly. If it is omitted, the contract is
defended only by code review of the trap's pop-failure branch.

---

## 10. Open questions for operator approval

1. **Option A acceptable as Slice A?** Or does the operator want to
   skip directly to Option B for the working-tree-never-touched
   guarantee?
2. **Do we want the test plan as a runnable script
   (`scripts/test-pre-push.sh`), or as a manual checklist in the PR
   description?** Runnable script is more durable but more LOC; manual
   checklist is faster to ship.
3. **Is there an existing "pre-commit" or related hook that should
   adopt the same staged-only pattern at the same time?** A quick
   `ls .githooks/` answer scopes whether this proposal generalizes.
4. **Should `SKIP_RUST_CHECKS=1` rotate to a less-permissive name?**
   Out of scope for this proposal but adjacent — if the staged-only
   fix lands, the most common reason to set the escape hatch
   (slow-on-dirty-tree pre-push) goes away, and the remaining uses
   are narrower. Flagging as a future R-row, not blocking this PR.

---

## 11. Out of scope

- **R1 (rust-toolchain.toml pinning)** — separate proposal, separate
  PR. R1 addresses operator/CI version drift; R2 addresses
  operator/origin tree drift. Both surfaced from the same incident
  burst but are independent fixes with no shared code.
- **CI's role as backstop** — unchanged. Playbook §3b still says CI
  is the second tier of Rust verification; this proposal makes the
  first tier (operator pre-push) match what CI checks.
- **Remote-agent flow** — unchanged. Remote agents do not run the
  hook (playbook §3b); this proposal does not change what they do.
- **The `pairs_replay_trades` standalone sort cleanup** mentioned in
  AGENT_STATE.md §Pin "Working-tree state" — that landed at
  `a82e8f0` already and is recorded in §1 of this proposal as one of
  the three incidents. No further action.
