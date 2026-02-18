from dataclasses import dataclass
from enum import Enum


class IntegrityStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_BACKFILLED = "PARTIAL_BACKFILLED"
    INCOMPLETE = "INCOMPLETE"
    STALE = "STALE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class IntegrityReport:
    status: IntegrityStatus
    coverage_pct: float


def can_run_live(report: IntegrityReport, min_coverage_pct: float = 99.5) -> bool:
    return (
        report.coverage_pct >= min_coverage_pct
        and report.status in {IntegrityStatus.COMPLETE, IntegrityStatus.PARTIAL_BACKFILLED}
    )
