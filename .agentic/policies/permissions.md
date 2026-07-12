# Permissions and Worker Tiers

Worker tiers bound what any agent or subagent may do. Every work order states
the tier it runs at. Nothing here overrides `AGENTS.md`, the default-deny
authorities in `.agentic/project.yaml`, or the merge tiers in
`.agentic/policies/git-github.md`.

## Worker tiers

| Tier | Use | Default authority |
|---|---|---|
| T0 | Research / review (read-only preferred) | Read repo, run read-only commands, produce reports. No writes outside `.agentic/runs/**`. |
| T1 | Sandbox coder | Writes inside the work order's allowed paths on a lane branch. No installs, no network beyond git/GitHub for the task, no protected paths without the Tier 3 flow. |
| T2 | Local privileged verification | Dependency installs, full local test suites (cargo workspace + Timescale harness, pytest), long-running local checks. Requires explicit authorization in the work order. |
| T3 | Human (Operator) | Policy exceptions, protected-path merge authorization, champion promotion, deployment, secrets, Hetzner host access, anything touching live capital or the paper→live boundary. Never delegated. |

## Work-order caps

Every work order must state: worker tier, wall-clock budget, allowed paths,
forbidden paths, network authority, dependency-install authority, and secret
access (default: none). Anything not granted is denied.

## Standing rules

- Approval for one action is not standing authority for future actions.
- A delegated mechanical step (e.g. a merge under Tier 1/2 of the merge
  authority) never lowers a T3 authority.
- Host access to the Hetzner runtime is Operator-only; agents prepare exact
  commands for the Operator to paste (`docs/playbooks/remote-agent-bootstrap.md`).
