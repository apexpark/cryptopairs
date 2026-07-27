#!/usr/bin/env python3
"""Inert AUTO-2C governed dynamic-allowlist command scaffold.

AUTO-2C C-b deliberately provides argument-shape compatibility only. It does
not read inputs, evaluate candidates, construct governed decisions, write
artifacts, or confer paper/live eligibility authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence


MODE = "auto2c_governor_scaffold"
DISABLED_DIAGNOSTIC = {
    "artifact_created": False,
    "mode": MODE,
    "status": "DISABLED",
}
NOT_IMPLEMENTED_DIAGNOSTIC = "GOVERNOR_NOT_IMPLEMENTED"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Disabled AUTO-2C scaffold. Candidate evaluation and artifact "
            "creation are not implemented in this slice."
        )
    )
    parser.add_argument(
        "--enabled",
        action="store_true",
        help="Reserved gate; always refuses because the governor is not implemented.",
    )
    parser.add_argument("--current-snapshot-json")
    parser.add_argument("--previous-snapshot-json")
    parser.add_argument("--paper-run-config-json")
    parser.add_argument("--governor-config-json")
    parser.add_argument("--evaluated-at")
    parser.add_argument("--previous-decision-json")
    parser.add_argument("--output-json")
    parser.add_argument("--output-markdown")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.enabled:
        print(NOT_IMPLEMENTED_DIAGNOSTIC, file=sys.stderr)
        return 2

    print(
        json.dumps(DISABLED_DIAGNOSTIC, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
