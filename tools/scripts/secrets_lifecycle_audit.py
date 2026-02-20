#!/usr/bin/env python3
"""Audit hosted secrets lifecycle configuration and mounted secret freshness."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

REFERENCE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def is_inline_placeholder(value: str) -> bool:
    if not value:
        return True
    upper = value.upper()
    return upper.startswith("REPLACE_") or upper in {"TODO", "TBD", "CHANGEME"}


def file_age_hours(path: Path) -> float:
    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    age = utc_now() - mtime
    return age.total_seconds() / 3600.0


def audit_secret(
    secret: dict[str, Any],
    env_values: dict[str, str],
    enforce_mounted_files: bool,
) -> dict[str, Any]:
    value_env = secret["value_env"]
    value_file_env = secret["value_file_env"]
    reference_env = secret["reference_env"]
    max_age_hours = int(secret["max_age_hours"])

    inline_value = env_values.get(value_env, "")
    file_value = env_values.get(value_file_env, "")
    reference_value = env_values.get(reference_env, "")

    inline_exposed = bool(inline_value) and not is_inline_placeholder(inline_value)
    has_file_path = bool(file_value)
    has_reference = bool(reference_value) and bool(REFERENCE_RE.match(reference_value))

    mounted_file_exists = False
    mounted_file_age_hours: float | None = None
    mounted_file_age_ok = True

    if file_value:
        mounted_path = Path(file_value)
        mounted_file_exists = mounted_path.exists()
        if mounted_file_exists:
            mounted_file_age_hours = file_age_hours(mounted_path)
            mounted_file_age_ok = mounted_file_age_hours <= max_age_hours
        elif enforce_mounted_files:
            mounted_file_age_ok = False

    checks = {
        "reference_present": has_reference,
        "file_path_present": has_file_path,
        "inline_secret_not_exposed": not inline_exposed,
        "mounted_file_age_ok": mounted_file_age_ok,
    }
    passed = all(checks.values())

    return {
        "name": secret["name"],
        "value_env": value_env,
        "value_file_env": value_file_env,
        "reference_env": reference_env,
        "max_age_hours": max_age_hours,
        "checks": checks,
        "details": {
            "reference_value": reference_value,
            "file_path": file_value,
            "mounted_file_exists": mounted_file_exists,
            "mounted_file_age_hours": mounted_file_age_hours,
        },
        "pass": passed,
    }


def build_report(
    policy_path: Path,
    env_path: Path,
    enforce_mounted_files: bool,
) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    env_values = parse_env_file(env_path)

    checks = [
        audit_secret(secret, env_values, enforce_mounted_files)
        for secret in policy.get("secrets", [])
    ]

    return {
        "generated_at": iso(utc_now()),
        "policy_path": str(policy_path),
        "env_path": str(env_path),
        "provider": policy.get("provider"),
        "rotation_default_hours": policy.get("rotation_default_hours"),
        "enforce_mounted_files": enforce_mounted_files,
        "secrets": checks,
        "pass": all(item["pass"] for item in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy-json",
        default="infra/config/hosted_secrets_rotation_policy.json",
    )
    parser.add_argument(
        "--env-file",
        default="infra/env/hosted-mode.env.example",
    )
    parser.add_argument(
        "--enforce-mounted-files",
        action="store_true",
        help="fail when configured secret files are missing on disk",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/secrets_lifecycle_audit_report.json",
    )
    args = parser.parse_args()

    policy_path = Path(args.policy_json)
    env_path = Path(args.env_file)
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not policy_path.exists() or not env_path.exists():
        failure = {
            "generated_at": iso(utc_now()),
            "pass": False,
            "error": "policy or env file not found",
            "policy_path": str(policy_path),
            "env_path": str(env_path),
        }
        output_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 1

    report = build_report(policy_path, env_path, args.enforce_mounted_files)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 2


if __name__ == "__main__":
    sys.exit(main())
