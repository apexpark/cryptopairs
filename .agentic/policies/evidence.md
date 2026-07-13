# Evidence Ladder

Every claim of "done" carries an evidence level. The work order states the
required level; the worker result and the PR state the level achieved. This
complements `docs/17-verification-protocol.md`; where they differ, the
verification protocol wins.

## Levels

| Level | Name | Meaning |
|---|---|---|
| E0 | Stated limitation | Explicitly unverified; the limitation is written down. |
| E1 | Static evidence | Files exist, parse, and are internally consistent (lint, JSON parse, doc-structure checks). |
| E2 | Local deterministic check | Deterministic local suites pass: `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`, `pytest`, contract JSON validation. |
| E3 | Integrated behavior check | Behavior proven against integrated components (Timescale-backed integration harness, service-level tests, report tooling run against real captured data). |
| E4 | Risk-specific proof | Targeted proof of the safety property at stake (fail-closed demonstrated, kill-switch path exercised, stale-input rejection shown in output). |
| E5 | Release / operational proof | Evidence from the deployed Hetzner runtime, gathered via operator-run validation commands from the runbooks. |

## CryptoPairs defaults

| Change surface | Minimum level |
|---|---|
| Docs, `.agentic/**` scaffolding | E1 |
| Rust or Python code outside protected paths | E2 |
| `specs/contracts/**`, `specs/examples/**` | E2 (parse + contract tests) |
| Execution-service, risk/kill-switch behavior, champion promotion/selection, autopilot paper tooling | E3 minimum, E4 for the specific safety property the change touches |
| Deployment (`scripts/deploy.sh`, `infra/**`), secrets lifecycle, anything live-capital-adjacent | E4 minimum, E5 before the change is considered operationally done; Operator runs the host commands |

## Report fields

Every worker result records: commands run, exit status, evidence level
achieved vs required, and any E0 limitations left open.
