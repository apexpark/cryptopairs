from strategy_engine import IntegrityReport, IntegrityStatus, can_run_live


def test_can_run_live_when_complete_and_threshold_met() -> None:
    report = IntegrityReport(status=IntegrityStatus.COMPLETE, coverage_pct=99.5)
    assert can_run_live(report, min_coverage_pct=99.5)


def test_can_run_live_blocks_when_incomplete() -> None:
    report = IntegrityReport(status=IntegrityStatus.INCOMPLETE, coverage_pct=100.0)
    assert not can_run_live(report, min_coverage_pct=99.5)


def test_can_run_live_blocks_when_coverage_below_threshold() -> None:
    report = IntegrityReport(status=IntegrityStatus.PARTIAL_BACKFILLED, coverage_pct=99.4)
    assert not can_run_live(report, min_coverage_pct=99.5)
