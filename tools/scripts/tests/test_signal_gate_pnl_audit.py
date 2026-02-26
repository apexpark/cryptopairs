from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import signal_gate_pnl_audit as audit  # noqa: E402


def test_pair_markers_to_round_trips_pairs_entries_with_next_exit_or_stop() -> None:
    markers = [
        {"index": 2, "kind": "entry"},
        {"index": 4, "kind": "exit"},
        {"index": 5, "kind": "entry"},
        {"index": 8, "kind": "stop"},
    ]
    trips = audit.pair_markers_to_round_trips(markers, point_count=12)
    assert trips == [(2, 4, "exit"), (5, 8, "stop")]


def test_infer_direction_uses_entry_band_sign() -> None:
    assert audit.infer_direction(-1.9, 1.8) == "LONG_SPREAD"
    assert audit.infer_direction(2.1, 1.8) == "SHORT_SPREAD"
    assert audit.infer_direction(0.4, 1.8) is None


def test_compute_leg_returns_bps_long_spread() -> None:
    left_bps, right_bps, gross_bps = audit.compute_leg_returns_bps(
        direction="LONG_SPREAD",
        hedge_ratio=0.5,
        left_entry=100.0,
        left_exit=102.0,
        right_entry=200.0,
        right_exit=198.0,
    )
    assert round(left_bps, 6) == 200.0
    assert round(right_bps, 6) == 50.0
    assert round(gross_bps, 6) == 250.0


def test_compute_leg_returns_bps_short_spread() -> None:
    left_bps, right_bps, gross_bps = audit.compute_leg_returns_bps(
        direction="SHORT_SPREAD",
        hedge_ratio=1.0,
        left_entry=100.0,
        left_exit=98.0,
        right_entry=50.0,
        right_exit=51.0,
    )
    assert round(left_bps, 6) == 200.0
    assert round(right_bps, 6) == 200.0
    assert round(gross_bps, 6) == 400.0


def test_history_index_nearest_respects_tolerance() -> None:
    rows = [
        {
            "pair_id": "PF_A__PF_B",
            "evaluated_at": "2026-02-26T00:00:00Z",
            "actionable": True,
        },
        {
            "pair_id": "PF_A__PF_B",
            "evaluated_at": "2026-02-26T00:01:00Z",
            "actionable": False,
        },
    ]
    index = audit.build_history_index(rows)
    probe_epoch = int(audit.parse_iso("2026-02-26T00:00:30Z").timestamp())
    matched = index.nearest(epoch=probe_epoch, tolerance_seconds=45)
    assert matched is not None
    assert matched["actionable"] is True
    not_matched = index.nearest(epoch=probe_epoch, tolerance_seconds=5)
    assert not_matched is None


def test_compute_equity_trade_bps_uses_pre_entry_to_exit_window() -> None:
    points = [
        {"equity": 1.00},
        {"equity": 0.99},   # entry bar after entry cost
        {"equity": 1.03},   # open trade drift
        {"equity": 1.05},   # exit bar after exit cost
    ]
    pre_entry, exit_equity, trade_bps = audit.compute_equity_trade_bps(points, entry_idx=1, exit_idx=3)
    assert pre_entry == 1.00
    assert exit_equity == 1.05
    assert round(trade_bps, 6) == 500.0
