#!/usr/bin/env python3
"""Host-side worker for queued strategy maintenance actions."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

DEFAULT_DEPLOY_HEALTH_RETRIES = 90
DEFAULT_DEPLOY_HEALTH_SLEEP_SECS = 2


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_host_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    raw_text = str(path)
    if raw_text.startswith("/workspace/"):
        return repo_root / raw_text[len("/workspace/") :]
    if path.is_absolute():
        return path
    return repo_root / path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_apply(repo_root: Path, request: dict[str, Any]) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    apply_script = to_host_path(repo_root, request["apply_script_path"])
    env_file = to_host_path(repo_root, request["env_file_path"])
    deploy_script = to_host_path(repo_root, request["deploy_script_path"])
    output_json = to_host_path(repo_root, request["output_json_path"])
    policy_json = to_host_path(repo_root, request["policy_json_path"])
    timeout_secs = max(int(request.get("timeout_secs", 300)), 1)
    try:
        deploy_health_retries = max(
            int(request.get("deploy_health_retries", DEFAULT_DEPLOY_HEALTH_RETRIES)),
            1,
        )
        deploy_health_sleep_secs = max(
            int(request.get("deploy_health_sleep_secs", DEFAULT_DEPLOY_HEALTH_SLEEP_SECS)),
            1,
        )
    except (TypeError, ValueError) as error:
        return None, f"invalid deploy health window: {error}"

    command = [
        "python3",
        str(apply_script),
        "--mode",
        str(request["mode"]),
        "--policy-json",
        str(policy_json),
        "--env-file",
        str(env_file),
        "--deploy-script",
        str(deploy_script),
        "--services",
        str(request.get("services", "strategy-service")),
        "--output-json",
        str(output_json),
    ]
    if bool(request.get("skip_pull", True)):
        command.append("--skip-pull")
    else:
        command.append("--no-skip-pull")
    command.extend(["--deploy-health-retries", str(deploy_health_retries)])
    command.extend(["--deploy-health-sleep-secs", str(deploy_health_sleep_secs)])

    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_secs,
        )
        return result, None
    except subprocess.TimeoutExpired as error:
        return None, f"worker timed out after {timeout_secs}s: {error}"


def process_request(repo_root: Path, pending_file: Path, queue_root: Path) -> bool:
    processing_dir = queue_root / "processing"
    completed_dir = queue_root / "completed"
    failed_dir = queue_root / "failed"
    processing_dir.mkdir(parents=True, exist_ok=True)
    completed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    processing_file = processing_dir / pending_file.name
    os.replace(pending_file, processing_file)

    request = read_json(processing_file)
    started_at = utc_now()
    result, timeout_error = run_apply(repo_root, request)

    output_json = to_host_path(repo_root, request["output_json_path"])
    apply_report = None
    if output_json.exists():
        try:
            apply_report = read_json(output_json)
        except Exception as error:  # noqa: BLE001
            apply_report = {"error": f"unable to parse apply report: {error}"}

    pass_flag = False
    if apply_report and isinstance(apply_report, dict):
        pass_flag = bool(apply_report.get("pass"))
    elif result is not None:
        pass_flag = result.returncode == 0

    worker_result = {
        "processed_at": utc_now(),
        "started_at": started_at,
        "request": request,
        "timeout_error": timeout_error,
        "command_exit_code": None if result is None else result.returncode,
        "stdout_tail": "" if result is None else result.stdout[-8000:],
        "stderr_tail": "" if result is None else result.stderr[-8000:],
        "apply_report_path": str(output_json),
        "apply_report": apply_report,
        "pass": pass_flag,
    }

    request_id = str(request.get("request_id", pending_file.stem))
    result_name = f"{request_id}-result.json"
    if pass_flag:
        write_json(completed_dir / result_name, worker_result)
        os.replace(processing_file, completed_dir / processing_file.name)
    else:
        write_json(failed_dir / result_name, worker_result)
        os.replace(processing_file, failed_dir / processing_file.name)

    return True


def run_once(repo_root: Path, queue_root: Path, max_items: int) -> int:
    pending_dir = queue_root / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    for pending_file in sorted(pending_dir.glob("*.json")):
        if processed >= max_items:
            break
        process_request(repo_root, pending_file, queue_root)
        processed += 1
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default="/opt/cryptopairs")
    parser.add_argument(
        "--queue-root",
        default="artifacts/strategy_tuning/manual_action_queue",
        help="Queue root relative to repo-root unless absolute",
    )
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval-secs", type=int, default=15)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    queue_root = Path(args.queue_root)
    if not queue_root.is_absolute():
        queue_root = repo_root / queue_root
    queue_root = queue_root.resolve()

    if args.once:
        run_once(repo_root, queue_root, max(args.max_items, 1))
        return 0

    while True:
        run_once(repo_root, queue_root, max(args.max_items, 1))
        time.sleep(max(args.poll_interval_secs, 1))


if __name__ == "__main__":
    raise SystemExit(main())
