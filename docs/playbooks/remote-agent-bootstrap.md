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
# Pin match: HEAD must equal docs/AGENT_STATE.md §Pin "Repo HEAD pin (committed)"
HEAD_SHA=$(git rev-parse HEAD)
PIN_SHA=$(grep -m1 'Repo HEAD pin' docs/AGENT_STATE.md | grep -oE '`[a-f0-9]{7,40}`' | tr -d '`')
[[ "$HEAD_SHA" == "$PIN_SHA"* || "$PIN_SHA" == "$HEAD_SHA"* ]] || { echo "PIN MISMATCH: HEAD=$HEAD_SHA pin=$PIN_SHA"; exit 1; }

# Clean tree (untracked .claude/ etc. is fine; modified files are not)
[[ -z "$(git status --porcelain | grep '^.M\|^M ')" ]] || { echo "WORKTREE DIRTY — refuse to start"; git status --short; exit 1; }

# Base branch up to date
git fetch origin
[[ -z "$(git log HEAD..origin/main --oneline)" ]] || { echo "main has moved; rebase before starting"; exit 1; }

# Confirm fresh feature branch
BRANCH=$(git branch --show-current)
[[ "$BRANCH" != "main" && "$BRANCH" != rc/* ]] || { echo "must work on a feature branch, not $BRANCH"; exit 1; }
```

---

## 2. Pick + claim a follow-up

1. Read `docs/AGENT_STATE.md` §"Next Recommended Move" top-to-bottom.
2. Pick the highest-priority item that is **not** marked operator-only and **not** already claimed (look for `Claimed by:` in the open-follow-ups table).
3. On a fresh feature branch named `<agent-id>/<short-slug>` (e.g. `claude/b3-schema-comment`, `codex/b6-pg-test-harness-design`):
   1. Edit the open-follow-ups row in `docs/AGENT_STATE.md` to add `Claimed by: <agent-id> <ISO-date>`.
   2. Commit that single edit as the **first commit** on the branch.
   3. Push immediately.
4. If the push is rejected (non-fast-forward), pull-rebase, re-check the row hasn't been claimed by another agent in the meantime, and retry. If it has been claimed, pick a different item.

The claim commit is intentionally tiny so concurrent claims surface as a git conflict you can detect, not as duplicated work you find out about at PR time.

---

## 3. Verification sequence

Run before opening the PR. The Rust portion is the same script the pre-push hook runs (`scripts/check-rust-ci.sh`) — call it by its canonical name so this stays in sync.

```bash
# Rust workspace (canonical script — also enforced by .githooks/pre-push)
./scripts/check-rust-ci.sh
# = cargo fmt --all -- --check
# + cargo clippy --workspace --all-targets -- -D warnings
# + cargo test --workspace

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
```

### What is NOT covered by this sequence

State this in the PR description rather than implying it passed:

- **Persistence-boundary tests** on `StrategyRepository` — no Postgres-backed harness in `strategy-service` (see open follow-up B6 in `AGENT_STATE.md`).
- **Host-runtime verification** — neither remote agents nor local agents have SSH to `cryptopairs`. Anything host-only is operator-only per `AGENTS.md` §8.3.
- **Live execution paths** — fail-closed by policy per `docs/12-risk-and-execution-policy.md`. Tests use SIM/manual modes only.

If your change implies coverage in any of these categories, either drop the claim or convert to a design-proposal-first PR (see §5).

The escape hatch `SKIP_RUST_CHECKS=1` exists in `.githooks/pre-push` but **must not be used** by remote agents. If checks are failing, fix them; if you cannot, raise a §6 Blocked entry.

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

## Files touched
<bullet list with one-line per-file rationale>

## Verification run
- [ ] ./scripts/check-rust-ci.sh — <pass/fail/N-A>
- [ ] tsc — <pass/fail/N-A — N/A if no apps/web change>
- [ ] schema validation — <command + result, or N/A>
- [ ] persistence-boundary tests — N/A (see B6)
- [ ] host-runtime verification — N/A (operator-only)

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
- [ ] Verification commands in the PR description correspond to the changed files (don't approve a tsc-claimed PR with no TS diff).
- [ ] `AGENT_STATE.md` delta accurately reflects what landed; status flips match.
- [ ] No new dependency without justification per `docs/07-dependency-and-supply-chain-policy.md`.
- [ ] If the change touches `specs/contracts/*` or `specs/examples/*`: schema example validates, version bumped per `docs/02-versioning-and-releases.md`, `CHANGELOG.md` entry present.
- [ ] If the change touches risk/execution/integrity surfaces: fail-closed posture preserved per `docs/12-risk-and-execution-policy.md`.
- [ ] Operator-only steps named in the PR are queued or scheduled — do not merge implying they're done.
- [ ] Pre-push hook output (or equivalent CI) was clean. Do not merge over a `SKIP_RUST_CHECKS=1` push.

If everything passes, merge to `main` (or the slice's named base branch per `AGENT_STATE.md`) and push. The local agent then bumps the `AGENT_STATE.md` pin if the merge changed `HEAD`.
