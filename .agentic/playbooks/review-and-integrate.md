# Playbook: Review and Integrate

From a finished worker result to a merged slice.

1. Diff check: `git diff` scope matches the work order's allowed paths;
   anything outside is removed or becomes a follow-up.
2. Spec review before code review when the slice implements a proposal
   (`templates/spec-review.md`).
3. Multi-angle inner review on every diff before any PR: at least two
   read-only reviewer perspectives (correctness/tests, safety/invariants;
   add governance-consistency for `.agentic`/docs changes). Fix findings,
   re-run affected checks.
4. Open the PR with the repo template; state the merge tier claimed; fill
   Base/Head SHA.
5. Tier 1–2: merge after green CI (Tier 2 also requires the clean inner
   review); report to the Operator after the fact. **Not yet operative** —
   see the transition note in `policies/git-github.md`; until
   `docs/ops/ai_workflow.md` is amended, every merge requires per-PR
   Operator authorization.
6. Tier 3: Operator pastes the Codex reviewer prompt pinned to the exact head
   SHA. A verdict that does not state the SHA it reviewed, or states a stale
   one, does not count. Every repair push → fresh review at the new SHA.
   Then Operator authorization on a plain-English brief; record the
   authorization (head SHA + merge SHA) in the decisions register.
7. Tier 4: never yours. Brief the Operator with exact paste text.
8. After merge: update `docs/AGENT_STATE.md` (pin/state per its Update
   Protocol), the agent-runs register, and CHANGELOG if user-visible.
