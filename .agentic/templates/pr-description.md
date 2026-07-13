# PR Description Mapping

How harness artifacts map into `.github/pull_request_template.md` (the
template itself is unchanged and authoritative):

| Harness artifact | PR template section |
|---|---|
| Work order objective | Summary |
| Work order id + run folder | Summary (link) |
| Worker result verification table | Test Plan |
| Evidence report | Test Plan / Observability |
| Inner review verdict | Apex Harness / Agentic Review → Reviewer signoff (advisory unless Tier 3 Codex review) |
| Merge tier claimed | Apex Harness / Agentic Review (state Tier 1–4 explicitly) |
| Base/Head SHA | Base SHA / Head SHA fields |
| Register rows added | Context & Policy References |
