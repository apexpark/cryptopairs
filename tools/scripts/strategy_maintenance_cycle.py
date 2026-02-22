#!/usr/bin/env python3
"""Automate daily strategy maintenance evaluation with fail-closed reporting."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import strategy_tuning_apply as apply_script

LOOKBACK_KEYS = apply_script.LOOKBACK_KEYS
HEALTH_CHECKS = (
    ("data-service", "http://127.0.0.1:8080/health"),
    ("account-service", "http://127.0.0.1:8081/health"),
    ("execution-service", "http://127.0.0.1:8082/health"),
    ("strategy-service", "http://127.0.0.1:8083/health"),
)
KNOWN_DECISIONS = {"PROMOTE", "HOLD", "REVERT"}


def utc_now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def utc_now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H-%M-%SZ")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root))
    except ValueError:
        return str(resolved)


def trunc(text: str, limit: int = 8_000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def parse_env_lookback_values(env_path: Path) -> dict[str, int]:
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    existing = apply_script.extract_existing_values(lines)
    resolved: dict[str, int] = {}
    for key in LOOKBACK_KEYS:
        value = existing.get(key)
        if value is None:
            raise ValueError(f"missing {key} in env file {env_path}")
        parsed = int(value)
        if parsed <= 0:
            raise ValueError(f"invalid non-positive value for {key}: {parsed}")
        resolved[key] = parsed
    return resolved


def is_same_profile(left: dict[str, int], right: dict[str, int]) -> bool:
    return all(int(left.get(key, -1)) == int(right.get(key, -2)) for key in LOOKBACK_KEYS)


def run_health_check(name: str, url: str, timeout_seconds: float) -> dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc)
    result: dict[str, Any] = {
        "name": name,
        "url": url,
        "started_at": started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "pass": False,
    }
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read(256).decode("utf-8", errors="replace")
            result["status_code"] = int(response.getcode())
            result["response_snippet"] = body
            result["pass"] = 200 <= int(response.getcode()) < 300
    except (urllib.error.URLError, socket.timeout, ValueError) as error:
        result["error"] = str(error)
        result["pass"] = False
    result["finished_at"] = utc_now_iso()
    return result


def run_subprocess(command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    finished = dt.datetime.now(dt.timezone.utc)
    return {
        "command": command,
        "started_at": started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "finished_at": finished.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "exit_code": int(completed.returncode),
        "stdout_tail": trunc(completed.stdout),
        "stderr_tail": trunc(completed.stderr),
    }


def run_report_step(
    *,
    python_bin: str,
    repo_root: Path,
    timeout_seconds: int,
    strategy_service_url: str,
    execution_service_url: str,
    exchange: str,
    account_id: str,
    window_minutes: int,
    policy_json: Path,
    profile: str,
    output_json: Path,
    compare_report: Path | None = None,
    skip_reoptimize: bool = False,
    timeframes: str = "1m,15m,1h",
    limit: int = 20,
) -> dict[str, Any]:
    command = [
        python_bin,
        "tools/scripts/strategy_tuning_report.py",
        "--strategy-service-url",
        strategy_service_url,
        "--execution-service-url",
        execution_service_url,
        "--exchange",
        exchange,
        "--account-id",
        account_id,
        "--window-minutes",
        str(window_minutes),
        "--policy-json",
        str(policy_json),
        "--profile",
        profile,
        "--timeframes",
        timeframes,
        "--limit",
        str(limit),
        "--output-json",
        str(output_json),
    ]
    if compare_report is not None:
        command.extend(["--compare-report", str(compare_report)])
    if skip_reoptimize:
        command.append("--skip-reoptimize")

    run = run_subprocess(command, repo_root, timeout_seconds)
    step: dict[str, Any] = {
        **run,
        "output_json": str(output_json),
        "pass": run["exit_code"] == 0 and output_json.exists(),
    }
    if output_json.exists():
        try:
            step["report"] = load_json(output_json)
        except Exception as error:  # noqa: BLE001
            step["pass"] = False
            step["error"] = f"unable to parse report json: {error}"
    return step


def run_apply_step(
    *,
    python_bin: str,
    repo_root: Path,
    timeout_seconds: int,
    mode: str,
    output_json: Path,
    policy_json: Path,
    env_file: Path,
    deploy_script: Path,
    services: str,
    skip_pull: bool,
    dry_run: bool,
) -> dict[str, Any]:
    command = [
        python_bin,
        "tools/scripts/strategy_tuning_apply.py",
        "--mode",
        mode,
        "--policy-json",
        str(policy_json),
        "--env-file",
        str(env_file),
        "--deploy-script",
        str(deploy_script),
        "--services",
        services,
        "--output-json",
        str(output_json),
    ]
    if skip_pull:
        command.append("--skip-pull")
    else:
        command.append("--no-skip-pull")
    if dry_run:
        command.append("--dry-run")

    run = run_subprocess(command, repo_root, timeout_seconds)
    step: dict[str, Any] = {
        **run,
        "output_json": str(output_json),
        "pass": run["exit_code"] == 0 and output_json.exists(),
    }
    if output_json.exists():
        try:
            step["apply_report"] = load_json(output_json)
            if "pass" in step["apply_report"]:
                step["pass"] = bool(step["apply_report"]["pass"])
        except Exception as error:  # noqa: BLE001
            step["pass"] = False
            step["error"] = f"unable to parse apply report json: {error}"
    return step


def restore_original_values(
    *,
    env_file: Path,
    deploy_script: Path,
    services: str,
    original_values: dict[str, int],
    skip_pull: bool,
    dry_run: bool,
    timeout_seconds: int,
    repo_root: Path,
) -> dict[str, Any]:
    step: dict[str, Any] = {
        "pass": False,
        "mode": "set-values",
        "target_values": original_values,
    }
    before_lines = env_file.read_text(encoding="utf-8").splitlines(keepends=True)
    after_lines = apply_script.apply_values(before_lines, original_values)
    before_values = apply_script.extract_existing_values(before_lines)
    step["before_values"] = before_values

    backup_path: Path | None = None
    if not dry_run:
        backup_path = env_file.with_name(f"{env_file.name}.bak.{utc_now_stamp()}.restore")
        shutil.copy2(env_file, backup_path)
        env_file.write_text("".join(after_lines), encoding="utf-8")
    step["backup_path"] = str(backup_path) if backup_path else None
    step["after_values"] = {key: str(value) for key, value in original_values.items()}

    deploy_result = apply_script.run_deploy(
        deploy_script=deploy_script,
        env_file=env_file,
        services=services,
        skip_pull=skip_pull,
        dry_run=dry_run,
    )
    step["deploy_exit_code"] = int(deploy_result.returncode)
    step["deploy_stdout"] = trunc(deploy_result.stdout)
    step["deploy_stderr"] = trunc(deploy_result.stderr)

    if deploy_result.returncode != 0 and backup_path and not dry_run:
        shutil.copy2(backup_path, env_file)
        step["rollback_performed"] = True
        step["rollback_reason"] = "deploy_failed"
    else:
        step["rollback_performed"] = False
    step["pass"] = deploy_result.returncode == 0
    return step


def choose_restore_mode(
    *,
    original_values: dict[str, int],
    baseline_values: dict[str, int],
    candidate_values: dict[str, int],
) -> str:
    if is_same_profile(original_values, baseline_values):
        return "revert"
    if is_same_profile(original_values, candidate_values):
        return "promote"
    return "custom"


def build_downloads(
    paths: list[tuple[str, Path]], repo_root: Path, artifacts_root: Path
) -> list[dict[str, str]]:
    downloads: list[dict[str, str]] = []
    for label, path in paths:
        if not path.exists():
            continue
        resolved = path.resolve()
        try:
            relative_path = str(resolved.relative_to(artifacts_root.resolve()))
        except ValueError:
            relative_path = repo_relative(resolved, repo_root)
        downloads.append(
            {
                "label": label,
                "path": relative_path,
            }
        )
    return downloads


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-bin", default="python3")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default="artifacts/strategy_tuning/runs")
    parser.add_argument(
        "--latest-report",
        default="artifacts/strategy_tuning/latest_maintenance_report.json",
    )
    parser.add_argument("--lock-file", default="artifacts/strategy_tuning/.maintenance.lock")
    parser.add_argument("--policy-json", default="infra/config/strategy_tuning_policy.json")
    parser.add_argument("--env-file", default="/opt/cryptopairs/.env.hosted")
    parser.add_argument("--deploy-script", default="scripts/deploy.sh")
    parser.add_argument("--services", default="strategy-service")
    parser.add_argument("--skip-pull", dest="skip_pull", action="store_true")
    parser.add_argument("--no-skip-pull", dest="skip_pull", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strategy-service-url", default="http://127.0.0.1:8083")
    parser.add_argument("--execution-service-url", default="http://127.0.0.1:8082")
    parser.add_argument("--exchange", default="kraken_futures")
    parser.add_argument("--account-id", default="primary")
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--timeframes", default="1m,15m,1h")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--health-timeout-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--public-health-url", default="")
    parser.add_argument("--restore-original", dest="restore_original", action="store_true")
    parser.add_argument("--no-restore-original", dest="restore_original", action="store_false")
    parser.set_defaults(skip_pull=True, restore_original=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    lock_file = (repo_root / Path(args.lock_file)).resolve()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.exists():
        report = {
            "generated_at": utc_now_iso(),
            "status": "FAIL",
            "decision": "HOLD",
            "decision_reasons": [
                f"maintenance lock exists at {repo_relative(lock_file, repo_root)}",
            ],
        }
        print(json.dumps(report, indent=2))
        return 2

    lock_file.write_text(
        json.dumps({"pid": os.getpid(), "started_at": utc_now_iso()}) + "\n",
        encoding="utf-8",
    )

    try:
        run_id = args.run_id or utc_now_stamp()
        output_root = (repo_root / Path(args.output_root)).resolve()
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        policy_path = (repo_root / Path(args.policy_json)).resolve()
        env_file = Path(args.env_file)
        deploy_script = (repo_root / Path(args.deploy_script)).resolve()
        latest_report_path = (repo_root / Path(args.latest_report)).resolve()

        baseline_report_path = run_dir / "baseline_report.json"
        apply_dry_path = run_dir / "candidate_apply_dry_run.json"
        apply_live_path = run_dir / "candidate_apply_live.json"
        candidate_report_path = run_dir / "candidate_report.json"
        restore_report_path = run_dir / "restore_original_report.json"
        decision_report_path = run_dir / "maintenance_decision.json"
        cycle_report_path = run_dir / "maintenance_cycle_report.json"

        steps: dict[str, Any] = {}
        decision = "HOLD"
        decision_reasons: list[str] = []
        status = "PASS"

        policy = load_json(policy_path)
        baseline_values = apply_script.profile_values(policy, "baseline")
        candidate_values = apply_script.profile_values(policy, "candidate")
        original_values = parse_env_lookback_values(env_file)

        health_results = [
            run_health_check(name, url, args.health_timeout_seconds) for name, url in HEALTH_CHECKS
        ]
        if args.public_health_url.strip():
            health_results.append(
                run_health_check("public-api", args.public_health_url.strip(), args.health_timeout_seconds)
            )
        health_pass = all(bool(item.get("pass")) for item in health_results)
        steps["health"] = {
            "pass": health_pass,
            "checks": health_results,
        }
        if not health_pass:
            status = "FAIL"
            decision = "HOLD"
            decision_reasons.append("health checks failed; fail-closed hold applied")

        if status == "PASS":
            steps["baseline_report"] = run_report_step(
                python_bin=args.python_bin,
                repo_root=repo_root,
                timeout_seconds=args.timeout_seconds,
                strategy_service_url=args.strategy_service_url,
                execution_service_url=args.execution_service_url,
                exchange=args.exchange,
                account_id=args.account_id,
                window_minutes=args.window_minutes,
                policy_json=policy_path,
                profile="baseline",
                output_json=baseline_report_path,
                skip_reoptimize=True,
                timeframes=args.timeframes,
                limit=args.limit,
            )
            if not steps["baseline_report"]["pass"]:
                status = "FAIL"
                decision = "HOLD"
                decision_reasons.append("baseline report step failed")
        else:
            steps["baseline_report"] = {"pass": False, "skipped": True}

        if status == "PASS":
            steps["candidate_apply_dry_run"] = run_apply_step(
                python_bin=args.python_bin,
                repo_root=repo_root,
                timeout_seconds=args.timeout_seconds,
                mode="promote",
                output_json=apply_dry_path,
                policy_json=policy_path,
                env_file=env_file,
                deploy_script=deploy_script,
                services=args.services,
                skip_pull=args.skip_pull,
                dry_run=True,
            )
            if not steps["candidate_apply_dry_run"]["pass"]:
                status = "FAIL"
                decision = "HOLD"
                decision_reasons.append("candidate dry-run apply step failed")
        else:
            steps["candidate_apply_dry_run"] = {"pass": False, "skipped": True}

        if status == "PASS":
            steps["candidate_apply_live"] = run_apply_step(
                python_bin=args.python_bin,
                repo_root=repo_root,
                timeout_seconds=args.timeout_seconds,
                mode="promote",
                output_json=apply_live_path,
                policy_json=policy_path,
                env_file=env_file,
                deploy_script=deploy_script,
                services=args.services,
                skip_pull=args.skip_pull,
                dry_run=args.dry_run,
            )
            if not steps["candidate_apply_live"]["pass"]:
                status = "FAIL"
                decision = "HOLD"
                decision_reasons.append("candidate live apply step failed")
        else:
            steps["candidate_apply_live"] = {"pass": False, "skipped": True}

        if status == "PASS":
            steps["candidate_report"] = run_report_step(
                python_bin=args.python_bin,
                repo_root=repo_root,
                timeout_seconds=args.timeout_seconds,
                strategy_service_url=args.strategy_service_url,
                execution_service_url=args.execution_service_url,
                exchange=args.exchange,
                account_id=args.account_id,
                window_minutes=args.window_minutes,
                policy_json=policy_path,
                profile="candidate",
                output_json=candidate_report_path,
                compare_report=baseline_report_path,
                skip_reoptimize=False,
                timeframes=args.timeframes,
                limit=args.limit,
            )
            if steps["candidate_report"]["pass"]:
                report_data = steps["candidate_report"].get("report", {})
                raw_decision = str(report_data.get("decision", "HOLD")).upper()
                decision = raw_decision if raw_decision in KNOWN_DECISIONS else "HOLD"
                reasons = report_data.get("decision_reasons", [])
                if isinstance(reasons, list):
                    decision_reasons.extend(str(reason) for reason in reasons)
            else:
                status = "FAIL"
                decision = "HOLD"
                decision_reasons.append("candidate report step failed")
        else:
            steps["candidate_report"] = {"pass": False, "skipped": True}

        restore_needed = (
            args.restore_original
            and not args.dry_run
            and bool(steps.get("candidate_apply_live", {}).get("pass"))
        )
        if restore_needed:
            restore_mode = choose_restore_mode(
                original_values=original_values,
                baseline_values=baseline_values,
                candidate_values=candidate_values,
            )
            if restore_mode == "custom":
                steps["restore_original"] = restore_original_values(
                    env_file=env_file,
                    deploy_script=deploy_script,
                    services=args.services,
                    original_values=original_values,
                    skip_pull=args.skip_pull,
                    dry_run=False,
                    timeout_seconds=args.timeout_seconds,
                    repo_root=repo_root,
                )
            else:
                steps["restore_original"] = run_apply_step(
                    python_bin=args.python_bin,
                    repo_root=repo_root,
                    timeout_seconds=args.timeout_seconds,
                    mode=restore_mode,
                    output_json=restore_report_path,
                    policy_json=policy_path,
                    env_file=env_file,
                    deploy_script=deploy_script,
                    services=args.services,
                    skip_pull=args.skip_pull,
                    dry_run=False,
                )
                steps["restore_original"]["mode"] = restore_mode
            if not steps["restore_original"]["pass"]:
                status = "FAIL"
                decision = "HOLD"
                decision_reasons.append("restore-original step failed")
        else:
            steps["restore_original"] = {
                "pass": True,
                "skipped": True,
                "reason": "restore disabled, dry-run mode, or candidate apply did not complete",
            }

        cycle_report: dict[str, Any] = {
            "generated_at": utc_now_iso(),
            "run_id": run_id,
            "status": status,
            "decision": decision,
            "decision_reasons": decision_reasons
            or ["No explicit decision reasons captured by cycle."],
            "policy_path": repo_relative(policy_path, repo_root),
            "env_file": str(env_file),
            "original_values": original_values,
            "baseline_values": baseline_values,
            "candidate_values": candidate_values,
            "steps": steps,
            "artifacts": {
                "run_dir": repo_relative(run_dir, repo_root),
                "baseline_report": repo_relative(baseline_report_path, repo_root),
                "candidate_apply_dry_run": repo_relative(apply_dry_path, repo_root),
                "candidate_apply_live": repo_relative(apply_live_path, repo_root),
                "candidate_report": repo_relative(candidate_report_path, repo_root),
                "restore_report": repo_relative(restore_report_path, repo_root),
                "decision_report": repo_relative(decision_report_path, repo_root),
                "cycle_report": repo_relative(cycle_report_path, repo_root),
                "latest_report": repo_relative(latest_report_path, repo_root),
            },
        }

        downloads = build_downloads(
            [
                ("Decision Report", decision_report_path),
                ("Cycle Report", cycle_report_path),
                ("Baseline Report", baseline_report_path),
                ("Candidate Apply Dry-Run", apply_dry_path),
                ("Candidate Apply Live", apply_live_path),
                ("Candidate Report", candidate_report_path),
                ("Restore Report", restore_report_path),
            ],
            repo_root,
            output_root.parent.resolve(),
        )
        cycle_report["downloads"] = downloads

        decision_report = {
            "generated_at": cycle_report["generated_at"],
            "run_id": run_id,
            "status": status,
            "decision": decision,
            "decision_reasons": cycle_report["decision_reasons"],
            "artifacts": cycle_report["artifacts"],
            "downloads": downloads,
            "step_pass_summary": {
                name: bool(value.get("pass"))
                for name, value in steps.items()
            },
        }

        write_json(decision_report_path, decision_report)
        write_json(cycle_report_path, cycle_report)
        latest_report_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cycle_report_path, latest_report_path)

        print(json.dumps(cycle_report, indent=2))
        return 0 if status == "PASS" else 2
    finally:
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
