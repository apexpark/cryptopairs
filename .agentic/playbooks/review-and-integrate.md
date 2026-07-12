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
5. Tier 1–2: delegated mechanical merge (operative upon merge of the
   GOV-SCAFFOLD-2 slice) — verify every required check passes and the head
   SHA equals the inner-reviewed SHA, squash-merge, post the per-merge
   record comment on the PR, and report to the Operator in the same
   session. Never over failing/pending/bypassed checks or unresolved
   threads; never touching `docs/AGENT_STATE.md` or any protected path.
   Conditions in `.agentic/registers/decisions.md` (standing delegation).
6. Tier 3: Operator pastes the Codex reviewer prompt pinned to the exact head
   SHA. A verdict that does not state the SHA it reviewed, or states a stale
   one, does not count. Every repair push → fresh review at the new SHA.
   Then Operator authorization on a plain-English brief; record the
   authorization (head SHA + merge SHA) in the decisions register.
7. Tier 4: never yours. Brief the Operator with exact paste text.
8. After merge: update `docs/AGENT_STATE.md` (pin/state per its Update
   Protocol), the agent-runs register, and CHANGELOG if user-visible.
