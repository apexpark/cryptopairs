# Inner Review Summary — AG-20260729-018

Verdict: `CLEAN`

## Scope reviewed

Reviewed the exact local diff from authorized base
`c5a5c1a370112567073eaf00088ff4c121a0170d` for:

- the separate disabled-by-default AUTO-2D controller;
- its production-shaped synthetic tests;
- the AUTO-2D Operator runbook;
- compatibility and CHANGELOG records;
- PR #262 landing reconciliation; and
- append-only run/decision governance.

The unchanged v1/v2 contracts and examples, both governors, B2-c, paper
contracts, and paper engine were checked against the exact base. No host, real
artifact, second production v2 window, configuration, eligibility,
operational start, trial root/process, paper/live trading, service,
deployment, secret, CI-1, OBS-1, OBS-3, AUTO-3, merge, or unattended-loop
action occurred.

## Review angles

### Independent decision and policy angle

- The production controller does not import or invoke the v2 governor or any
  test auditor.
- Exact raw-byte hashes, producer-Git attestations, canonical timestamps,
  static baseline, snapshot completeness, selector configuration, evidence
  segregation, directions, qualification, both ranking lanes, exploration
  reservation, concentration skips, deterministic truncation, transition
  sets, churn, calculations, policy hash, decision ID, methodology, status,
  reasons, and authority fields are independently recomputed.
- The controller accepts only exact
  `POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION` output with an empty reason list
  and all governor authority fields false.
- `NONE` and null remain distinct and non-actionable. Unknown selector
  directions and non-long/short realized marks reject fail closed.

### Paper lifecycle and no-actuation angle

- Default invocation is byte-stable and performs no file, process, or network
  I/O. `--verify-only` reads and validates but creates nothing and performs no
  network request. Start requires both `--enabled --start`.
- The existing paper engine is reused only in-process; it was not modified.
  The controller owns the immutable universe, global trial ledger, exposure
  caps, entry/exit-only/hard deadlines, cooldown, candidate age, idempotency,
  expiry, no-fallback, and no-restart controls.
- Every paper record is checked against the immutable universe before the
  existing paper writer may create or append an artifact.
- Marks use literal IPv4/IPv6 loopback HTTP, GET only, with credentials,
  redirects, proxies, fragments, implicit/invalid ports, non-loopback names,
  malformed/non-finite payloads, and unknown directions refused.
- No live-order, exchange-routing, execution-service POST, deployment,
  service-configuration, automatic-restart, or self-approval surface exists.

### Input, concurrency, and retained-evidence angle

- Bound inputs require absolute normalized paths, exact raw hashes,
  regular/non-symlink/open-no-follow reads, stable identities, and repeated
  preservation checks. The exact repository SHA and clean tracked worktree
  are rechecked before creation and on every tick.
- The exact observe file is stable-read and structurally/direction validated
  before root creation, then rechecked by device/inode identity on each tick.
- The deterministic parent is opened without following symlinks, locked
  exclusively without waiting, revalidated by inode, and used for
  descriptor-relative exclusive root creation.
- Pre-existing roots and concurrent owners refuse before creation. A failure
  during initial output creation is reported as a retained partial root.
  Later failures retain the root, record `NO_GO` when writable, never
  overwrite/repair/clean/reuse it, and never retry automatically.
- Provenance records validate against the unchanged schema and bind the exact
  decision, immutable universe, bounds, paper record hashes, lifecycle,
  authority, and unresolved-open count.

### Governance and compatibility angle

- PR #262 is reconciled as exact landing
  `c5a5c1a370112567073eaf00088ff4c121a0170d`.
- The decisions register has two appended rows and zero deletions.
- Existing contracts/examples, governors, B2-c, paper contracts, and paper
  engine are byte-unchanged from the base.
- CI-1, OBS-1, and OBS-3 remain separately scoped.

## Findings repaired during inner review

1. Post-root refusals initially used the pre-root `INPUT_REJECTED` status,
   expiry relied only on the wider hard-runtime relationship, and unreadable
   persisted state could obscure unresolved exposure. Post-root refusals now
   report `NO_GO`, expiry has an explicit no-fallback terminal path, and
   unreadable state records the conservative maximum unresolved exposure.
2. Paper records were initially written before the controller checked that
   every record belonged to the immutable universe. All decision/position
   identities are now validated before the paper writer is called.
3. The root-creation path did not yet prove the concurrent-owner refusal or
   report a retained root if initial output creation failed. Both branches
   are now hardened and covered by focused tests.
4. Invalid URL ports could escape the bounded refusal path, and `localhost`
   depended on name resolution rather than a literal loopback address.
   Malformed ports/URLs now reject with bounded diagnostics and only literal
   `127.0.0.1` or `::1` is accepted.
5. The initial observe file was identity-bound but first parsed only after
   root creation. It is now stable-read and structurally/direction validated
   during read-only preflight, so malformed initial evidence creates no root.

All repaired behavior is covered by the passing focused suite.

## Verification evidence

- Focused AUTO-2D suite: **43 passed**, no skips, xfails, or placeholders.
- Full canonical `tools/scripts` suite: **370 passed plus 70 subtests**, with
  one pre-existing third-party `dateutil` deprecation warning.
- Every generated provenance record passes Draft 2020-12 schema validation
  with active RFC 3339 format checking.
- Production-shaped synthetic eligible replay matches the independent
  reconstruction exactly.
- Ruff check/format, Python 3.9 source compilation, JSON parsing,
  `git diff --check`, exact base/ancestry, append-only decisions, protected
  surface preservation, and policy-value comparison pass.
- Bounded E4 proves disabled no-I/O, two-gate start refusal, invalid-input
  no-root/no-retry/no-repair behavior, and Python 3.9 source compatibility.
- Genuine E3: **NOT RUN — separately gated**. No host file, real production
  artifact, or second comparable v2 window was accessed or fabricated.

## Residual boundaries

- Producer Git SHAs remain format-validated Operator attestations; raw-byte
  SHA-256 values are the offline content bindings.
- The controller's exposure ledger is global only within its exclusively
  owned trial. A later fresh host preflight must prove that no other paper
  loop or unresolved external paper position exists before any operational
  start; otherwise start is `NO-GO`.
- The observe source is an exact live file bound by path and inode rather than
  a fixed content hash, because append-only observations are expected during
  the bounded trial.
- Genuine E3, merge, host preflight, and one paper start remain four separate
  Operator gates. Review or CI cannot grant any of them.

## Next gate

Commit and push one exact head, then open a Tier 3 draft PR. Claude must review
that exact SHA independently and read-only. Any repair push voids the verdict.
Genuine read-only E3 is mandatory before the Operator considers merge.
Neither E3 nor merge authorizes host alignment, configuration/eligibility
mutation, or the separately gated first paper trial.
