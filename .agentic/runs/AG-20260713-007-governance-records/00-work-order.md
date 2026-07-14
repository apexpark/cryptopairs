---
id: AG-20260713-007
title: Governance records + restart policies + runbook amendments
repo: cryptopairs
base_branch: main
working_branch: claude/governance-records-and-restart-policies
worker_tier: T1
required_evidence_level: E2
status: dispatched
---

# Work Order

## Objective

Book the pending session records (PR #244/#249 authorizations, OP-24,
OP-25..30 host actions) into the machine-of-record; add compose restart
policies so the stack survives reboots; make the operator-authorized
loop-resilience change official runbook text; add hosted-runbook reboot
guidance; bring AGENT_STATE and agent-runs current.

## Scope

In: `.agentic/registers/*.md`, `docker-compose.yml`,
`docs/playbooks/autopilot-paper-only-runbook.md`,
`docs/playbooks/hosted-deployment-runbook.md`, `docs/AGENT_STATE.md`,
`CHANGELOG.md`, this run folder.
Out: any service code; any AUTO-2B.2 implementation; the signal-lab
compose file (not part of the production stack incident).

## Acceptance criteria

1. Six compose services carry `restart: unless-stopped`; YAML parses;
   nothing else in the compose file changes.
2. Register rows accurate (SHAs verified against git); the PR #249 thread
   promise (OP-24 row) fulfilled.
3. Runbook loop amendment matches the operator-authorized variant running
   on the host verbatim in behavior.
4. Multi-angle inner review clean before PR; Tier 3 flow on the PR
   (compose, playbooks, .agentic, AGENT_STATE all protected).

## Stop conditions

Any compose change beyond the restart key → stop (live topology file).
