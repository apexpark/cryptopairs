# Inner Review Summary — AG-20260712-003

Two independent read-only reviewers on commit af8a3a1 (pre-push). Both
returned FINDINGS; all repaired before push.

## Reviewer A — doctrine fidelity to sources

- P2: ladder table dropped the AUTO-2D rung of the §3 non-negotiable
  sequence. **Fix:** table rebuilt with all five §3 rungs (2A–2D, AUTO-3)
  and §3 exit criteria verbatim; AUTO-1 moved out of the §3 attribution and
  described as the deployed predecessor from its own proposal.
- P2: AUTO-2A evidence gate paraphrased into a results/profitability bar
  and dropped §3's "duplicate/cooldown/exits verified, no live path
  reachable." **Fix:** §3 criteria used verbatim.
- P3s: AUTO-2B invented gates (fixed to §3's measurability criteria);
  AUTO-2A status overstated (now "commands prepared, ready for operator
  run"); rule 9 gloss (now attributed to the Operator decision row,
  consistent with rule 9's only-for-stop-close permission); invariants
  section attribution split between the decisions-register row and the
  docs/23 always-on rules.

## Reviewer B — adversarial loophole probing

- All SHAs, pin convention, register consistency, and scope verified PASS.
- P2: same AUTO-2D omission (converged with Reviewer A). Same fix.
- P3: "autonomous-capable" could read as license to commit dormant
  schedulers. **Fix:** defined as structure/interfaces only; instantiating
  or wiring a scheduler/daemon is "creating" one and forbidden.
- P3: cron exception grammar let Claude claim the scheduling. **Fix:** the
  exception now belongs to the Operator; Claude's part ends at preparing
  the paste text.
- P3: graduation rows not self-contained. **Fix:** a graduation row is
  authoritative only once merged via the Tier 3 flow citing the Operator
  instruction; agent-authored or unmerged rows grant nothing.

Verdict after repairs: all P2/P3 findings closed; none waived.
