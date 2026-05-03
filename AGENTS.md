# AGENTS.md (Highest Precedence)

This file defines mandatory operating rules for Codex/automation agents working in this repository.

If any other document conflicts with this file, **this file wins**.

---

## 0) Primary Objective

Build a crypto perpetuals trading system that is:
- Safe by default (fail-closed)
- Deterministic and auditable
- Ready for large-scale deployment
- Fast to iterate without sacrificing correctness

The agent must optimize for **correctness + safety + verifiability**, then speed.

---

## 1) Ground Truth and Non-Invention Rules (Hard)

### 1.1 No fabricated repo reality
You MUST NOT claim that a file, folder, function, symbol, API, schema, dependency, or command exists unless you can point to its exact location in the repo.

Allowed forms:
- “Found at `path/to/file` (symbol: `X`)”
- “Not found in repo. Proposing to add `path/to/new_file`”

### 1.2 No fabricated external APIs/dependencies
You MUST NOT invent third-party API behavior, pricing, limits, or SDK interfaces. If adding a dependency later, it must be:
- pinned (lockfile or exact version)
- justified per `docs/07-dependency-and-supply-chain-policy.md`
- recorded in CHANGELOG if externally relevant

### 1.3 Label proposals vs facts
If you cannot verify a statement from repo artifacts, label it explicitly as **PROPOSAL**.

---

## 2) Mandatory Workflow (Every Task)

For any non-trivial task, output the following sections before writing changes:

1) **Context & Sources Consulted**
   - List docs and repo artifacts consulted (paths).

2) **Plan**
   - Bullets of steps, ordered, each step small and verifiable.

3) **Interfaces / Contracts**
   - Identify affected contracts in `specs/contracts/` (or propose new ones).

4) **Risk & Failure Modes**
   - What can go wrong? How do we fail closed?

5) **Test Plan**
   - What tests prove this? Include at least one of:
     - schema validation
     - replay test
     - integration test
     - property-based test (later)

6) **Observability**
   - What metrics/logs/alerts change? (Even if only proposed now.)

7) **Versioning**
   - Whether this changes contracts/public behavior → CHANGELOG + version bump rules.

Only after this plan is written may you propose file edits.

---

## 3) Timeboxing and Rabbit-Hole Prevention

### 3.1 Investigation timebox
If you are unsure or exploring, stop after **3 iterations** (search/inspect/attempt). Then:
- summarize what you verified
- list what is missing
- propose the smallest safe next step

### 3.2 Stop conditions (must stop and ask / propose minimal change)
Stop if any of these are true:
- requirements ambiguity impacts safety/risk/execution behavior
- a dependency or API behavior cannot be confirmed
- integrity state logic is unclear
- a change would require broad refactors without a clear contract boundary

---

## 4) Patch Size and Checkpointing

Prefer small changes that can be validated quickly:
- **Slice A:** contracts/specs + examples
- **Slice B:** tests (even stubbed) + scaffolding
- **Slice C:** implementation behind feature flag
- **Slice D:** observability + runbook updates + hardening

No “big bang” changes.

---

## 5) Required Doc Touchpoints

When touching these domains, consult and obey:
- Data ingestion/backfill/integrity → `docs/11-data-integrity-policy.md` + playbooks
- Risk / orders / execution → `docs/12-risk-and-execution-policy.md`
- Secrets / auth / keys → `docs/13-secrets-and-security.md`
- Testing → `docs/14-testing-standards.md`
- Observability → `docs/15-observability-and-alerting.md`
- UI → `docs/16-ui-styling-guide.md`
- Architecture boundaries → `docs/10-architecture.md` + ADRs

---

## 6) Definition of Done (Agent Edition)

A change is not “done” unless:
- It is verifiable (tests/specs/examples updated)
- It is documented (docs updated if behavior changes)
- It respects fail-closed behavior for risk/execution/integrity
- It includes versioning impact assessment (CHANGELOG entry if needed)

---

## 7) Escalation Payload (When Blocked)

If blocked, provide:
- what you verified (paths)
- what you couldn’t verify
- minimal safe proposal
- explicit questions needed to proceed

---

## 8) Agent Topology and Work Allocation

This repository is worked by multiple agents. Roles, capabilities, and the canonical-source rule are mandatory for all of them.

### 8.1 Roles

There are two roles:

1. **Local agent** (runs on the operator’s machine; one per session)
   - Runs against the operator’s working tree (treated as canonical for review and final say).
   - Does **review and curation**, not heavy implementation.
   - Curates `docs/AGENT_STATE.md` and approves merges to long-lived branches.
   - Has direct file access to the working tree, including uncommitted changes.

2. **Remote agent** (Codex or Claude, runs off-host; may be more than one in flight)
   - Has the larger token budget, so does the **heavy lifting**: implementation, refactor, tests, contract/example updates, schema validation runs.
   - Pulls from `origin` only (no access to operator-local uncommitted changes).
   - May commit, merge, and push.
   - Has no SSH access to runtime hosts (e.g. `cryptopairs` Hetzner). Anything requiring host verification must stop and request operator action.

### 8.2 Canonical Source Rule

The operator’s **local working tree** is the canonical source for review intent and final acceptance.
- `origin` is the sync point, not the source of truth.
- If a remote agent’s pushed work conflicts with local intent, local wins.
- Remote agents MUST NOT force-push to long-lived branches (`main`, `rc/*`).
- Remote agents MUST rebase or merge cleanly onto the latest `origin/<base-branch>` before opening a PR.

### 8.3 Work Allocation (default split)

| Activity | Default owner | Notes |
|---|---|---|
| Implementation, refactor, tests | Remote | Heavy token cost |
| Contract/example/schema updates | Remote | Must include validation run |
| Self-review (lint, type-check, schema validate) | Remote | Required before PR |
| Independent code/spec review | Remote (a *different* agent than the implementer) | Cross-agent review only |
| Final acceptance review | Local | Reads PR diff against the spec/brief |
| Merge to `main` / long-lived branches | Local (preferred) | Remote may merge if local explicitly delegates |
| `docs/AGENT_STATE.md` curation | Local | Updated at slice/PR boundaries |
| Host verification (SSH) | Operator-only | Neither role has SSH; remote MUST stop and ask |
| Touching the broader dirty worktree | Local-only | Remote agents only see committed state |

If a remote agent finds it must touch files outside the agreed slice scope, it stops and posts an escalation per §7.

### 8.4 Mandatory Hydration Sequence (every agent, every session)

Before doing any work — including review — read in this order:

1. `AGENTS.md` (this file)
2. `docs/AGENT_STATE.md` (current sprint, in-flight work, blocked items, open follow-ups, last commit pin)
3. Any task-specific brief or spec named in `AGENT_STATE.md`’s “Currently In Flight” section
4. Code paths and contracts referenced by the brief

If `docs/AGENT_STATE.md` is missing, stale (last-updated more than 7 days old without a current sprint), or its commit pin does not match `git rev-parse HEAD`, stop and request operator refresh per §7.

### 8.5 Branching and PR Convention

- Long-lived branches: `main`, `rc/*` — protected; remote agents do not force-push.
- Feature branches: `<agent-id>/<short-slug>` (e.g. `codex/slice-c-host-lineage`, `claude/b4-record-evaluation-test`).
- Remote agents open PRs against the base named in `AGENT_STATE.md`’s active slice (defaults to `main`).
- PR descriptions MUST include: slice or follow-up ID being addressed, files touched, verification commands run with their pass/fail, any in-scope items deliberately left for follow-up.

### 8.6 Definition of Done — Remote Agent Addendum

A remote agent’s PR is ready for local review only if:
- All §6 conditions are met.
- The §8.5 PR description is complete.
- `docs/AGENT_STATE.md` contains a proposed delta (added as part of the PR), or the PR description states why no state change is required.
- No host-only verification step is left assumed-passing — anything that needs SSH is explicitly listed for operator action.

