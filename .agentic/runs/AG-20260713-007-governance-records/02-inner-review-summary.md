# Inner Review Summary — AG-20260713-007

Two independent read-only reviewers on commit 41ee6ae; repairs in the
follow-up commit.

## Reviewer A — records accuracy + bash/config safety

- Verified clean: exact six-line compose diff; `unless-stopped` policy
  choice endorsed (honors deliberate operator stops, unlike `always`);
  all register SHAs verified against git; pin convention compliant; the
  stale-skip loop's bash semantics confirmed fail-closed per tick with
  clean JSON capture; runbook claims accurate; CHANGELOG/agent-runs/work
  order consistent.
- P2: AGENT_STATE `Working-tree state` field was left describing the
  AUTO-2B review era, contradicting the Merged rows. **Fix:** rewritten
  for this slice, including the true in-flight host state.
- P3: work-order `dispatched` vs agent-runs `in-progress` vocabulary —
  waived with rationale: established convention since AG-001 (work orders
  say dispatched; agent-runs carries live status).

## Reviewer B — deploy.sh operational interaction (adversarial)

- Verdict P3-only. Restart policy converges automatically for the four app
  services on next deploy (`--force-recreate` is unconditional) and
  removes a latent footgun: pre-change, the next deploy would have
  stripped the operator's live `docker update` policies. signal-lab
  exclusion correct (separate stack). No env/interpolation interaction.
- P3: deploy.sh never touches timescaledb/redis, so compose policy on
  those two applies only via manual full `up`. **Fix:** stated in the
  hosted-runbook reboot note.
- P3: broken builds now restart-loop instead of exiting cleanly during the
  health window; deploy still fails loudly via health checks — accepted as
  inherent to the policy, noted here.

Verdict after repairs: P2 closed; P3s fixed or waived with rationale.
