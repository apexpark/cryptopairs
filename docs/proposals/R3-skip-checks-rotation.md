# Proposal: Rotate the Rust pre-push escape hatch (R3)

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Author**: codex (remote agent), 2026-05-07.
>
> **Branch**: `codex/r3-skip-checks-rotation-design`. Sprint base: `codex/fix-clippy-run-24549051096`.
>
> **Open follow-up**: R3 in `docs/AGENT_STATE.md` §"Cross-cutting" (severity low-medium).

---

## 1. Problem

R2-impl is already satisfied. The merged R2 implementation changed
`.githooks/pre-push` so the hook autostashes unstaged tracked changes and
untracked files before invoking `scripts/check-rust-ci.sh`, then restores
that state through the EXIT/INT/TERM trap. `scripts/test-pre-push.sh` covers
the seven staged-tree scenarios recorded in `docs/AGENT_STATE.md`.

That removes the main practical reason to bypass the hook during dirty-tree
work. The remaining escape hatch is still broad:

```bash
SKIP_RUST_CHECKS=1 git push
```

The current hook honors that value before any other check, prints one line,
and exits 0. That is useful in emergencies, but it is also easy to keep in a
shell session or script by accident. R3 is therefore defensive and
speculative: no bypass abuse has been observed in this repo. The goal is to
make intentional operator overrides explicit and auditable without making
legitimate emergency pushes painful enough that people invent a worse
workaround.

This is a proposal-only PR. It does not modify `.githooks/pre-push`,
`scripts/test-pre-push.sh`, CI, or Rust code.

---

## 2. Constraints and what "good" looks like

The replacement interface should:

1. Keep the hook fail-closed by default.
2. Require a human-readable reason for any bypass.
3. Make accidental persistent bypass less likely than `SKIP_RUST_CHECKS=1`.
4. Preserve a short, discoverable command for operator emergencies.
5. Keep the implementation patch small enough to review inside the hook.
6. Preserve remote-agent policy: remote agents must not invoke any bypass.

---

## 3. Options

### Option A - Rename to `RUST_PREFLIGHT_OVERRIDE=<reason-string>`

Replace the boolean skip with a reason-bearing variable:

```bash
RUST_PREFLIGHT_OVERRIDE="docs-only PR; cargo already green on base" git push
```

The hook skips only when the value is non-empty and reason-like. Boolean-ish
values such as `1`, `true`, or `yes` should be rejected so the new interface
does not collapse back into the old one.

**Trade-offs**

| Dimension | Assessment |
|---|---|
| Operator UX friction | Low. One env var, one quoted reason. |
| Audit trail clarity | Good. The hook can print the reason in the terminal output. |
| Accidental-bypass risk | Lower than today, though still persistent if exported in a shell profile. |
| Single-shot vs persistent | Persistent if exported; single command if prefixed inline. |
| Contributor discoverability | Good. The error for legacy `SKIP_RUST_CHECKS=1` can point directly to the new command form. |

**Failure modes**

- A user can still export a long-lived reason. The hook cannot distinguish an
  intentional session-level override from a stale one.
- If the reason is too lightly validated, `RUST_PREFLIGHT_OVERRIDE=1` becomes
  a renamed broad skip. Rejecting boolean-ish values closes the most obvious
  version of that failure.

### Option B - Keep `SKIP_RUST_CHECKS=1` but require `RUST_PREFLIGHT_REASON`

Keep the existing boolean, but require a second variable:

```bash
SKIP_RUST_CHECKS=1 RUST_PREFLIGHT_REASON="release branch already checked" git push
```

The hook fails closed when `SKIP_RUST_CHECKS=1` is set without a non-empty
reason.

**Trade-offs**

| Dimension | Assessment |
|---|---|
| Operator UX friction | Medium. Two variables are harder to type and easier to mistype. |
| Audit trail clarity | Good when both are set. |
| Accidental-bypass risk | Medium. An old `SKIP_RUST_CHECKS=1` export no longer bypasses alone, but a profile or alias carrying both variables would still be persistent. |
| Single-shot vs persistent | Persistent if exported. |
| Contributor discoverability | Mixed. The old name remains visible and keeps teaching "skip checks" as the mental model. |

**Failure modes**

- Backward compatibility is smoother, but the broad variable remains in the
  interface.
- Two-variable state creates awkward edge cases: reason set without skip,
  skip set without reason, stale reason reused for unrelated pushes.

### Option C - Single-shot sentinel file

Require the operator to create an untracked sentinel file under `.git/`, for
example:

```bash
printf "%s\n" "operator-approved docs-only push" > .git/rust-preflight-override-once
git push
```

The hook reads the reason, deletes the sentinel before exiting, and skips
only that one push.

**Trade-offs**

| Dimension | Assessment |
|---|---|
| Operator UX friction | High unless wrapped in a helper command. |
| Audit trail clarity | Good for the current push; weak after deletion unless the hook prints the reason. |
| Accidental-bypass risk | Lowest. The bypass is single-use by construction. |
| Single-shot vs persistent | Single-shot. |
| Contributor discoverability | Poor without adding docs or a helper script. |

**Failure modes**

- If the hook exits before deleting the sentinel, the next push might also
  skip. The implementation would need a careful trap.
- Adding a helper script improves UX but expands scope beyond the desired
  10-20 LOC hook patch.
- File permissions and path typos create more operator support burden than an
  env var.

### Option D - Deprecation warning only

Keep `SKIP_RUST_CHECKS=1` working for now, but print a deprecation warning
that points to a future replacement.

**Trade-offs**

| Dimension | Assessment |
|---|---|
| Operator UX friction | None. |
| Audit trail clarity | No better than today unless a reason is also added. |
| Accidental-bypass risk | Unchanged. |
| Single-shot vs persistent | Persistent. |
| Contributor discoverability | Good for migration messaging, bad for actually reducing bypass risk. |

**Failure modes**

- This does not solve R3. It only postpones it.
- Because R3 is defensive and no abuse has been observed, a warning-only
  transition is tempting, but it leaves the broad bypass active after the
  R2 dirty-tree pain has already been removed.

---

## 4. Backward compatibility

Recommended behavior for the implementation PR:

- `SKIP_RUST_CHECKS=1` becomes a hard reject.
- The hook exits non-zero and prints:

  ```text
  [pre-push] SKIP_RUST_CHECKS=1 is no longer supported; use RUST_PREFLIGHT_OVERRIDE='<reason>'.
  ```

- `RUST_PREFLIGHT_OVERRIDE=<reason-string>` is the only supported bypass.
- Empty values do not bypass.
- Boolean-ish values such as `1`, `true`, and `yes` are rejected with a
  message that the value must be a reason, not a boolean.

This is intentionally not warning-only. A warning still permits stale shell
state to skip the canonical Rust gate. Hard rejection is more disruptive the
first time an operator reaches for the old command, but it fails closed and
the remediation command is shown inline.

---

## 5. Recommendation

Choose **Option A: `RUST_PREFLIGHT_OVERRIDE=<reason-string>` with hard reject
for legacy `SKIP_RUST_CHECKS=1`**.

Rationale:

- It is the smallest implementation that materially improves the current
  interface.
- It turns an invisible boolean into an explicit reason without adding a new
  helper script or tracked state.
- It keeps emergency UX short enough that the operator is unlikely to route
  around the hook.
- It gives the later implementation PR a focused test surface.
- It matches the R3 intent: rotate away from the broad skip now that R2-impl
  removed dirty-tree friction.

The single-shot sentinel file is safer against persistence, but its extra UX
and implementation complexity are not justified before any bypass abuse has
been observed.

---

## 6. Acceptance criteria for the implementation PR

### 6.1 Files changed

The implementation PR should touch:

- `.githooks/pre-push`
- `scripts/test-pre-push.sh`
- `docs/playbooks/remote-agent-bootstrap.md`
- `CHANGELOG.md`
- `docs/AGENT_STATE.md`

No CI, Rust, contract, or schema files are expected.

### 6.2 Hook diff shape

Replace the current `SKIP_RUST_CHECKS=1` early-return block near the top of
`.githooks/pre-push` with two checks before the executable-check block. Keep
the patch around 10-20 LOC if possible:

```bash
if [[ "${SKIP_RUST_CHECKS:-0}" == "1" ]]; then
  echo "[pre-push] SKIP_RUST_CHECKS=1 is no longer supported; use RUST_PREFLIGHT_OVERRIDE='<reason>'." >&2
  exit 1
fi

if [[ -n "${RUST_PREFLIGHT_OVERRIDE:-}" ]]; then
  case "$RUST_PREFLIGHT_OVERRIDE" in
    1|true|TRUE|yes|YES)
      echo "[pre-push] RUST_PREFLIGHT_OVERRIDE must be a reason, not a boolean." >&2
      exit 1
      ;;
  esac
  echo "[pre-push] RUST_PREFLIGHT_OVERRIDE set; skipping Rust CI preflight. Reason: $RUST_PREFLIGHT_OVERRIDE"
  exit 0
fi
```

If the implementation needs broader validation, keep it local to this block
and explain why in the PR description.

### 6.3 Test additions

Extend `scripts/test-pre-push.sh` without weakening the existing seven R2
scenarios. Add scenarios that assert:

1. `RUST_PREFLIGHT_OVERRIDE="docs-only"` exits 0 and does not invoke the fake
   Rust check script.
2. `SKIP_RUST_CHECKS=1` exits non-zero, prints the replacement guidance, and
   does not invoke the fake Rust check script.
3. `RUST_PREFLIGHT_OVERRIDE=1` exits non-zero and does not invoke the fake
   Rust check script.
4. No override still runs the existing normal path.

These are integration-style hook tests: each scenario installs the hook into
a temp git repo and invokes `bash .githooks/pre-push origin <url>`, matching
the existing R2 harness pattern.

### 6.4 Docs updates

The implementation PR must update:

- `docs/playbooks/remote-agent-bootstrap.md` §3b to name
  `RUST_PREFLIGHT_OVERRIDE=<reason>` as the local-agent-only escape hatch and
  remove `SKIP_RUST_CHECKS=1` as a supported path.
- `docs/playbooks/remote-agent-bootstrap.md` §7 to say local review must not
  merge over a `RUST_PREFLIGHT_OVERRIDE` push or red CI run.
- `CHANGELOG.md` `## Unreleased` with one operator-tooling line.
- `docs/AGENT_STATE.md` R3 row with the implementation status and commit/PR
  reference.

---

## 7. Effort estimate

| Component | LOC |
|---|---|
| `.githooks/pre-push` replacement block | 10-20 |
| `scripts/test-pre-push.sh` scenarios | 25-45 |
| Playbook docs updates | 4-8 |
| `CHANGELOG.md` entry | 1 |
| `docs/AGENT_STATE.md` status flip | 1 |
| **Total** | **~40-75 LOC** |

Implementation effort: one focused PR. Verification is dominated by running
`scripts/test-pre-push.sh`; cargo is not relevant unless unrelated files are
touched.

---

## 8. Preconditions

1. Operator approves the backward-compatibility choice: hard reject
   `SKIP_RUST_CHECKS=1` rather than warning-only deprecation.
2. R2-impl remains present, because the recommendation assumes the hook
   already handles dirty-tree staged-only preflight.
3. No additional hook surfaces are added before implementation. `rg` currently
   finds `.githooks/pre-push` as the only hook-side consumer of
   `SKIP_RUST_CHECKS`.
4. The implementation keeps remote-agent behavior unchanged. Remote agents do
   not invoke bypasses.

---

## 9. Open questions for operator approval

1. Should `SKIP_RUST_CHECKS=1` hard reject immediately, or do you want one
   short deprecation window that still exits 0?
2. Is the boolean-ish rejection list sufficient (`1`, `true`, `TRUE`, `yes`,
   `YES`), or should the hook reject shorter-than-N-character reasons too?
3. Should the hook print the supplied reason exactly, or redact/sanitize it to
   discourage putting secrets in terminal history?
4. Should we revisit a single-shot sentinel file after the first real bypass
   incident, or keep env-var-only unless abuse appears?

---

## 10. Out of scope

- Changing `.githooks/pre-push` in this PR.
- Changing `scripts/test-pre-push.sh` in this PR.
- Changing `scripts/check-rust-ci.sh`.
- Changing CI behavior.
- Adding a helper script for sentinel-file overrides.
- Changing Rust toolchain pinning (R1).
- Changing R2 staged-tree autostash behavior.
