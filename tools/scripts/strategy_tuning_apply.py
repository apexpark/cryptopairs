#!/usr/bin/env python3
"""Apply strategy tuning profiles with backup, deploy, and rollback safeguards."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

LOOKBACK_KEYS = (
    "STRATEGY_LOOKBACK_BARS_1M",
    "STRATEGY_LOOKBACK_BARS_15M",
    "STRATEGY_LOOKBACK_BARS_1H",
)


def utc_now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H-%M-%SZ")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_profile(mode: str, explicit_profile: str | None) -> str:
    if mode == "promote":
        return "candidate"
    if mode == "revert":
        return "baseline"
    if explicit_profile in {"baseline", "candidate"}:
        return explicit_profile
    raise ValueError("mode=set-profile requires --profile {baseline|candidate}")


def profile_values(policy: dict[str, Any], profile: str) -> dict[str, int]:
    profiles = policy.get("profiles", {})
    values = profiles.get(profile)
    if not isinstance(values, dict):
        raise ValueError(f"profile '{profile}' not found in policy")

    resolved: dict[str, int] = {}
    for key in LOOKBACK_KEYS:
        if key not in values:
            raise ValueError(f"missing key '{key}' in profile '{profile}'")
        value = int(values[key])
        if value <= 0:
            raise ValueError(f"invalid non-positive lookback value for {key}: {value}")
        resolved[key] = value
    return resolved


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"expected positive integer, got {value}")
    return parsed


def extract_existing_values(lines: list[str]) -> dict[str, str | None]:
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    existing: dict[str, str | None] = {key: None for key in LOOKBACK_KEYS}
    for line in lines:
        match = pattern.match(line.strip())
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key in existing:
            existing[key] = value
    return existing


def apply_values(lines: list[str], updates: dict[str, int]) -> list[str]:
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    replaced = set()
    updated_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        match = pattern.match(line.strip())
        if match and match.group(1) in updates:
            key = match.group(1)
            updated_lines.append(f"{key}={updates[key]}")
            replaced.add(key)
        else:
            updated_lines.append(line)

    missing = [key for key in LOOKBACK_KEYS if key not in replaced]
    if missing:
        if updated_lines and updated_lines[-1] != "":
            updated_lines.append("")
        updated_lines.append("# Strategy tuning profile values")
        for key in missing:
            updated_lines.append(f"{key}={updates[key]}")

    return [f"{line}\n" for line in updated_lines]


def run_deploy(
    deploy_script: Path,
    env_file: Path,
    services: str,
    skip_pull: bool,
    dry_run: bool,
    deploy_health_retries: int | None = None,
    deploy_health_sleep_secs: int | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        "bash",
        str(deploy_script),
        "--env-file",
        str(env_file),
        "--services",
        services,
    ]
    if skip_pull:
        cmd.append("--skip-pull")
    if dry_run:
        cmd.append("--dry-run")
    if deploy_health_retries is not None:
        cmd.extend(["--health-retries", str(deploy_health_retries)])
    if deploy_health_sleep_secs is not None:
        cmd.extend(["--health-sleep-secs", str(deploy_health_sleep_secs)])

    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["promote", "revert", "set-profile"], required=True)
    parser.add_argument("--profile", choices=["baseline", "candidate"])
    parser.add_argument("--policy-json", default="infra/config/strategy_tuning_policy.json")
    parser.add_argument("--env-file", default="/opt/cryptopairs/.env.hosted")
    parser.add_argument("--deploy-script", default="scripts/deploy.sh")
    parser.add_argument("--services", default="strategy-service")
    parser.add_argument("--skip-pull", dest="skip_pull", action="store_true")
    parser.add_argument("--no-skip-pull", dest="skip_pull", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--deploy-health-retries", type=positive_int)
    parser.add_argument("--deploy-health-sleep-secs", type=positive_int)
    parser.add_argument("--output-json", default="artifacts/strategy_tuning/apply_report.json")
    parser.set_defaults(skip_pull=True)
    args = parser.parse_args()

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "mode": args.mode,
        "profile": None,
        "pass": False,
        "rollback_performed": False,
    }

    try:
        policy_path = Path(args.policy_json)
        env_file = Path(args.env_file)
        deploy_script = Path(args.deploy_script)

        policy = load_json(policy_path)
        profile = resolve_profile(args.mode, args.profile)
        updates = profile_values(policy, profile)

        report["profile"] = profile
        report["policy_path"] = str(policy_path)
        report["env_file"] = str(env_file)
        report["deploy_script"] = str(deploy_script)
        report["skip_pull"] = bool(args.skip_pull)
        report["dry_run"] = bool(args.dry_run)
        report["deploy_health_retries"] = args.deploy_health_retries
        report["deploy_health_sleep_secs"] = args.deploy_health_sleep_secs
        report["target_values"] = updates

        if not env_file.exists():
            raise FileNotFoundError(f"env file not found: {env_file}")
        if not deploy_script.exists():
            raise FileNotFoundError(f"deploy script not found: {deploy_script}")

        before_lines = env_file.read_text(encoding="utf-8").splitlines(keepends=True)
        before_values = extract_existing_values(before_lines)
        after_lines = apply_values(before_lines, updates)

        report["before_values"] = before_values
        report["after_values"] = {key: str(value) for key, value in updates.items()}

        backup_path: str | None = None
        if not args.dry_run:
            backup = env_file.with_name(f"{env_file.name}.bak.{utc_now_stamp()}")
            shutil.copy2(env_file, backup)
            backup_path = str(backup)
            env_file.write_text("".join(after_lines), encoding="utf-8")
        report["backup_path"] = backup_path

        deploy_result = run_deploy(
            deploy_script=deploy_script,
            env_file=env_file,
            services=args.services,
            skip_pull=args.skip_pull,
            dry_run=args.dry_run,
            deploy_health_retries=args.deploy_health_retries,
            deploy_health_sleep_secs=args.deploy_health_sleep_secs,
        )

        report["deploy_exit_code"] = deploy_result.returncode
        report["deploy_stdout"] = deploy_result.stdout[-8000:]
        report["deploy_stderr"] = deploy_result.stderr[-8000:]

        if deploy_result.returncode != 0 and not args.dry_run and backup_path:
            shutil.copy2(backup_path, env_file)
            report["rollback_performed"] = True
            report["rollback_reason"] = "deploy_failed"

        report["pass"] = deploy_result.returncode == 0
    except Exception as error:  # noqa: BLE001
        report["error"] = str(error)
        report["pass"] = False

    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
