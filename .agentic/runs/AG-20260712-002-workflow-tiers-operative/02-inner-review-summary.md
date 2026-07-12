# Inner Review Summary — AG-20260712-002

Two independent read-only reviewers on commit ffaa971 (pre-push). Both
returned FINDINGS; all repaired before push. The protected-path expansion
and Tier 2 confirmation were ratified by the Operator (OP-8) before the
repair was finalized.

## Reviewer A — adversarial authority probing

- P1: `docs/playbooks/**` unprotected → runbook command-sheets the Operator
  pastes on the Hetzner host were Tier 1 self-mergeable. **Fix:** protected
  (OP-8 expansion).
- P1: `.githooks/**` + `scripts/**` unprotected → code executing on the
  Operator's machine at every push was Tier 2 self-mergeable. **Fix:**
  protected (OP-8 expansion).
- P2: root `docker-compose*.yml` unprotected. **Fix:** protected.
- P2: `Cargo.toml`/`Cargo.lock`/`rust-toolchain.toml` supply-chain vector.
  **Fix:** protected, and dependency/toolchain manifests named in the
  forbidden-even-when-delegated list.
- P2: `--admin` bypass not forbidden → could merge red CI. **Fix:**
  delegated merges pinned to green-checks-verified `gh pr merge --squash`;
  `--admin` only for the approval formality, never over failing/pending/
  bypassed checks or unresolved threads.
- P2: report-after-the-fact had no forcing function. **Fix:** per-merge
  record comment on the PR at merge time + same-session report; batching
  forbidden.
- P2: ambiguity rule missing from canonical git-github.md location. **Fix:**
  added to the operative-status note.
- P3s: forbidden list now names file categories; `services/**` fully
  protected (OP-8 chose full expansion including all services).

## Reviewer B — governance consistency

- All SHAs, pin convention, tier cross-references verified accurate.
- P2: operative-tense drift (policy files said operative-now vs register's
  operative-upon-merge). **Fix:** all four surfaces now say "operative upon
  merge of the GOV-SCAFFOLD-2 slice."
- P2: superseded register rows not flipped. **Fix:** OP-1 Q1/Q2 rows flipped
  to superseded with successor rows appended (register hygiene preserved).
- P2: Lead-Coder-authors-slices vs `AGENTS.md` §8.1. **Fix:** reworded as
  per-slice Operator assignment; AGENTS.md §8 default allocation unchanged.
- P3s: "independent perspectives" wording, docs/12 rule citation in the
  prompt pack, duplicated pin-notes sentence — all fixed.

Verdict after repairs: all P1/P2 findings closed; none waived. Operator
decisions arising from findings recorded as register rows (OP-8).
