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
