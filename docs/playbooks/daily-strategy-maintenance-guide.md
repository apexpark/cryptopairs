# Daily Strategy Maintenance Guide (Plain English)

## Purpose

Give operators a simple daily routine to:
1. Keep the system healthy.
2. Decide whether to keep, promote, or revert strategy tuning.
3. Ship changes safely when updates are needed.

This guide is intentionally non-technical and fail-closed.

## What "Daily Maintenance" Means

Every day, answer three questions:
1. Is the platform healthy?
2. Is the current strategy profile good enough, or should we revert?
3. If we need a change, how do we ship it safely?

## 10-15 Minute Morning Routine

### Step 1: Resume context first (interruption-safe)

```bash
cd /opt/cryptopairs
python3 tools/scripts/alpha_tracker.py --plan plans/strategy_tuning_plan.json summary
```

Follow the latest `next_action`. Do not start random side tasks first.

If automation is enabled, first review the latest generated cycle report in Analytics (downloads panel), then continue with manual decision steps.

### Step 2: Confirm core services are up

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8081/health
curl -fsS http://127.0.0.1:8082/health
curl -fsS http://127.0.0.1:8083/health
```

If any health check fails, stop tuning work and recover service health first.

### Step 3: Capture a baseline report

```bash
STAMP_BASE=$(date -u +%Y-%m-%dT%H-%M-%SZ)
BASELINE_REPORT="artifacts/strategy_tuning/${STAMP_BASE}-baseline.json"

python3 tools/scripts/strategy_tuning_report.py \
  --profile baseline \
  --skip-reoptimize \
  --output-json "$BASELINE_REPORT"
```

This is your "before" snapshot.

### Step 4: Apply candidate profile safely (dry-run, then live)

Dry-run first:

```bash
STAMP_DRY=$(date -u +%Y-%m-%dT%H-%M-%SZ)
python3 tools/scripts/strategy_tuning_apply.py \
  --mode promote \
  --dry-run \
  --output-json "artifacts/strategy_tuning/${STAMP_DRY}-apply-promote-dryrun.json"
```

Live apply:

```bash
STAMP_PROMOTE=$(date -u +%Y-%m-%dT%H-%M-%SZ)
python3 tools/scripts/strategy_tuning_apply.py \
  --mode promote \
  --output-json "artifacts/strategy_tuning/${STAMP_PROMOTE}-apply-promote.json"
```

### Step 5: Capture candidate report and compare to baseline

```bash
STAMP_CAND=$(date -u +%Y-%m-%dT%H-%M-%SZ)
CANDIDATE_REPORT="artifacts/strategy_tuning/${STAMP_CAND}-candidate.json"

python3 tools/scripts/strategy_tuning_report.py \
  --profile candidate \
  --compare-report "$BASELINE_REPORT" \
  --output-json "$CANDIDATE_REPORT"
```

### Step 6: Read the decision in plain terms

```bash
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("Decision:", d.get("decision")); [print("-", r) for r in d.get("decision_reasons", [])]' "$CANDIDATE_REPORT"
```

## Decision Guide (What To Do Next)

### If decision is `PROMOTE`

Meaning: candidate settings passed checks.

Action:
1. Keep candidate active.
2. Save artifact paths in your notes/checkpoint.

### If decision is `HOLD`

Meaning: not enough clean evidence yet, or mixed results.

Action:
1. Leave current profile as-is.
2. Collect another cycle of data later.

### If decision is `REVERT`

Meaning: safety or quality degraded.

Action:

```bash
STAMP_REVERT=$(date -u +%Y-%m-%dT%H-%M-%SZ)
python3 tools/scripts/strategy_tuning_apply.py \
  --mode revert \
  --output-json "artifacts/strategy_tuning/${STAMP_REVERT}-apply-revert.json"
```

## How To Ship Changes Safely (When Updates Are Needed)

Use this flow for policy updates, strategy logic updates, or UI updates.

### 1) Create a small branch locally

```bash
cd /Users/kevinsaunders/Documents/Crypto_PairsTrader
git fetch origin
git checkout main
git pull --ff-only
git checkout -b codex/<short-change-name>
```

### 2) Make one small change slice

Examples:
- Tune thresholds/profiles: edit `infra/config/strategy_tuning_policy.json`.
- Change strategy behavior: edit service code + tests.
- Change UI copy/panels: edit web files + verify build output.

### 3) Validate before commit

Use the smallest relevant checks for the change:
- Script changes: run script tests.
- UI changes: run web build and sanity checks.
- Ops/docs changes: verify commands and referenced files exist.

### 4) Commit and push

```bash
git add <changed-files>
git commit -m "<clear change message>"
git push -u origin codex/<short-change-name>
```

### 5) Open PR and merge to `main`

After merge, deploy from server:

```bash
ssh root@46.224.220.150
cd /opt/cryptopairs
git checkout main
git pull --ff-only
bash scripts/deploy.sh
```

If `git pull --ff-only` fails because the server branch diverged, stop and align the server checkout to `origin/main` before deploy (do not create ad hoc merges on the server).

### 6) Verify after deploy

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8081/health
curl -fsS http://127.0.0.1:8082/health
curl -fsS http://127.0.0.1:8083/health
```

Then confirm frontend bundle changed when UI was modified:

```bash
APP="https://app.apexpark.io"
curl -s "$APP/?t=$(date +%s)" | rg -o '/assets/index-[^"]+\.js' | head -n1
```

## End-Of-Day Evidence Checklist

Keep these paths for auditability:
1. Baseline report artifact.
2. Candidate report artifact.
3. Promote/revert apply artifact (if used).
4. Final decision (`PROMOTE`, `HOLD`, `REVERT`) and reason summary.

## Quick Troubleshooting

1. Reporter script fails: treat as fail-closed and mark decision `HOLD`.
2. Deploy fails: do not force trading; restore safe profile and re-check health.
3. Integrity/risk gate failures: no new entries until checks are healthy again.

## Related References

- `docs/22-strategy-tuning-control.md`
- `docs/playbooks/strategy-tuning-runbook.md`
- `docs/playbooks/hosted-deployment-runbook.md`
- `infra/config/strategy_tuning_policy.json`
- `plans/strategy_tuning_plan.json`
