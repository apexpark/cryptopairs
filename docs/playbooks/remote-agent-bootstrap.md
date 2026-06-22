# Remote Agent Bootstrap Playbook

> Operational procedure for `AGENTS.md` §8.4. Run top-to-bottom every session.
> `AGENTS.md` is the rules; this file is the procedure.
> If a step here conflicts with `AGENTS.md`, `AGENTS.md` wins and you stop and ask.

---

## 0. Bootstrap prompt

Paste this verbatim into a remote Codex or remote Claude session as the first turn:

```
You are working on the cryptopairs repository.
Before doing any work, read these in order and confirm each is present:

1. AGENTS.md (highest-precedence rules; pay particular attention to §8 Agent Topology and Work Allocation)
2. docs/AGENT_STATE.md (current sprint, in-flight work, blocked items, prioritized open follow-ups, last commit pin)
3. docs/playbooks/remote-agent-bootstrap.md (this playbook — follow it step by step)

Then run the §1 self-preflight from the playbook. If preflight fails, stop and report.
If preflight passes, follow the playbook's claim, work, verify, and PR steps.

Do not start work until all three reads + the preflight have completed successfully.
Do not assume any context not in those files.
```

The same prompt works for both remote Codex and remote Claude.

---

## 1. Self-preflight

Run before any work. Stop and report if any check fails.

```bash
# Pin reachability: pin SHA in AGENT_STATE.md §Pin records the "as of" anchor for state.
# Hard requirement: pin must be reachable from HEAD via fast-forward.
# Not a hard requirement: pin == HEAD. The pin lags HEAD by any trivial commits that
# didn't change state. See docs/AGENT_STATE.md §"Pin Convention" for the rationale.
# Note the `head -1`: defensive against future formatting that puts multiple backticked
# SHAs in the pin row. The first backticked SHA on the "Repo HEAD pin" line is canonical.
PIN_SHA=$(grep -m1 'Repo HEAD pin' docs/AGENT_STATE.md | grep -oE '`[a-f0-9]{7,40}`' | head -1 | tr -d '`')
[[ -n "$PIN_SHA" ]] || { echo "PIN UNREADABLE: could not extract a SHA from AGENT_STATE.md §Pin row"; exit 1; }
git merge-base --is-ancestor "$PIN_SHA" HEAD \
  || { echo "PIN UNREACHABLE: $PIN_SHA is not an ancestor of HEAD ($(git rev-parse HEAD))"; exit 1; }

# Notice: HEAD has advanced past the AGENT_STATE.md last-touch commit
LAST_TOUCHED=$(git log -1 --format=%H -- docs/AGENT_STATE.md)
HEAD_SHA=$(git rev-parse HEAD)
if [[ "$HEAD_SHA" != "$LAST_TOUCHED" ]]; then
  COMMITS_SINCE=$(git rev-list --count "$LAST_TOUCHED..HEAD")
  echo "NOTICE: HEAD ($HEAD_SHA) is $COMMITS_SINCE commits past AGENT_STATE.md last-touch ($LAST_TOUCHED)."
  echo "Skim commit subjects in $LAST_TOUCHED..HEAD; if anything changed slice scope without an AGENT_STATE.md update, stop and ask operator."
  git log --oneline "$LAST_TOUCHED..HEAD"
fi

# Clean tree (untracked .claude/ etc. is fine; modified files are not)
[[ -z "$(git status --porcelain | grep '^.M\|^M ')" ]] || { echo "WORKTREE DIRTY — refuse to start"; git status --short; exit 1; }

# Sprint base branch (read from AGENT_STATE.md §Pin "Sprint base branch" row)
SPRINT_BASE=$(grep -m1 'Sprint base branch' docs/AGENT_STATE.md | grep -oE '`[^`]+`' | head -1 | tr -d '`')
[[ -n "$SPRINT_BASE" ]] || SPRINT_BASE=main  # fallback if AGENT_STATE.md is missing the row
echo "Sprint base branch: $SPRINT_BASE"

# Sprint base up to date
git fetch origin
[[ -z "$(git log HEAD..origin/$SPRINT_BASE --oneline)" ]] \
  || { echo "$SPRINT_BASE has moved; rebase before starting"; git log HEAD..origin/$SPRINT_BASE --oneline; exit 1; }

# Branch advisory (not a hard fail — §2 enforces the actual feature-branch creation).
# Being on the sprint base or main at preflight time is OK; §2 checks out the feature branch.
BRANCH=$(git branch --show-current)
if [[ "$BRANCH" == "main" || "$BRANCH" == rc/* ]]; then
  echo "ADVISORY: currently on protected branch '$BRANCH'. §2 will checkout a fresh feature branch from origin/$SPRINT_BASE before any work."
elif [[ "$BRANCH" == "$SPRINT_BASE" ]]; then
  echo "ADVISORY: currently on the sprint base '$BRANCH'. §2 will create a feature branch from here. OK to proceed."
else
  echo "ADVISORY: currently on '$BRANCH'. If this is already your feature branch for this claim, OK; otherwise §2 will create one."
fi
```

---

## 2. Pick + claim a follow-up

1. Read `docs/AGENT_STATE.md` §"Next Recommended Move" top-to-bottom.
2. Pick the highest-priority item that is **not** marked operator-only and **not** already claimed (look for `Claimed by:` in the open-follow-ups table).
3. On a fresh feature branch named `<agent-id>/<short-slug>` (e.g. `claude/b3-schema-comment`, `codex/b6-pg-test-harness-design`), forked from the **sprint base branch** named in `AGENT_STATE.md` §Pin (the `Sprint base branch` row is canonical; do not use `main` unless that row says `main`):
   - `git fetch origin && git checkout -b <agent-id>/<slug> origin/<sprint-base-branch>`
   1. Edit the open-follow-ups row in `docs/AGENT_STATE.md` to add `Claimed by: <agent-id> <ISO-date>`.
   2. Commit that single edit as the **first commit** on the branch.
   3. Push immediately.
4. If the push is rejected (non-fast-forward), pull-rebase, re-check the row hasn't been claimed by another agent in the meantime, and retry. If it has been claimed, pick a different item.

The claim commit is intentionally tiny so concurrent claims surface as a git conflict you can detect, not as duplicated work you find out about at PR time.

---

## 3. Verification sequence

Verification splits into two tiers because the remote agent's environment cannot install `cargo`. Run every check you *can* run locally; explicitly delegate the rest to the local agent (primary) and CI (backstop).

### 3a. Agent-runnable locally (must pass before pushing)

```bash
# Web app (only if any apps/web file changed)
npm --prefix apps/web exec -- tsc --noEmit --pretty false

# Schema/example validation (only if any specs/contracts/*.schema.json or
# specs/examples/*.example.json changed). For each modified pair:
python3 - <<'PY'
import json
from jsonschema import Draft202012Validator
schema = json.load(open('specs/contracts/<NAME>.schema.json'))
example = json.load(open('specs/examples/<NAME>.example.json'))
errs = list(Draft202012Validator(schema).iter_errors(example))
assert not errs, errs
print('OK')
PY

# JSON syntax (cheap; same check ci.yml's `contracts` job runs)
for f in specs/contracts/*.json specs/examples/*.json; do
  python3 -m json.tool "$f" > /dev/null
done
```

### 3b. Cargo-dependent (delegated to local agent + CI backstop)

Remote agents **cannot** run `cargo` and **must not** attempt to install a Rust toolchain. The Rust checks are enforced two ways, both running the same canonical script `scripts/check-rust-ci.sh`:

The repository pins Rust with `rust-toolchain.toml`, and `.github/workflows/ci.yml` passes the same channel to `dtolnay/rust-toolchain`. Local rustup-aware cargo invocations and CI cargo invocations therefore resolve the same Rust channel by construction.

Operator pre-push semantics are intentionally different from direct local-agent verification: `.githooks/pre-push` temporarily autostashes unstaged tracked changes and untracked files so the hook checks the staged/index tree being pushed, while `scripts/check-rust-ci.sh` invoked directly by the local agent on a PR branch still checks that branch's working tree. These two paths have different tree semantics by design, but they continue to share the same canonical Rust command sequence.

1. **Primary — local agent runs on demand.** After the remote agent pushes a Rust-touching feature branch and opens the draft PR, the local agent pulls that branch and runs `./scripts/check-rust-ci.sh` (cargo fmt + clippy + test, fast with incremental cache). Result is posted in the PR thread.
2. **Backstop — GitHub Actions.** `.github/workflows/ci.yml` runs the same checks on every push to `codex/**` / `claude/**` and on every PR. Slower but automated.

The remote agent's job is to:

- **State explicitly in the PR description** that cargo-dependent checks are delegated (use the §4 template's "Rust check status" field).
- **Wait for at least one of the two paths** to confirm green before flipping the PR from draft to ready-for-review. CI status is observable at `https://github.com/apexpark/cryptopairs/actions`. If the agent has no GitHub access, it waits for the local agent's PR comment.
- **If CI / local-agent reports red**, the remote agent fixes and repushes. It does **not** ask for a manual cargo waiver — there is no agent-side override.

### What is NOT covered by either tier

State this in the PR description rather than implying it passed:

- **Persistence-boundary tests** on `StrategyRepository` — no Postgres-backed harness in `strategy-service` (see open follow-up B6 in `AGENT_STATE.md`). Even `cargo test --workspace` does not exercise the real `record_evaluation` write path.
- **Host-runtime verification** — neither remote agents nor local agents have SSH to `cryptopairs`. Anything host-only is operator-only per `AGENTS.md` §8.3.
- **Live execution paths** — fail-closed by policy per `docs/12-risk-and-execution-policy.md`. Tests use SIM/manual modes only.

If your change implies coverage in any of these categories, either drop the claim or convert to a design-proposal-first PR (see §5).

The escape hatch `RUST_PREFLIGHT_OVERRIDE=<reason>` exists in `.githooks/pre-push` for the local agent's emergency use only and **must not be invoked by remote agents** in any form. The hook prints the supplied reason exactly, so do not put secrets, credentials, tokens, or other sensitive values in the reason. Legacy `SKIP_RUST_CHECKS=1` is rejected. If cargo checks are failing on the local agent or CI, fix them; if you cannot, raise a §6 Blocked entry.

---

## 4. Branch, commit, PR templates

**Branch**: `<agent-id>/<short-slug>` — `agent-id` ∈ {`codex`, `claude`}, `short-slug` lowercase-kebab tied to the follow-up ID.

**Commit subject**: conventional-commit style. Examples:
- `test(strategy): add accumulate test for SelectionTransitionCounts` (B1)
- `chore(specs): document optional/required choice for transition counters` (B3)
- `refactor(strategy): mark unreachable champion-projection arm` (S8)
- `docs(proposal): postgres-backed test harness for strategy-service` (B6)

**PR description** — paste this template, fill every section, leave nothing implicit:

```
## Item addressed
<follow-up ID, e.g. B3 (Slice B follow-up) — link to docs/AGENT_STATE.md row>

## Slice Loop Check
- New input consumed: <new evidence / operator decision / incident / review finding / accepted design>
- New state transition: <what state changes when this lands>
- New artifact/runtime/user value: <concrete new value created>
- Why this is not repeating the prior slice: <specific prior capability vs this slice>
- Stop/defer condition: <boundaries that would stop, split, or require Operator approval>

## Files touched
<bullet list with one-line per-file rationale>

## Verification run
- [ ] tsc — <pass/fail/N-A — N/A if no apps/web change>
- [ ] schema validation — <command + result, or N/A>
- [ ] JSON syntax — <pass/fail/N-A>
- [ ] persistence-boundary tests — N/A (see B6)
- [ ] host-runtime verification — N/A (operator-only)

## Rust check status (delegated — see playbook §3b)
- [ ] N/A — no Rust files changed
- [ ] Pending local agent — `scripts/check-rust-ci.sh` not yet run on this branch
- [ ] Local agent: PASS at <SHA> — <link to PR comment>
- [ ] CI (GitHub Actions): PASS at <SHA> — <link>
- [ ] Either path RED — see comment thread, fix in progress

## In-scope items deliberately left for follow-up
<list, or "none">

## Operator-only steps requested
<ssh verification / secret rotation / etc., or "none">

## AGENT_STATE.md delta
<paste the proposed change to docs/AGENT_STATE.md (status flip,
new follow-up, pin update, etc.), or "no change required and why">
```

---

## 5. Two PR variants

**Implementation PR** (default) — code + tests + spec/example/contract updates + AGENT_STATE.md delta. Use when the design is already settled. Examples today: B3, S8, S6, X1.

**Design-proposal-first PR** — a single doc commit at `docs/proposals/<id>-<slug>.md` describing options, trade-offs, recommended path, acceptance criteria. **No code.** Use when the item involves infra choices, alerting topology, or contract semantics that operator must approve before implementation. Examples today: B6 (test harness shape), B5 (metrics topology), Slice C (host-lineage import strategy).

After operator approval on a design proposal, open a follow-up Implementation PR that references the merged proposal in its "Item addressed" line.

---

## 6. When blocked

Add a row to `docs/AGENT_STATE.md` §"Blocked / Waiting On" naming:

- what was attempted (one sentence)
- what blocked it (specific commit / missing dep / ambiguous spec — be precise)
- minimal next step to unblock (operator action / spec clarification / different approach)

Open the PR as a **draft** so the work-so-far is visible. Do not delete the branch. Do not retry silently — the operator may want to pick up where you left off, or assign the unblock to a different agent.

If the blocker is a `.git/index.lock` file the sandbox cannot remove, escalate immediately rather than retrying — that's the macOS host-vs-Linux-sandbox filesystem boundary issue and only the operator can clear it. Remote agents do not normally hit this because they run on a clean Linux box.

---

## 7. Local agent review checklist

When the local agent reviews an inbound PR:

- [ ] Diff stays in the claimed scope. No "broader-worktree" files snuck in (env/* configs, retention/data-horizon files, 4k z-chart UI, etc. unless explicitly part of the claimed item).
- [ ] Slice Loop Check is present and concrete for implementation, tooling, contracts, runbooks, or governance workflow changes; vague or repetitive hardening should be sent back for re-scope.
- [ ] Verification commands in the PR description correspond to the changed files (don't approve a tsc-claimed PR with no TS diff).
- [ ] **Cargo-dependent verification done by the local agent**: if any Rust file changed, the local agent runs `git fetch origin && git checkout <branch> && ./scripts/check-rust-ci.sh` and posts the result in the PR thread before approving. Do not approve a Rust-touching PR on CI-only signal — verify locally too. CI is the backstop, not the only gate.
- [ ] `AGENT_STATE.md` delta accurately reflects what landed; status flips match.
- [ ] No new dependency without justification per `docs/07-dependency-and-supply-chain-policy.md`.
- [ ] If the change touches `specs/contracts/*` or `specs/examples/*`: schema example validates, version bumped per `docs/02-versioning-and-releases.md`, `CHANGELOG.md` entry present.
- [ ] If the change touches risk/execution/integrity surfaces: fail-closed posture preserved per `docs/12-risk-and-execution-policy.md`.
- [ ] Operator-only steps named in the PR are queued or scheduled — do not merge implying they're done.
- [ ] Both verification paths green for the head SHA: local-agent `scripts/check-rust-ci.sh` AND GitHub Actions CI. Do not merge over a `RUST_PREFLIGHT_OVERRIDE` push or a red CI run.

If everything passes, merge to `main` (or the slice's named base branch per `AGENT_STATE.md`) and push. The local agent then bumps the `AGENT_STATE.md` pin if the merge changed `HEAD`.
