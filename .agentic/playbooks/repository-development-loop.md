# Repository Development Loop Playbook

Use this playbook only for operator-authorized, bounded repository-development
loops. It does not authorize schedulers, deployment, merge, secrets, external
connectors, host access, live trading, production jobs, or background loops.

## 1. Hydrate Local Authority

Read, in order:

1. `AGENTS.md`
2. `docs/AGENT_STATE.md`
3. `docs/playbooks/remote-agent-bootstrap.md`
4. `.agentic/project.yaml`
5. `.agentic/policies/project-loop-policy.md`
6. the task-specific brief or spec named by the operator

Stop if the `docs/AGENT_STATE.md` pin is not reachable from `HEAD`.

## 2. Prove The Loop Is Needed

Complete the Slice Loop Check before implementation:

- new input consumed;
- new state transition;
- new artifact/runtime/user value;
- why this is not repeating the prior slice;
- stop/defer condition.

If these are vague, do not run a loop. Write a one-shot work order or ask the
operator to re-scope.

## 3. Create Run State

Create `.agentic/runs/<run_id>/` and copy:

- `.agentic/templates/loop-spec.json` to `.agentic/runs/<run_id>/loop-spec.json`
- `.agentic/templates/loop-state.json` to `.agentic/runs/<run_id>/loop-state.json`

Edit the copied spec to name the real objective, allowed paths, gates, and stop
conditions. Keep permissions default-deny unless the operator explicitly grants
more authority for that exact loop.

Validate the copied spec:

```bash
python3 /Users/kevinsaunders/.codex/skills/agentic-loop-harness/scripts/loop_preflight.py .agentic/runs/<run_id>/loop-spec.json --format json
```

## 4. Iterate

For each iteration:

1. Record the starting `HEAD` and planned file paths in `loop-state.json`.
2. Make only in-scope edits.
3. Run the named deterministic gate.
4. Record command, output path, exit code, and result in `loop-state.json`.
5. Stop on success, hard-stop limit, repeated failure, forbidden authority, or
   operator stop.

Do not expand scope inside the loop. Split a new slice instead.

## 5. Check And Close

Before PR, merge, release, deployment, policy change, or irreversible action:

1. Obtain independent read-only checker review for the exact head SHA.
2. Resolve P1/P2 findings or stop with findings recorded.
3. Update `.agentic/registers/loop-runs.md`.
4. Follow `docs/ops/ai_workflow.md` and
   `docs/playbooks/remote-agent-bootstrap.md` for PR and operator review.

Merge and deployment remain outside this adapter and require the existing
operator authorization path.
