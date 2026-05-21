#!/usr/bin/env python3
"""Validate the repo-side Slice F alert-rule template.

This script validates example coverage only. It does not inspect a production
host and must not be used as deployed alert evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from slice_f_evidence_check import REQUIRED_ALERT_RULES


FORBIDDEN_LABEL_NAMES = {
    "run_id",
    "pair_id",
    "operator_id",
    "lease_owner",
    "hostname",
    "container_id",
    "artifact_path",
    "url",
    "error_text",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("alert rules root must be an object")
    return value


def forbidden_labels_in_query(query: str) -> list[str]:
    found: list[str] = []
    for label_name in sorted(FORBIDDEN_LABEL_NAMES):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(label_name)}\s*=", query):
            found.append(label_name)
    return found


def validate_template(template: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if template.get("template_only") is not True:
        errors.append("template_only must be true")
    if template.get("not_deployment_evidence") is not True:
        errors.append("not_deployment_evidence must be true")
    if template.get("host_alerting_configured") is not False:
        errors.append("host_alerting_configured must remain false for repo templates")
    if template.get("missing_data_policy") != "BLOCK":
        errors.append("top-level missing_data_policy must be BLOCK")

    rules_raw = template.get("rules")
    if not isinstance(rules_raw, list):
        return errors + ["rules must be a list"]

    rules: dict[str, dict[str, Any]] = {}
    for index, rule in enumerate(rules_raw):
        if not isinstance(rule, dict):
            errors.append(f"rules[{index}] must be an object")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str):
            errors.append(f"rules[{index}] missing id")
            continue
        if rule_id in rules:
            errors.append(f"duplicate alert rule id: {rule_id}")
        rules[rule_id] = rule

    missing = sorted(REQUIRED_ALERT_RULES - set(rules))
    extra = sorted(set(rules) - REQUIRED_ALERT_RULES)
    for rule_id in missing:
        errors.append(f"required alert rule missing: {rule_id}")
    for rule_id in extra:
        errors.append(f"unexpected alert rule id: {rule_id}")

    for rule_id, rule in sorted(rules.items()):
        if rule.get("missing_data_policy") != "BLOCK":
            errors.append(f"{rule_id}: missing_data_policy must be BLOCK")
        if rule.get("route_required") is not True:
            errors.append(f"{rule_id}: route_required must be true")
        if rule.get("dashboard_or_query_required") is not True:
            errors.append(f"{rule_id}: dashboard_or_query_required must be true")
        if rule.get("host_configured") is not False:
            errors.append(f"{rule_id}: host_configured must remain false for repo templates")
        if rule.get("severity") not in {"P1", "P2"}:
            errors.append(f"{rule_id}: severity must be P1 or P2")
        query = rule.get("query_template")
        if not isinstance(query, str) or not query.strip():
            errors.append(f"{rule_id}: query_template missing")
            continue
        forbidden = forbidden_labels_in_query(query)
        if forbidden:
            errors.append(f"{rule_id}: forbidden metric labels used: {', '.join(forbidden)}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to Slice F alert-rule template JSON")
    parser.add_argument("--output-json", default=None, help="Optional validation report path")
    args = parser.parse_args()

    path = Path(args.path)
    try:
        template = load_json(path)
        errors = validate_template(template)
    except Exception as error:  # noqa: BLE001
        errors = [f"unable to load alert template: {error}"]

    report = {
        "path": str(path),
        "pass": not errors,
        "errors": errors,
        "host_alerting_configured": False,
    }
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
