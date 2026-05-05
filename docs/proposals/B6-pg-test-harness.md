# Proposal: Postgres-backed integration test harness for `strategy-service` (B6)

> **Status**: merged design proposal. Operator implementation decisions are
> captured in `docs/AGENT_STATE.md` §B6 and summarized in §10 below.
>
> **Author**: claude (remote agent), 2026-05-04.
>
> **Branch**: `claude/b6-pg-test-harness-design`. Sprint base: `codex/fix-clippy-run-24549051096`.
>
> **Open follow-up**: B6 in `docs/AGENT_STATE.md` §"From Slice B independent review".

---

## 1. Problem

`strategy-service` persists champion-selection state through `StrategyRepository`
(`services/strategy-service/src/main.rs:431`), a concrete struct holding an
`Arc<tokio_postgres::Client>`. Three methods are load-bearing for
champion-selection integrity:

- `record_evaluation` (`services/strategy-service/src/main.rs:887`) — orchestrates
  `INSERT … ON CONFLICT … DO UPDATE` on `strategy_signal_performance`, then
  reads/writes `strategy_selected_signal` via `upsert_selected_signal`, and
  conditionally writes `strategy_champion_drift_events` via
  `record_champion_drift_event`.
- `upsert_selected_signal` (`:1864`) — owns the `strategy_selected_signal`
  primary-key contract.
- `record_champion_drift_event` (`:1895`) — owns the
  `strategy_champion_drift_events` row shape.

Today there is no Postgres-backed test exercising any of these write paths.
`cargo test --workspace` exercises the in-memory accounting helper only.
The B4 follow-up ("Integration-shaped test that drives `record_evaluation` and
asserts `summary.transition_counts` matches an expected `ChampionDecision`
distribution") was downgraded to "partially resolved" because the helper
extraction (`update_persist_summary_for_transition`) is unit-tested but the
helper call could be removed from `record_evaluation` and the test would still
pass — i.e. the persistence boundary is unverified.

The same harness gap blocks any future test for Slice C
(`docs/26-champion-selection-integrity-fix-spec.md` §"Slice C: Remove Incumbent
Bias In Host Runtime") and Slice D (Recanonicalize Legacy Rows) that needs to
assert real `upsert_selected_signal` / `record_champion_drift_event` row shape
and ON CONFLICT semantics under simulated host lineage.

This proposal picks an architecture for that harness. It is **markdown-only**
per playbook §5 — no code, no `Cargo.toml`, no schema, no CI changes land in
this PR. A subsequent implementation PR (after operator approval) will execute
the chosen path.

---

## 2. What "good" looks like

The harness should:

1. **Drive real SQL** through `tokio_postgres` against a real Postgres (the
   prod adapter is `tokio-postgres`; mocks at the SQL-string level are
   low-confidence and easy to drift).
2. **Run idempotently** — every test run starts from a known empty state,
   teardown leaves nothing behind for the next run.
3. **Not require new contributor tooling** by default — `cargo test
   --workspace` without Docker should still pass. Pg-backed tests are opt-in
   locally, automatic in CI.
4. **Survive in CI** without flake from port conflicts or container-startup
   races.
5. **Match production schema** by reusing `StrategyRepository::ensure_schema`
   so the harness can never drift away from the prod DDL.
6. **Not require a `Cargo.toml` rewrite** of the existing 30+ async methods
   on `StrategyRepository` (`fetch_recent_closes`, `record_opportunity_history`,
   `replace_paper_trades`, etc.). The B6 spec line in `AGENT_STATE.md`
   acknowledges the trait-seam alternative; this proposal explains why I am
   not recommending it.

---

## 3. Options

### Option A — `testcontainers-rs` (ephemeral container per test run)

Spin a fresh postgres or `timescale/timescaledb:2.16.1-pg16` container per
test process via the `testcontainers` crate.

**Pros**

- Maximum isolation; each test process gets a clean DB.
- No env-var contract; the harness owns the lifecycle.
- Same image (`timescale/timescaledb:2.16.1-pg16`) as `docker-compose.yml`.

**Cons**

- New runtime dependency on Docker for any dev or CI machine that wants to
  run the integration tests. `cargo test --workspace` becomes Docker-dependent
  unless the tests are explicitly gated.
- New `Cargo.toml` dependency under `[dev-dependencies]`. Per
  `docs/07-dependency-and-supply-chain-policy.md` this requires use-case
  justification, security/maintenance assessment, and lockfile pin. Adds
  transitive surface (bollard, hyper, etc.).
- Container start-up cost (~3–8s per test process) makes the gated tests
  meaningfully slower than the rest of the suite. Mitigable via `static`
  one-time init + per-test schema isolation, but that recreates the
  complexity of Option B without its simplicity benefit.
- testcontainers-rs requires Docker socket access on CI runners. GitHub-
  hosted ubuntu runners have it, but it's a coupling the existing rust job
  in `.github/workflows/ci.yml` does not currently take on.

### Option B — CI `services: postgres` block + env-gated local opt-in

Add an `STRATEGY_TEST_DATABASE_URL` environment variable. Tests that need a
DB skip with `#[ignore]`-style logic when the var is unset; when set, they
connect to whatever Postgres the variable points at.

In CI, `.github/workflows/ci.yml`'s `rust` job gains a `services: timescaledb:`
block (GitHub Actions native) that exposes the DB on `localhost:5432`, and the
job sets `STRATEGY_TEST_DATABASE_URL` for the test step. Locally, contributors
who want to run the integration tests do
`STRATEGY_TEST_DATABASE_URL=postgres://… cargo test -p strategy-service` —
typically against the `docker-compose up timescaledb` instance the repo
already provides.

Per-test isolation is via a unique schema name formatted as
`strategy_test_{unix_seconds}_{process_id}_{atomic_counter:03}` created on
connect, used as `search_path`, and dropped on teardown. The fixture calls
`StrategyRepository::ensure_schema` against that schema so all test DDL goes
through the same code path as production.

**Pros**

- No new `Cargo.toml` deps. tokio-postgres (already a dep) is used for the
  fixture, identical adapter to production code.
- `cargo test --workspace` still passes on machines without Docker; the
  pg-gated tests skip cleanly.
- Reuses the existing `docker-compose.yml` timescaledb service for local
  iteration.
- CI `services:` is the lowest-friction CI primitive; no Docker-in-Docker.
- Schema-per-test isolation parallelises cleanly even on a single shared
  Postgres.
- Aligns with `docs/14-testing-standards.md` §"Integration tests (service
  and storage boundaries)" without adding new infra to learn.

**Cons**

- Two-tier behaviour ("skipped vs run") is easy to silently regress —
  someone removes the env var in CI and tests stop running. Mitigated by
  asserting in the fixture that, in CI specifically, the env var must be
  present (e.g. via `CI=true` heuristic that fails the test rather than
  skips when CI is detected without the URL).
- Cleanup correctness depends on the fixture's `Drop` impl actually running.
  Panicking tests must still drop the schema. Solved by a hand-written `Drop`
  implementation on the fixture struct; no `scopeguard` dependency is added.
- Per-test schema-creation cost (~100ms locally) adds up. Acceptable for the
  single-digit number of tests this harness will plausibly carry in the
  near term.

### Option C — `sqlx-mock` / SQL-string mocking

Mock at the SQL string level without hitting a real DB.

**Pros**

- No infrastructure dependency at all.

**Cons**

- `tokio-postgres` (the prod adapter) has no first-party mock library.
  Adopting a mock would require migrating to `sqlx`, which is far outside
  B6 scope and would be its own multi-PR effort.
- Mocks at the SQL-string level provide near-zero confidence about real
  ON CONFLICT semantics, cardinality, return values, or row visibility —
  exactly the properties the B4 / Slice C / Slice D tests need to assert.
- Drift risk: mocks pass while the prod query is wrong.

This option fails the "drives real SQL" criterion and is rejected.

### Option D — Trait seam (`StrategyRepository` becomes a trait, in-memory + pg impls)

Lift the StrategyRepository struct to a trait, write an in-memory
implementation for tests, keep the pg implementation for production.

**Pros**

- Zero infra dep.
- Tests are blazing fast.

**Cons**

- The struct currently has ~30+ async methods; any non-trivial subset of
  them touches multiple tables with non-trivial ON CONFLICT semantics
  (`upsert_candidate_run`, `activate_candidate_probation`,
  `replace_paper_trades`, `record_shadow_model_run`, etc.). An in-memory
  reimplementation of even the champion-selection subset would have to
  re-encode the ON CONFLICT keys, the `selected_score` comparison, and the
  drift-row write predicate that production currently expresses in SQL.
  Every drift between in-memory and pg semantics becomes a false-positive
  test pass.
- Contradicts the explicit purpose of B6, which is "assert real
  `upsert_selected_signal` / `record_champion_drift_event` behavior". An
  in-memory impl by construction cannot do that.
- Disrupts ongoing Slice C work, which is also expected to touch
  `StrategyRepository` once the host lineage is reproduced. Adding a trait
  refactor on top of unfinished slice work raises merge-conflict risk on a
  6000+ line file.

The trait seam is a viable refactor someday, but **not in service of B6**.
Recommended posture: leave `StrategyRepository` concrete; revisit a trait
split only if a future test class genuinely cannot be expressed against a
real Postgres.

---

## 4. Recommendation

**Option B**, with the following concrete shape:

1. **Adapter**: tokio-postgres, identical to production. No new `Cargo.toml`
   dependency.
2. **Discovery**: a single env var `STRATEGY_TEST_DATABASE_URL`. When unset,
   pg-gated tests are skipped (printed as `SKIPPED — STRATEGY_TEST_DATABASE_URL
   unset`). When `CI=true` and the var is unset, the fixture **fails** rather
   than skips, so a CI mis-configuration is loud, not silent.
3. **Isolation**: a fixture creates a per-test schema named
   `strategy_test_{unix_seconds}_{process_id}_{atomic_counter:03}` via
   `CREATE SCHEMA`, sets `search_path` on the connection to that schema, calls
   `StrategyRepository::ensure_schema` so DDL always goes through production
   code, runs the test, and `DROP SCHEMA … CASCADE`s from a hand-written
   `Drop` implementation so cleanup executes on panic.
4. **Reuse infra**: contributors run `docker compose up timescaledb` once
   from the existing `docker-compose.yml` and export
   `STRATEGY_TEST_DATABASE_URL=postgres://cryptopairs:cryptopairs@localhost:5432/cryptopairs`.
   No new local infra.
5. **CI**: `.github/workflows/ci.yml` `rust` job gets a `services:` block for
   `timescale/timescaledb:2.16.1-pg16` (same image as production) on
   `localhost:5432`, and the test step sets
   `STRATEGY_TEST_DATABASE_URL=postgres://postgres:postgres@localhost:5432/postgres`
   plus `CI=true`. No new repo dependency, no Docker-in-Docker.
6. **Test layout**: tests live in a new
   `services/strategy-service/tests/repository_integration.rs` integration
   test target. The fixture is a private module within that file (no public
   API exported from `strategy-service`).

This path is reversible. If, later, we hit a use case Option B can't serve
cleanly, we can layer testcontainers on top without removing the env-gated
mode. The trait seam (Option D) remains available as a much-later refactor
that this proposal does **not** lock us out of.

---

## 5. What this unblocks

| Item | What it unblocks for |
|---|---|
| **B4** (real persistence-boundary test) | The B6 implementation PR includes a test that constructs a real `StrategyRepository`, drives `record_evaluation` for each `ChampionDecision` (Initialize, Unchanged, PromoteChallenger, KeepChampion), and asserts both the in-memory `summary.transition_counts` AND the actual rows in `strategy_selected_signal` and `strategy_champion_drift_events`. This converts B4 from "partially resolved (helper-only)" to "resolved (boundary-verified)". |
| **Slice C** persistence assertions | When the host `rc/live-trial` lineage is imported (operator action; see `AGENT_STATE.md` §B-Host-Lineage), Slice C work will need tests that verify the neutral-evaluation path actually writes the same `strategy_selected_signal` row a host-lineage path would have written. That test cannot exist until B6 ships. |
| **Slice D** recanonicalization tests | Slice D's "treat `LEGACY_ROW_FALLBACK` as a migration-only internal state" requires asserting that recanonicalization writes the expected row shape AND leaves unresolved rows blocked. Both are persistence-boundary properties — same harness applies. |
| Future `StrategyRepository` regressions | Any future change to `record_evaluation`, `upsert_selected_signal`, `record_champion_drift_event`, or the surrounding ON CONFLICT primary keys gets a regression-test slot for free. |

---

## 6. Acceptance criteria for the implementation PR

The implementation PR that follows this proposal **MUST**:

1. Add `services/strategy-service/tests/repository_integration.rs` containing
   a fixture that:
   - Reads `STRATEGY_TEST_DATABASE_URL`.
   - Skips with a printed `SKIPPED` line if unset and `CI` is not `true`.
   - Fails the test with a clear error if unset and `CI=true`.
   - Connects via `tokio_postgres`.
   - Creates a unique schema and sets `search_path`.
   - Calls `StrategyRepository::ensure_schema` against the unique schema.
   - Drops the schema on teardown, including on panic.
2. Add at least one test, `record_evaluation_writes_selected_and_drift_rows`,
   that drives `record_evaluation` for each of the four `ChampionDecision`
   variants and asserts:
   - `summary.transition_counts` matches the expected per-decision distribution
     (the B4 in-memory assertion).
   - The expected number of rows landed in `strategy_selected_signal`.
   - For `PromoteChallenger` and `KeepChampion`, a row landed in
     `strategy_champion_drift_events` with the correct `decision` value.
   - For `Initialize` and `Unchanged`, **no** drift row was written.
3. Add `upsert_selected_signal_on_conflict_keeps_latest_row`, asserting that
   two upserts at the same (`pair_id`, `timeframe`) leave exactly one
   `strategy_selected_signal` row with the latest variant, score, and
   `updated_at`.
4. Extend `.github/workflows/ci.yml`'s `rust` job with a `services:` block
   for `timescale/timescaledb:2.16.1-pg16` and set the two env vars on the
   `cargo test` step. Pin the service image tag to the same tag as
   `docker-compose.yml`.
5. Update `docs/14-testing-standards.md` Rust section to document the
   `STRATEGY_TEST_DATABASE_URL` env var, how to set it locally
   (`docker compose up timescaledb` + the connection string), and the
   skip-vs-fail behaviour under `CI=true`.
6. **NOT** modify `StrategyRepository`'s public API or any of its existing
   methods. The harness drives the existing struct as-is.
7. **NOT** add new `Cargo.toml` dependencies beyond ones already in the
   workspace. The schema-name generator must use `std::time::SystemTime`,
   `std::process::id()`, and an atomic counter; do not add `uuid`.
8. Run cleanly under `cargo test --workspace` on a machine without
   `STRATEGY_TEST_DATABASE_URL` set (skipped tests, suite still green).
9. Run cleanly under `cargo test --workspace` on a machine with the env var
   set against an empty Postgres (fixture creates the schema, runs DDL,
   tests pass, fixture drops the schema; subsequent runs find no leftover
   schemas from the previous run).
10. Update `docs/AGENT_STATE.md`:
   - Move B6 row to "**resolved by this PR**".
   - Move B4 row to "**resolved (boundary-verified)**" linking to the new
     `record_evaluation_writes_selected_and_drift_rows` test.
   - Update `Done This Sprint` with the new harness entry.
   - Bump `Pin` per the Pin Convention.

The implementation PR **MAY** also (out of strict scope but reasonable to
batch):

- Add a `cargo make` or `xtask` target that wraps "start docker-compose
  timescaledb, export the env var, run integration tests" if there is
  appetite for it. Not required for B6 itself.

---

## 7. Effort estimate

Single implementation PR, expected ~250–400 LOC of test code + fixture
helpers. ~30–60 LOC of YAML changes in `ci.yml`. ~20 LOC of doc changes in
`docs/14-testing-standards.md`.

No production code change. No `Cargo.toml` dependency change.

The slowest part is likely shaping the per-test schema fixture so that
hand-written `Drop` cleanup actually runs through panic. The implementation
uses no `scopeguard` or `uuid` dependency.

---

## 8. Preconditions

This proposal does **not** itself add any preconditions. The implementation
PR depends on:

- **CI infrastructure**: GitHub Actions runners that support
  `services:` (already true for the existing `rust` job's runner —
  `ubuntu-latest`).
- **Local developer flow**: contributors who run integration tests need
  Docker locally (already required to run anything pointing at
  `docker-compose.yml`). Contributors who do not run integration tests are
  unaffected — `cargo test --workspace` continues to work without Docker.
- **No `Cargo.toml` change** is anticipated. The operator decision recorded
  in `docs/AGENT_STATE.md` §B6 forbids adding `uuid` for schema names; use
  `SystemTime`, process id, and an atomic counter instead.

The proposal does **not** depend on the host-lineage import (B-Host-Lineage)
landing first; the B6 harness is useful for B4 alone.

---

## 9. Out of scope

- Migrating to `sqlx`. Out of scope; would be a separate cross-cutting
  proposal.
- Refactoring `StrategyRepository` into a trait. Explicitly rejected for B6
  (see §3 Option D); revisit only if a future test cannot be expressed
  against a real Postgres.
- Adding a Postgres harness to other services (`data-service`,
  `strategy-runner`, etc.). The same pattern is reusable, but each service
  is a separate decision with its own approval; this proposal scopes only
  to `strategy-service`.
- Live-trading or host-runtime verification. Operator-only per
  `AGENTS.md` §8.3.

---

## 10. Operator decisions captured

The operator decisions for the implementation PR are recorded in
`docs/AGENT_STATE.md` §B6 and are binding:

1. Env var name: `STRATEGY_TEST_DATABASE_URL`.
2. Skip-vs-fail: skip locally, fail when `CI=true` and the env var is unset.
3. Include `upsert_selected_signal_on_conflict_keeps_latest_row` in the same
   implementation PR.
4. Schema name format:
   `strategy_test_{unix_seconds}_{process_id}_{atomic_counter:03}`. Do not add
   `uuid`.

---

## 11. References

- `docs/AGENT_STATE.md` §"From Slice B independent review" — B4 and B6 rows.
- `docs/26-champion-selection-integrity-fix-spec.md` §"Slice C", §"Slice D".
- `docs/14-testing-standards.md` §"Integration tests".
- `docs/07-dependency-and-supply-chain-policy.md` §"Approval Requirements".
- `services/strategy-service/src/main.rs:431` — `StrategyRepository`.
- `services/strategy-service/src/main.rs:887` — `record_evaluation`.
- `services/strategy-service/src/main.rs:1864` — `upsert_selected_signal`.
- `services/strategy-service/src/main.rs:1895` — `record_champion_drift_event`.
- `docker-compose.yml` — existing `timescaledb` service definition.
- `.github/workflows/ci.yml` — existing `rust` job.
