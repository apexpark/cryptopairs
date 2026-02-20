#!/usr/bin/env python3
"""Alpha tracker utility for keeping delivery focused and recoverable."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

VALID_STATUS = {"PENDING", "IN_PROGRESS", "BLOCKED", "DONE"}
VALID_PRIORITY = {"NOW", "NEXT", "LATER"}


def default_plan_path() -> Path:
    return Path(__file__).resolve().parents[2] / "plans" / "alpha_plan.json"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_plan(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"plan file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    validate_plan(data)
    return data


def save_plan(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = utc_now_iso()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def validate_plan(plan: dict[str, Any]) -> None:
    if "items" not in plan or not isinstance(plan["items"], list):
        raise SystemExit("invalid plan: missing items array")
    ids = set()
    for item in plan["items"]:
        item_id = item.get("id")
        if not isinstance(item_id, int):
            raise SystemExit("invalid plan: item id must be int")
        if item_id in ids:
            raise SystemExit(f"invalid plan: duplicate id {item_id}")
        ids.add(item_id)
        if item.get("status") not in VALID_STATUS:
            raise SystemExit(f"invalid plan: item {item_id} has invalid status")
        if item.get("priority") not in VALID_PRIORITY:
            raise SystemExit(f"invalid plan: item {item_id} has invalid priority")



def get_item(plan: dict[str, Any], item_id: int) -> dict[str, Any]:
    for item in plan["items"]:
        if item["id"] == item_id:
            return item
    raise SystemExit(f"item not found: {item_id}")


def deps_done(plan: dict[str, Any], item: dict[str, Any]) -> bool:
    deps = item.get("depends_on", [])
    for dep_id in deps:
        dep = get_item(plan, dep_id)
        if dep["status"] != "DONE":
            return False
    return True


def priority_rank(value: str) -> int:
    if value == "NOW":
        return 0
    if value == "NEXT":
        return 1
    return 2


def printable_line(item: dict[str, Any], ready: bool) -> str:
    readiness = "READY" if ready else "WAIT_DEP"
    return (
        f"#{item['id']:02d} [{item['status']}] [{item['priority']}] [{readiness}] "
        f"{item['title']}"
    )


def cmd_summary(plan: dict[str, Any], limit: int) -> int:
    items = plan["items"]
    counts = {status: 0 for status in VALID_STATUS}
    for item in items:
        counts[item["status"]] += 1

    focus_id = plan.get("active_focus_id")
    focus = None
    if isinstance(focus_id, int):
        try:
            focus = get_item(plan, focus_id)
        except SystemExit:
            focus = None

    print(f"Plan: {plan.get('milestone', 'unknown')}")
    print(f"Updated: {plan.get('updated_at', 'unknown')}")
    if focus:
        print(f"Active focus: #{focus['id']:02d} [{focus['status']}] {focus['title']}")
    else:
        print("Active focus: not set")
    print(
        "Status counts: "
        f"PENDING={counts['PENDING']} IN_PROGRESS={counts['IN_PROGRESS']} "
        f"BLOCKED={counts['BLOCKED']} DONE={counts['DONE']}"
    )

    actionable = [
        item
        for item in items
        if item["status"] in {"PENDING", "IN_PROGRESS"}
    ]
    actionable.sort(key=lambda item: (priority_rank(item["priority"]), item["id"]))

    print("\nTop actionable items:")
    for item in actionable[: max(limit, 1)]:
        print(f"- {printable_line(item, deps_done(plan, item))}")

    sidetracks = plan.get("sidetrack_queue", [])
    if sidetracks:
        print("\nParked sidetracks:")
        for parked in sidetracks:
            state = parked.get("status", "PARKED")
            print(f"- [{state}] {parked.get('title', '(untitled)')}")
    return 0


def cmd_set_status(plan: dict[str, Any], item_id: int, status: str, note: str | None, evidence: str | None) -> int:
    item = get_item(plan, item_id)
    item["status"] = status
    if note:
        item.setdefault("notes", []).append(f"{utc_now_iso()} {note}")
    if evidence:
        item.setdefault("evidence", []).append(evidence)
    print(f"updated item #{item_id:02d}: status={status}")
    return 0


def cmd_set_focus(plan: dict[str, Any], item_id: int) -> int:
    _ = get_item(plan, item_id)
    plan["active_focus_id"] = item_id
    print(f"active focus set to #{item_id:02d}")
    return 0


def cmd_checkpoint(plan: dict[str, Any], delta: str, next_action: str, blockers: list[str]) -> int:
    focus_id = plan.get("active_focus_id")
    checkpoint = {
        "ts": utc_now_iso(),
        "focus_id": focus_id,
        "delta": delta,
        "next_action": next_action,
        "blockers": blockers,
    }
    plan.setdefault("checkpoints", []).append(checkpoint)
    print("checkpoint recorded")
    return 0


def cmd_park(plan: dict[str, Any], title: str, return_after_id: int | None) -> int:
    entry = {
        "id": f"S{len(plan.get('sidetrack_queue', [])) + 1}",
        "title": title,
        "captured_at": utc_now_iso(),
        "return_after_id": return_after_id,
        "status": "PARKED",
    }
    plan.setdefault("sidetrack_queue", []).append(entry)
    print(f"sidetrack parked: {entry['id']}")
    return 0


def cmd_unpark(plan: dict[str, Any], sidetrack_id: str) -> int:
    for entry in plan.get("sidetrack_queue", []):
        if entry.get("id") == sidetrack_id:
            entry["status"] = "RESOLVED"
            entry["resolved_at"] = utc_now_iso()
            print(f"sidetrack resolved: {sidetrack_id}")
            return 0
    raise SystemExit(f"sidetrack not found: {sidetrack_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Alpha delivery tracker")
    parser.add_argument("--plan", default=str(default_plan_path()), help="Path to alpha plan JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    summary = sub.add_parser("summary", help="Show summary and top actionable items")
    summary.add_argument("--limit", type=int, default=5, help="Number of actionable items to show")

    set_status = sub.add_parser("set-status", help="Update an item status")
    set_status.add_argument("--id", type=int, required=True, help="Item id")
    set_status.add_argument("--status", required=True, choices=sorted(VALID_STATUS), help="New status")
    set_status.add_argument("--note", help="Optional timestamped note")
    set_status.add_argument("--evidence", help="Optional evidence file path")

    set_focus = sub.add_parser("set-focus", help="Set active focus item")
    set_focus.add_argument("--id", type=int, required=True, help="Item id")

    checkpoint = sub.add_parser("checkpoint", help="Record a progress checkpoint")
    checkpoint.add_argument("--delta", required=True, help="What changed")
    checkpoint.add_argument("--next-action", required=True, help="Immediate next action")
    checkpoint.add_argument("--blocker", action="append", default=[], help="Blocker entry")

    park = sub.add_parser("park", help="Park a sidetrack so focus is preserved")
    park.add_argument("--title", required=True, help="Sidetrack summary")
    park.add_argument("--return-after-id", type=int, help="Primary item to finish before returning")

    unpark = sub.add_parser("unpark", help="Mark sidetrack resolved")
    unpark.add_argument("--id", required=True, help="Sidetrack id, e.g. S1")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    plan_path = Path(args.plan)
    plan = load_plan(plan_path)

    if args.command == "summary":
        return cmd_summary(plan, args.limit)
    if args.command == "set-status":
        rc = cmd_set_status(plan, args.id, args.status, args.note, args.evidence)
        save_plan(plan_path, plan)
        return rc
    if args.command == "set-focus":
        rc = cmd_set_focus(plan, args.id)
        save_plan(plan_path, plan)
        return rc
    if args.command == "checkpoint":
        rc = cmd_checkpoint(plan, args.delta, args.next_action, args.blocker)
        save_plan(plan_path, plan)
        return rc
    if args.command == "park":
        rc = cmd_park(plan, args.title, args.return_after_id)
        save_plan(plan_path, plan)
        return rc
    if args.command == "unpark":
        rc = cmd_unpark(plan, args.id)
        save_plan(plan_path, plan)
        return rc

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
