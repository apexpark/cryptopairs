#!/usr/bin/env python3
"""Independently verify and run one bounded AUTO-2D paper-only trial.

The default invocation performs no file or network I/O. ``--verify-only``
strictly reads and independently recomputes one hash-bound AUTO-2C v2
decision, creating nothing. Only ``--enabled --start`` may create one
exclusive trial root and run the bounded foreground paper loop. The controller
has no live-order, exchange-routing, deployment, service-configuration or
automatic-restart authority.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import autopilot_dynamic_allowlist as common
import autopilot_paper as paper


MODE = "auto2d_bounded_paper_controller"
PROVENANCE_MODE = "auto2d_dynamic_paper_provenance"
POLICY_VERSION = "auto2c-v2-paper-automatic-acceptance-1"
ELIGIBLE_STATUS = "POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION"
PRIOR_SOURCE = "STATIC_PAPER_ALLOWLIST"
ACTIONABLE_DIRECTIONS = {"LONG_SPREAD", "SHORT_SPREAD"}
SELECTOR_DIRECTIONS = {None, "LONG_SPREAD", "NONE", "SHORT_SPREAD"}
CADENCE_SECONDS = 60
PROVENANCE_NAME = "autopilot_dynamic_paper_provenance_v2.jsonl"
BINDING_NAME = "controller_binding.json"
EVENTS_NAME = "controller_events.jsonl"
PAPER_ROOT_NAME = "paper"

DISABLED_DIAGNOSTIC = {
    "mode": MODE,
    "status": "DISABLED",
    "files_read": False,
    "network_accessed": False,
    "artifact_created": False,
    "start_invoked": False,
}

POLICY: dict[str, Any] = {
    "required_comparable_v2_snapshots": 2,
    "min_source_cutoff_separation_seconds": 86400,
    "max_current_source_age_seconds": 1800,
    "min_selector_rows_each_snapshot": 12,
    "min_trade_now_count_each_snapshot": 3,
    "min_trade_now_ratio_each_snapshot": 0.01,
    "require_positive_finite_selector_mean_net_edge": True,
    "max_selected_entries": 4,
    "max_additions": 2,
    "max_selector_exploration_entries": 2,
    "min_selector_exploration_entries_when_qualified_and_transition_safe": 1,
    "max_removals": 2,
    "max_directions_per_pair_variant": 2,
    "max_entries_per_pair_id": 2,
    "max_entries_per_full_instrument": 2,
    "max_new_additions_per_full_instrument": 1,
    "max_churn_ratio": 0.5,
    "churn_measure": "PRIOR_SELECTED_SYMMETRIC_DIFFERENCE",
    "churn_denominator": "MAX_POLICY_CAPACITY_PRIOR_ACTIVE_COUNT",
    "churn_floor_capacity": 4,
    "decision_validity_seconds": 108000,
    "candidate_overflow_behavior": "DETERMINISTIC_TRUNCATE_AND_RECORD",
    "concentration_overflow_behavior": "SKIP_AND_CONTINUE",
    "selection_allocation": (
        "RESERVE_BEST_EXPLORATION_ADDITION_FILL_REALIZED_ALLOW_SECOND_ADDITION"
    ),
    "realized_lane_ranking": (
        "MIN_TOTAL_B2C_SCORE_DESC_MIN_CLOSED_COUNT_DESC_"
        "MIN_TRADE_NOW_RATIO_DESC_EXACT_KEY_ASC"
    ),
    "exploration_lane_ranking": (
        "MIN_TRADE_NOW_RATIO_DESC_MIN_TRADE_NOW_COUNT_DESC_"
        "MIN_SELECTOR_EDGE_DESC_EXACT_KEY_ASC"
    ),
    "fallback_behavior": "NO_FALLBACK",
    "max_simultaneously_open_paper_positions": 2,
    "max_open_paper_positions_per_pair_id": 1,
    "max_open_paper_positions_per_full_instrument": 1,
    "max_open_selector_exploration_positions": 1,
    "max_open_positions_per_exact_key": 1,
    "hold_window_bars": 5,
    "cooldown_seconds": 300,
    "max_candidate_age_seconds": 120,
    "max_automatic_start_decision_age_seconds": 300,
    "entry_window_seconds": 86400,
    "exit_only_grace_seconds": 3600,
    "controller_hard_runtime_seconds": 90000,
}

GOVERNOR_CONFIG = {"policy_version": POLICY_VERSION, "policy": POLICY}
GATE_NAMES = (
    "provenance",
    "current_snapshot_schema",
    "previous_snapshot_schema",
    "snapshot_hash_distinct",
    "selector_config_match",
    "source_cutoff_order",
    "source_cutoff_separation",
    "current_source_freshness",
    "evidence_completeness",
    "direction_domain",
    "evidence_segregation",
    "candidate_qualification",
    "transition_limits",
)
REASON_TO_GATE = {
    "SOURCE_CUTOFF_SEPARATION_TOO_SHORT": "source_cutoff_separation",
    "CURRENT_SOURCE_STALE": "current_source_freshness",
    "NO_QUALIFYING_ENTRIES": "candidate_qualification",
    "TRANSITION_LIMITS_UNSATISFIABLE": "transition_limits",
}

ExactKey = tuple[str, str, str, str]


class ControllerInputError(ValueError):
    """A fail-closed AUTO-2D input or lifecycle refusal."""

    def __init__(
        self,
        code: str,
        *,
        artifact_created: bool = False,
        trial_root: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.artifact_created = artifact_created
        self.trial_root = trial_root


def fail(code: str) -> None:
    raise ControllerInputError(code)


@dataclasses.dataclass(frozen=True)
class SelectorMetrics:
    selector_row_count: int
    trade_now_count: int
    time_in_trade_now_ratio: float
    selector_stated_mean_net_edge_bps: float

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RealizedMetrics:
    total_b2c_score: float
    closed_position_count: int

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SnapshotDetails:
    evidence: common.SnapshotEvidence
    selector_prominent_metrics: Mapping[ExactKey, SelectorMetrics]
    realized_selected_metrics: Mapping[ExactKey, RealizedMetrics]


@dataclasses.dataclass(frozen=True)
class Candidate:
    key: ExactKey
    evidence_class: str
    current_selector: SelectorMetrics
    previous_selector: SelectorMetrics
    current_realized: RealizedMetrics | None
    previous_realized: RealizedMetrics | None
    rank_components: Mapping[str, Any]
    lane_rank: int
    absent_from_prior_active_set: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": common.key_object(self.key),
            "evidence_class": self.evidence_class,
            "current_selector": self.current_selector.as_dict(),
            "previous_selector": self.previous_selector.as_dict(),
            "current_realized": (
                self.current_realized.as_dict()
                if self.current_realized is not None
                else None
            ),
            "previous_realized": (
                self.previous_realized.as_dict()
                if self.previous_realized is not None
                else None
            ),
            "rank_components": dict(self.rank_components),
            "lane_rank": self.lane_rank,
            "absent_from_prior_active_set": self.absent_from_prior_active_set,
        }


@dataclasses.dataclass(frozen=True)
class Selection:
    candidate: Candidate
    sequence: int
    rule: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": common.key_object(self.candidate.key),
            "evidence_class": self.candidate.evidence_class,
            "lane_rank": self.candidate.lane_rank,
            "selection_sequence": self.sequence,
            "selection_rule": self.rule,
        }


@dataclasses.dataclass(frozen=True)
class Verification:
    decision_bound: common.BoundInput
    bound_inputs: tuple[common.BoundInput, ...]
    decision: Mapping[str, Any]
    expected_decision: Mapping[str, Any]
    selected_entries: tuple[Mapping[str, Any], ...]
    evaluated_at: dt.datetime
    valid_until: dt.datetime


@dataclasses.dataclass(frozen=True)
class TrialPaths:
    root: Path
    binding: Path
    provenance: Path
    events: Path
    paper_root: Path


def canonical_bytes(value: object) -> bytes:
    return common.canonical_json_bytes(value)


def json_file_bytes(value: object) -> bytes:
    return canonical_bytes(value) + b"\n"


def format_timestamp(value: dt.datetime) -> str:
    return common.format_timestamp(value)


def policy_envelope_sha256() -> str:
    return hashlib.sha256(
        canonical_bytes({"policy_version": POLICY_VERSION, "policy": POLICY})
    ).hexdigest()


def prior_active_set_sha256(baseline: frozenset[ExactKey]) -> str:
    return hashlib.sha256(
        canonical_bytes([common.key_object(key) for key in sorted(baseline)])
    ).hexdigest()


def decision_id(
    *,
    current_snapshot_sha256: str,
    previous_snapshot_sha256: str,
    paper_run_config_sha256: str,
    governor_config_sha256: str,
    policy_hash: str,
    prior_set_hash: str,
    evaluated_at: str,
) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "current_snapshot_sha256": current_snapshot_sha256,
                "previous_snapshot_sha256": previous_snapshot_sha256,
                "paper_run_config_sha256": paper_run_config_sha256,
                "governor_config_sha256": governor_config_sha256,
                "policy_envelope_sha256": policy_hash,
                "prior_active_set_sha256": prior_set_hash,
                "evaluated_at": evaluated_at,
            }
        )
    ).hexdigest()


def key_text(key: ExactKey) -> str:
    return "|".join(key)


def instrument_ids(key: ExactKey) -> tuple[str, str]:
    parts = key[0].split("__")
    if len(parts) != 2 or not all(parts):
        fail("PAIR_ID_INSTRUMENTS_INVALID")
    return parts[0], parts[1]


def require_distinct_bound_inputs(inputs: Sequence[common.BoundInput]) -> None:
    paths = [str(item.path) for item in inputs]
    identities = [item.stat_identity[:2] for item in inputs]
    if len(paths) != len(set(paths)):
        fail("BOUND_INPUT_PATH_REUSED")
    if len(identities) != len(set(identities)):
        fail("BOUND_INPUT_FILE_REUSED")


def selector_metrics(value: object, field: str) -> SelectorMetrics | None:
    row = common.require_exact_keys(
        value,
        {
            "rows_observed",
            "time_in_tradable_now_ratio",
            "bucket_counts",
            "top_gate_failure_reasons",
        },
        field,
        optional={"score_z_summary", "stated_net_edge_bps_summary"},
    )
    rows = common.require_integer(row["rows_observed"], f"{field}_ROWS")
    counts = common.require_exact_keys(
        row["bucket_counts"],
        {"TRADE_NOW", "WATCHLIST", "EXCLUDED"},
        f"{field}_BUCKETS",
    )
    trade_now = common.require_integer(counts["TRADE_NOW"], f"{field}_TRADE_NOW")
    ratio = common.require_number(row["time_in_tradable_now_ratio"], f"{field}_RATIO")
    assert ratio is not None
    summary = row.get("stated_net_edge_bps_summary")
    if summary is None:
        return None
    summary_row = common.require_exact_keys(
        summary, {"min", "max", "mean"}, f"{field}_EDGE"
    )
    mean = common.require_number(
        summary_row["mean"], f"{field}_EDGE_MEAN", nullable=True
    )
    if mean is None:
        return None
    if (
        rows < POLICY["min_selector_rows_each_snapshot"]
        or trade_now < POLICY["min_trade_now_count_each_snapshot"]
        or ratio < POLICY["min_trade_now_ratio_each_snapshot"]
        or mean <= 0
    ):
        return None
    return SelectorMetrics(rows, trade_now, ratio, mean)


def extract_selector_metrics(
    snapshot: common.SnapshotEvidence, role: str
) -> dict[ExactKey, SelectorMetrics]:
    selector_view = snapshot.bound.payload.get("selector_view")
    if not isinstance(selector_view, dict):
        fail(f"{role}_SELECTOR_VIEW_MISSING")
    values = selector_view.get("selector_view_prominent")
    if not isinstance(values, list):
        fail(f"{role}_SELECTOR_PROMINENT_INVALID")
    result: dict[ExactKey, SelectorMetrics] = {}
    for index, value in enumerate(values):
        row = common.require_exact_keys(
            value,
            {
                "pair_id",
                "timeframe",
                "selected_variant",
                "direction",
                "evidence_kind",
                "metrics",
            },
            f"{role}_SELECTOR_PROMINENT_{index}",
        )
        direction = row["direction"]
        if direction in {None, "NONE"}:
            continue
        if direction not in ACTIONABLE_DIRECTIONS:
            fail("UNKNOWN_SELECTOR_DIRECTION")
        key = common.exact_key_from_object(
            {
                "pair_id": row["pair_id"],
                "timeframe": row["timeframe"],
                "selected_variant": row["selected_variant"],
                "direction": direction,
            },
            f"{role}_SELECTOR_PROMINENT_{index}",
        )
        metrics = selector_metrics(
            row["metrics"], f"{role}_SELECTOR_PROMINENT_{index}_METRICS"
        )
        if metrics is not None:
            result[key] = metrics
    return result


def extract_realized_metrics(
    snapshot: common.SnapshotEvidence, role: str
) -> dict[ExactKey, RealizedMetrics]:
    values = snapshot.bound.payload["selected"]
    if not isinstance(values, list):
        fail(f"{role}_SELECTED_NOT_ARRAY")
    result: dict[ExactKey, RealizedMetrics] = {}
    for index, value in enumerate(values):
        row = common.require_exact_keys(
            value,
            {
                "pair_id",
                "timeframe",
                "selected_variant",
                "direction",
                "decision",
                "reason_codes",
                "metrics",
                "score_components",
            },
            f"{role}_SELECTED_{index}",
        )
        if row["direction"] not in ACTIONABLE_DIRECTIONS:
            fail("REALIZED_DIRECTION_NON_ACTIONABLE")
        key = common.exact_key_from_object(
            {
                "pair_id": row["pair_id"],
                "timeframe": row["timeframe"],
                "selected_variant": row["selected_variant"],
                "direction": row["direction"],
            },
            f"{role}_SELECTED_{index}",
        )
        metrics = common.require_exact_keys(
            row["metrics"],
            {
                "closed_positions",
                "profitable_closed_positions",
                "losing_closed_positions",
                "win_rate",
                "sum_realized_net_bps",
                "avg_realized_net_bps",
                "max_loss_bps",
                "avg_exit_lag_seconds",
                "max_exit_lag_seconds",
                "first_entry_at",
                "last_exit_at",
            },
            f"{role}_SELECTED_{index}_METRICS",
        )
        score = common.require_exact_keys(
            row["score_components"],
            {
                "avg_net_bps",
                "win_rate_bonus",
                "sample_size_bonus",
                "tail_loss_penalty",
                "exit_lag_penalty",
                "total_score",
            },
            f"{role}_SELECTED_{index}_SCORE",
        )
        total = common.require_number(
            score["total_score"], f"{role}_SELECTED_{index}_TOTAL_SCORE"
        )
        assert total is not None
        result[key] = RealizedMetrics(
            total_b2c_score=total,
            closed_position_count=common.require_integer(
                metrics["closed_positions"],
                f"{role}_SELECTED_{index}_CLOSED",
                1,
            ),
        )
    return result


def validate_all_selector_directions(
    snapshot: common.SnapshotEvidence, role: str
) -> None:
    selector_view = snapshot.bound.payload.get("selector_view")
    if not isinstance(selector_view, dict):
        fail(f"{role}_SELECTOR_VIEW_MISSING")
    for collection_name in ("selector_view_prominent", "selector_view_marginal"):
        values = selector_view.get(collection_name)
        if not isinstance(values, list):
            fail(f"{role}_{collection_name.upper()}_INVALID")
        for value in values:
            if not isinstance(value, dict):
                fail(f"{role}_{collection_name.upper()}_ROW_INVALID")
            direction = value.get("direction")
            if direction not in SELECTOR_DIRECTIONS:
                fail("UNKNOWN_SELECTOR_DIRECTION")


def validate_snapshot_v2(bound: common.BoundInput, role: str) -> SnapshotDetails:
    try:
        evidence = common.validate_snapshot(bound, role)
    except common.GovernorInputError as error:
        fail(str(error))
    if evidence.schema_version != 2:
        fail(f"{role}_SNAPSHOT_NOT_SCHEMA_V2")
    if (
        evidence.selector_prominent is None
        or evidence.selector_marginal is None
        or not evidence.selector_churn_available
    ):
        fail(f"{role}_SELECTOR_EVIDENCE_INCOMPLETE")
    if evidence.generated_at.microsecond or evidence.source_cutoff_at.microsecond:
        fail(f"{role}_SNAPSHOT_TIMESTAMP_NOT_CANONICAL_SECONDS")
    validate_all_selector_directions(evidence, role)
    return SnapshotDetails(
        evidence=evidence,
        selector_prominent_metrics=extract_selector_metrics(evidence, role),
        realized_selected_metrics=extract_realized_metrics(evidence, role),
    )


def candidate_rank(candidate: Candidate) -> tuple[Any, ...]:
    rank = candidate.rank_components
    if candidate.evidence_class == "REALIZED_AND_SELECTOR":
        return (
            -float(rank["minimum_total_b2c_score"]),
            -int(rank["minimum_closed_position_count"]),
            -float(rank["minimum_trade_now_ratio"]),
            candidate.key,
        )
    return (
        -float(rank["minimum_trade_now_ratio"]),
        -int(rank["minimum_trade_now_count"]),
        -float(rank["minimum_selector_stated_mean_net_edge_bps"]),
        candidate.key,
    )


def build_candidates(
    current: SnapshotDetails,
    previous: SnapshotDetails,
    baseline: frozenset[ExactKey],
) -> list[Candidate]:
    selector_keys = set(current.selector_prominent_metrics) & set(
        previous.selector_prominent_metrics
    )
    realized: list[Candidate] = []
    exploration: list[Candidate] = []
    for key in sorted(selector_keys):
        current_realized_sets = (
            current.evidence.selected
            | current.evidence.rejected
            | current.evidence.quarantined
        )
        previous_realized_sets = (
            previous.evidence.selected
            | previous.evidence.rejected
            | previous.evidence.quarantined
        )
        selected_both = (
            key in current.evidence.selected and key in previous.evidence.selected
        )
        absent_both = (
            key not in current_realized_sets and key not in previous_realized_sets
        )
        if selected_both and key in baseline:
            evidence_class = "REALIZED_AND_SELECTOR"
            current_realized = current.realized_selected_metrics[key]
            previous_realized = previous.realized_selected_metrics[key]
        elif absent_both and key not in baseline:
            evidence_class = "SELECTOR_EXPLORATION"
            current_realized = None
            previous_realized = None
        else:
            continue
        current_selector = current.selector_prominent_metrics[key]
        previous_selector = previous.selector_prominent_metrics[key]
        rank_components: dict[str, Any] = {
            "minimum_total_b2c_score": (
                min(
                    current_realized.total_b2c_score,
                    previous_realized.total_b2c_score,
                )
                if current_realized is not None and previous_realized is not None
                else None
            ),
            "minimum_closed_position_count": (
                min(
                    current_realized.closed_position_count,
                    previous_realized.closed_position_count,
                )
                if current_realized is not None and previous_realized is not None
                else None
            ),
            "minimum_trade_now_ratio": min(
                current_selector.time_in_trade_now_ratio,
                previous_selector.time_in_trade_now_ratio,
            ),
            "minimum_trade_now_count": min(
                current_selector.trade_now_count,
                previous_selector.trade_now_count,
            ),
            "minimum_selector_stated_mean_net_edge_bps": min(
                current_selector.selector_stated_mean_net_edge_bps,
                previous_selector.selector_stated_mean_net_edge_bps,
            ),
            "exact_key_tiebreak": key_text(key),
        }
        candidate = Candidate(
            key=key,
            evidence_class=evidence_class,
            current_selector=current_selector,
            previous_selector=previous_selector,
            current_realized=current_realized,
            previous_realized=previous_realized,
            rank_components=rank_components,
            lane_rank=0,
            absent_from_prior_active_set=key not in baseline,
        )
        if evidence_class == "REALIZED_AND_SELECTOR":
            realized.append(candidate)
        else:
            exploration.append(candidate)
    ranked: list[Candidate] = []
    for lane in (realized, exploration):
        for index, candidate in enumerate(sorted(lane, key=candidate_rank), start=1):
            ranked.append(dataclasses.replace(candidate, lane_rank=index))
    return ranked


def concentration_failure(
    selected: Sequence[Candidate],
    candidate: Candidate,
    baseline: frozenset[ExactKey],
) -> str | None:
    prospective = [item.key for item in selected] + [candidate.key]
    pair_counts = Counter(key[0] for key in prospective)
    if pair_counts[candidate.key[0]] > POLICY["max_entries_per_pair_id"]:
        return "SKIPPED_PAIR_CONCENTRATION"
    pair_variant = candidate.key[:3]
    pair_variant_count = sum(key[:3] == pair_variant for key in prospective)
    if pair_variant_count > POLICY["max_directions_per_pair_variant"]:
        return "SKIPPED_PAIR_VARIANT_DIRECTION_CONCENTRATION"
    instrument_counts: Counter[str] = Counter()
    addition_instrument_counts: Counter[str] = Counter()
    for key in prospective:
        for instrument in instrument_ids(key):
            instrument_counts[instrument] += 1
            if key not in baseline:
                addition_instrument_counts[instrument] += 1
    if any(
        count > POLICY["max_entries_per_full_instrument"]
        for count in instrument_counts.values()
    ):
        return "SKIPPED_INSTRUMENT_CONCENTRATION"
    if any(
        count > POLICY["max_new_additions_per_full_instrument"]
        for count in addition_instrument_counts.values()
    ):
        return "SKIPPED_ADDITION_INSTRUMENT_CONCENTRATION"
    return None


def outcome(candidate: Candidate, reason: str) -> dict[str, Any]:
    return {
        "key": common.key_object(candidate.key),
        "evidence_class": candidate.evidence_class,
        "lane_rank": candidate.lane_rank,
        "reason_code": reason,
    }


def transition_counts(
    keys: Sequence[ExactKey], baseline: frozenset[ExactKey]
) -> tuple[int, int, int, float]:
    proposed = frozenset(keys)
    additions = proposed - baseline
    removals = baseline - proposed
    changes = len(additions) + len(removals)
    denominator = max(POLICY["churn_floor_capacity"], len(baseline))
    return len(additions), len(removals), changes, changes / denominator


def reservation_transition_safety(
    exploration: Candidate,
    realized: Sequence[Candidate],
    baseline: frozenset[ExactKey],
) -> tuple[bool, str | None]:
    simulated = [exploration]
    first_concentration_failure: str | None = None
    for realized_candidate in realized:
        if len(simulated) >= POLICY["max_selected_entries"]:
            break
        reason = concentration_failure(simulated, realized_candidate, baseline)
        if reason is not None:
            if first_concentration_failure is None:
                first_concentration_failure = reason
            continue
        simulated.append(realized_candidate)
    selections = [
        Selection(item, index, "RESERVATION_TRANSITION_SAFETY_CHECK")
        for index, item in enumerate(simulated, 1)
    ]
    return (
        transition_is_valid(selections, [exploration], baseline),
        first_concentration_failure,
    )


def allocate_candidates(
    candidates: Sequence[Candidate],
    baseline: frozenset[ExactKey],
) -> tuple[
    list[Selection],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    realized = [
        item for item in candidates if item.evidence_class == "REALIZED_AND_SELECTOR"
    ]
    exploration = [
        item for item in candidates if item.evidence_class == "SELECTOR_EXPLORATION"
    ]
    selected: list[Candidate] = []
    selections: list[Selection] = []
    steps: list[dict[str, Any]] = []
    truncated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    processed: set[ExactKey] = set()

    def record_skip(candidate: Candidate, reason: str) -> None:
        processed.add(candidate.key)
        skipped.append(outcome(candidate, reason))
        steps.append(
            {
                "step": len(steps) + 1,
                "rule": "SKIP_CONCENTRATION_AND_CONTINUE",
                "candidate_key": common.key_object(candidate.key),
                "result": "SKIPPED",
            }
        )

    def process(candidate: Candidate, rule: str) -> None:
        if candidate.key in processed:
            return
        result = "SELECTED"
        step_rule = rule
        if len(selected) >= POLICY["max_selected_entries"]:
            result = "TRUNCATED"
            reason = "TRUNCATED_MAX_SELECTED_ENTRIES"
            truncated.append(outcome(candidate, reason))
            step_rule = "TRUNCATE_AT_CAPACITY"
        elif (
            candidate.key not in baseline
            and sum(item.key not in baseline for item in selected)
            >= POLICY["max_additions"]
        ):
            result = "SKIPPED"
            reason = "SKIPPED_MAX_ADDITIONS"
            skipped.append(outcome(candidate, reason))
            step_rule = "SKIP_CONCENTRATION_AND_CONTINUE"
        else:
            reason = concentration_failure(selected, candidate, baseline)
            if reason is not None:
                result = "SKIPPED"
                skipped.append(outcome(candidate, reason))
                step_rule = "SKIP_CONCENTRATION_AND_CONTINUE"
            else:
                selected.append(candidate)
                selections.append(Selection(candidate, len(selected), rule))
        steps.append(
            {
                "step": len(steps) + 1,
                "rule": step_rule,
                "candidate_key": common.key_object(candidate.key),
                "result": result,
            }
        )
        processed.add(candidate.key)

    for candidate in exploration:
        transition_safe, reason = reservation_transition_safety(
            candidate, realized, baseline
        )
        if not transition_safe and reason is not None:
            record_skip(candidate, reason)
            continue
        process(candidate, "RESERVE_BEST_QUALIFYING_ADDITION")
        if candidate.key in {item.key for item in selected}:
            break
    for candidate in realized:
        process(candidate, "FILL_REALIZED_SUPPORTED")
    exploration_selected = sum(
        item.evidence_class == "SELECTOR_EXPLORATION" for item in selected
    )
    for candidate in exploration:
        if candidate.key in processed:
            continue
        if exploration_selected >= POLICY["max_selector_exploration_entries"]:
            process(candidate, "FILL_SECOND_QUALIFYING_ADDITION")
            continue
        before = len(selected)
        process(candidate, "FILL_SECOND_QUALIFYING_ADDITION")
        if len(selected) > before:
            exploration_selected += 1
    return selections, steps, truncated, skipped


def transition_is_valid(
    selections: Sequence[Selection],
    candidates: Sequence[Candidate],
    baseline: frozenset[ExactKey],
) -> bool:
    proposed = frozenset(item.candidate.key for item in selections)
    additions = proposed - baseline
    removals = baseline - proposed
    change_count = len(additions) + len(removals)
    denominator = max(POLICY["churn_floor_capacity"], len(baseline))
    churn = change_count / denominator
    exploration_qualifies = any(
        item.evidence_class == "SELECTOR_EXPLORATION" for item in candidates
    )
    exploration_selected = sum(
        item.candidate.evidence_class == "SELECTOR_EXPLORATION" for item in selections
    )
    pair_counts = Counter(key[0] for key in proposed)
    pair_variant_counts = Counter((key[0], key[1], key[2]) for key in proposed)
    instrument_counts: Counter[str] = Counter()
    addition_instrument_counts: Counter[str] = Counter()
    for key in proposed:
        for instrument in instrument_ids(key):
            instrument_counts[instrument] += 1
            if key in additions:
                addition_instrument_counts[instrument] += 1
    return bool(proposed) and all(
        (
            len(proposed) <= POLICY["max_selected_entries"],
            len(additions) <= POLICY["max_additions"],
            len(removals) <= POLICY["max_removals"],
            exploration_selected <= POLICY["max_selector_exploration_entries"],
            (
                not exploration_qualifies
                or exploration_selected
                >= POLICY[
                    "min_selector_exploration_entries_when_qualified_and_transition_safe"
                ]
            ),
            churn <= POLICY["max_churn_ratio"],
            all(
                count <= POLICY["max_entries_per_pair_id"]
                for count in pair_counts.values()
            ),
            all(
                count <= POLICY["max_directions_per_pair_variant"]
                for count in pair_variant_counts.values()
            ),
            all(
                count <= POLICY["max_entries_per_full_instrument"]
                for count in instrument_counts.values()
            ),
            all(
                count <= POLICY["max_new_additions_per_full_instrument"]
                for count in addition_instrument_counts.values()
            ),
        )
    )


def gate_results(
    reasons: Sequence[str],
) -> tuple[dict[str, Any], dict[str, int]]:
    grouped: dict[str, list[str]] = {name: [] for name in GATE_NAMES}
    for reason in reasons:
        grouped[REASON_TO_GATE[reason]].append(reason)
    results = {
        name: {
            "verdict": "BLOCK" if grouped[name] else "PASS",
            "reason_codes": grouped[name],
        }
        for name in GATE_NAMES
    }
    blocked = sum(value["verdict"] == "BLOCK" for value in results.values())
    return results, {
        "pass_count": len(GATE_NAMES) - blocked,
        "block_count": blocked,
        "total_count": len(GATE_NAMES),
    }


def snapshot_reference(
    snapshot: SnapshotDetails, producer_git_sha: str
) -> dict[str, Any]:
    evidence = snapshot.evidence
    return {
        "path": str(evidence.bound.path),
        "sha256": evidence.bound.sha256,
        "producer_git_sha": producer_git_sha,
        "schema_version": 2,
        "generated_at": format_timestamp(evidence.generated_at),
        "source_cutoff_at": format_timestamp(evidence.source_cutoff_at),
        "selector_config_sha256": hashlib.sha256(
            canonical_bytes(common.SELECTOR_CONFIG)
        ).hexdigest(),
        "selector_view_present": True,
        "selector_view_churn_available": True,
    }


def concentration_calculations(
    proposed: frozenset[ExactKey],
    additions: frozenset[ExactKey],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    pairs = Counter(key[0] for key in proposed)
    pair_variants = Counter((key[0], key[1], key[2]) for key in proposed)
    instruments: Counter[str] = Counter()
    addition_instruments: Counter[str] = Counter()
    for key in proposed:
        for instrument in instrument_ids(key):
            instruments[instrument] += 1
            if key in additions:
                addition_instruments[instrument] += 1
    return (
        [
            {"pair_id": pair_id, "entry_count": count}
            for pair_id, count in sorted(pairs.items())
        ],
        [
            {
                "pair_id": pair_id,
                "timeframe": timeframe,
                "selected_variant": variant,
                "direction_count": count,
            }
            for (pair_id, timeframe, variant), count in sorted(pair_variants.items())
        ],
        [
            {
                "instrument_id": instrument,
                "entry_count": count,
                "addition_count": addition_instruments[instrument],
            }
            for instrument, count in sorted(instruments.items())
        ],
    )


def build_expected_decision(
    *,
    current: SnapshotDetails,
    previous: SnapshotDetails,
    baseline: frozenset[ExactKey],
    paper_bound: common.BoundInput,
    governor_bound: common.BoundInput,
    current_producer_git_sha: str,
    previous_producer_git_sha: str,
    paper_producer_git_sha: str,
    evaluated_at: dt.datetime,
) -> dict[str, Any]:
    if current.evidence.bound.sha256 == previous.evidence.bound.sha256:
        fail("SNAPSHOT_HASH_REUSED")
    if current.evidence.source_cutoff_at <= previous.evidence.source_cutoff_at:
        fail("SOURCE_CUTOFF_ORDER_INVALID")
    if current.evidence.source_cutoff_at > evaluated_at:
        fail("CURRENT_SOURCE_FROM_FUTURE")
    try:
        common.validate_static_comparison(current.evidence, baseline, "CURRENT")
        common.validate_static_comparison(previous.evidence, baseline, "PREVIOUS")
        common.validate_current_churn(current.evidence, previous.evidence)
    except common.GovernorInputError as error:
        fail(str(error))

    separation_seconds = (
        current.evidence.source_cutoff_at - previous.evidence.source_cutoff_at
    ).total_seconds()
    age_seconds = (evaluated_at - current.evidence.source_cutoff_at).total_seconds()
    separation = int(separation_seconds)
    age = int(age_seconds)
    reasons: list[str] = []
    if separation_seconds < POLICY["min_source_cutoff_separation_seconds"]:
        reasons.append("SOURCE_CUTOFF_SEPARATION_TOO_SHORT")
    if age_seconds > POLICY["max_current_source_age_seconds"]:
        reasons.append("CURRENT_SOURCE_STALE")

    candidates: list[Candidate] = []
    selections: list[Selection] = []
    steps: list[dict[str, Any]] = []
    truncated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    early_block = bool(reasons)
    if not early_block:
        candidates = build_candidates(current, previous, baseline)
        if not candidates:
            reasons.append("NO_QUALIFYING_ENTRIES")
            early_block = True
    if not early_block:
        selections, steps, truncated, skipped = allocate_candidates(
            candidates, baseline
        )
        if not transition_is_valid(selections, candidates, baseline):
            reasons.append("TRANSITION_LIMITS_UNSATISFIABLE")
            selections = []
            steps = []
            truncated = []
            skipped = []

    status = "GOVERNOR_BLOCKED" if reasons else ELIGIBLE_STATUS
    proposed = frozenset(item.candidate.key for item in selections)
    additions = proposed - baseline if not reasons else frozenset()
    removals = baseline - proposed if not reasons else frozenset()
    retained = proposed & baseline if not reasons else frozenset()
    change_count = len(additions) + len(removals)
    churn_denominator = max(POLICY["churn_floor_capacity"], len(baseline))
    churn_ratio = change_count / churn_denominator if selections else 0
    pair_counts, pair_variant_counts, instrument_counts = concentration_calculations(
        proposed, additions
    )
    gates, gate_summary = gate_results(reasons)
    evaluated_text = format_timestamp(evaluated_at)
    valid_until = format_timestamp(
        evaluated_at + dt.timedelta(seconds=POLICY["decision_validity_seconds"])
    )
    policy_hash = policy_envelope_sha256()
    prior_hash = prior_active_set_sha256(baseline)
    return {
        "schema_version": 2,
        "mode": "governed_dynamic_allowlist_decision",
        "policy_version": POLICY_VERSION,
        "decision_id": decision_id(
            current_snapshot_sha256=current.evidence.bound.sha256,
            previous_snapshot_sha256=previous.evidence.bound.sha256,
            paper_run_config_sha256=paper_bound.sha256,
            governor_config_sha256=governor_bound.sha256,
            policy_hash=policy_hash,
            prior_set_hash=prior_hash,
            evaluated_at=evaluated_text,
        ),
        "policy_envelope_sha256": policy_hash,
        "status": status,
        "evaluated_at": evaluated_text,
        "valid_until": valid_until,
        "current_snapshot": snapshot_reference(current, current_producer_git_sha),
        "previous_snapshot": snapshot_reference(previous, previous_producer_git_sha),
        "paper_run_config": {
            "path": str(paper_bound.path),
            "sha256": paper_bound.sha256,
            "producer_git_sha": paper_producer_git_sha,
            "static_allowlist_mode": "pair_variant_direction",
            "static_allowlist_entry_count": len(baseline),
        },
        "governor_config_source": {
            "path": str(governor_bound.path),
            "sha256": governor_bound.sha256,
        },
        "selector_config": common.SELECTOR_CONFIG,
        "policy": POLICY,
        "prior_active_set_source": PRIOR_SOURCE,
        "prior_active_set_sha256": prior_hash,
        "prior_active_entries": [common.key_object(key) for key in sorted(baseline)],
        "candidates": [candidate.as_dict() for candidate in candidates],
        "selection_steps": steps,
        "selected_entries": [selection.as_dict() for selection in selections],
        "truncated_candidates": truncated,
        "skipped_candidates": skipped,
        "additions": [common.key_object(key) for key in sorted(additions)],
        "removals": [common.key_object(key) for key in sorted(removals)],
        "retained_entries": [common.key_object(key) for key in sorted(retained)],
        "direction_counts": dict(current.evidence.direction_counts),
        "gate_results": gates,
        "gate_summary": gate_summary,
        "calculations": {
            "source_cutoff_separation_seconds": separation,
            "current_source_age_seconds": age,
            "prior_active_entry_count": len(baseline),
            "qualifying_candidate_count": len(candidates),
            "selected_entry_count": len(selections),
            "selector_exploration_selected_count": sum(
                item.candidate.evidence_class == "SELECTOR_EXPLORATION"
                for item in selections
            ),
            "addition_count": len(additions),
            "removal_count": len(removals),
            "change_count": change_count,
            "churn_denominator_count": churn_denominator,
            "churn_ratio": churn_ratio,
            "pair_concentrations": pair_counts,
            "pair_variant_concentrations": pair_variant_counts,
            "instrument_concentrations": instrument_counts,
        },
        "reason_codes": reasons,
        "methodology": {
            "realized_selector_relation": (
                "SEPARATE_STREAMS_SET_MEMBERSHIP_NO_NUMERIC_MERGE"
            ),
            "none_direction_behavior": "NON_ACTIONABLE_DISTINCT_FROM_NULL",
            "null_direction_behavior": "NON_ACTIONABLE_MISSING_DIRECTION",
            "unknown_direction_behavior": "REJECT_INPUT_NO_ARTIFACT",
            "candidate_overflow_behavior": ("DETERMINISTIC_TRUNCATE_AND_RECORD"),
            "concentration_overflow_behavior": "SKIP_AND_CONTINUE",
            "selection_allocation": (
                "RESERVE_BEST_EXPLORATION_ADDITION_FILL_REALIZED_ALLOW_SECOND_ADDITION"
            ),
            "fallback_behavior": "NO_FALLBACK",
            "policy_hash_formula": ("SHA256_CANONICAL_JSON_POLICY_VERSION_AND_POLICY"),
            "decision_id_formula": (
                "SHA256_CANONICAL_JSON_BOUND_INPUT_HASHES_POLICY_HASH_"
                "PRIOR_SET_HASH_EVALUATED_AT"
            ),
            "serialization_behavior": ("MINIFIED_KEY_SORTED_UTF8_NO_TRAILING_NEWLINE"),
            "input_behavior": "READ_ONLY_RAW_HASH_BOUND_STABLE_FILES",
            "output_behavior": ("EXCLUSIVE_CREATE_NO_OVERWRITE_REPAIR_OR_REUSE"),
        },
        "per_output_operator_approval_required": False,
        "auto2d_verification": {
            "independent_recomputation_required": True,
            "policy_envelope_hash_match_required": True,
            "decision_hash_match_required": True,
            "raw_input_hash_recheck_required": True,
            "immutable_universe_required": True,
            "schema_v1_decision_accepted": False,
            "raw_snapshot_accepted_as_decision": False,
            "governor_self_approval_accepted": False,
        },
        "authority": ("non_actuating_requires_independent_auto2d_verification"),
        "authority_boundaries": {
            "paper_eligibility_authority": False,
            "paper_configuration_write_authority": False,
            "paper_trial_start_authority": False,
            "live_eligibility_authority": False,
            "execution_authority": False,
            "deployment_authority": False,
            "governor_self_approval_authority": False,
        },
    }


def require_git_sha(value: str | None, field: str) -> str:
    try:
        return common.require_git_sha(value, field)
    except common.GovernorInputError as error:
        fail(str(error))


def require_absolute_path(value: str | None, field: str) -> Path:
    try:
        return common.require_absolute_path(value, field)
    except common.GovernorInputError as error:
        fail(str(error))


def read_bound_input(
    path_value: str | None, expected_sha256: str | None, source: str
) -> common.BoundInput:
    try:
        return common.read_bound_input(path_value, expected_sha256, source)
    except common.GovernorInputError as error:
        fail(str(error))


def parse_required_timestamp(value: object, field: str) -> dt.datetime:
    try:
        parsed = common.parse_timestamp(value, field)
    except common.GovernorInputError as error:
        fail(str(error))
    if parsed.microsecond:
        fail(f"{field}_NOT_CANONICAL_SECONDS")
    return parsed


def validate_governor_config(bound: common.BoundInput) -> None:
    if bound.payload != GOVERNOR_CONFIG:
        fail("GOVERNOR_CONFIG_MISMATCH")


def validate_paper_config(
    bound: common.BoundInput,
) -> frozenset[ExactKey]:
    try:
        baseline = common.validate_paper_config(bound)
    except common.GovernorInputError as error:
        fail(str(error))
    return baseline


def read_and_verify(args: argparse.Namespace) -> Verification:
    current_producer = require_git_sha(
        args.current_snapshot_producer_git_sha,
        "CURRENT_SNAPSHOT_PRODUCER_GIT_SHA",
    )
    previous_producer = require_git_sha(
        args.previous_snapshot_producer_git_sha,
        "PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA",
    )
    paper_producer = require_git_sha(
        args.paper_run_config_producer_git_sha,
        "PAPER_RUN_CONFIG_PRODUCER_GIT_SHA",
    )
    evaluated_at = parse_required_timestamp(args.evaluated_at, "EVALUATED_AT")
    if args.prior_active_set_source != PRIOR_SOURCE:
        fail("PRIOR_ACTIVE_SET_SOURCE_UNSUPPORTED")

    decision_bound = read_bound_input(
        args.decision_json, args.decision_sha256, "DECISION"
    )
    current_bound = read_bound_input(
        args.current_snapshot_json,
        args.current_snapshot_sha256,
        "CURRENT_SNAPSHOT",
    )
    previous_bound = read_bound_input(
        args.previous_snapshot_json,
        args.previous_snapshot_sha256,
        "PREVIOUS_SNAPSHOT",
    )
    paper_bound = read_bound_input(
        args.paper_run_config_json,
        args.paper_run_config_sha256,
        "PAPER_RUN_CONFIG",
    )
    governor_bound = read_bound_input(
        args.governor_config_json,
        args.governor_config_sha256,
        "GOVERNOR_CONFIG",
    )
    bound_inputs = (
        decision_bound,
        current_bound,
        previous_bound,
        paper_bound,
        governor_bound,
    )
    require_distinct_bound_inputs(bound_inputs)
    current = validate_snapshot_v2(current_bound, "CURRENT")
    previous = validate_snapshot_v2(previous_bound, "PREVIOUS")
    baseline = validate_paper_config(paper_bound)
    validate_governor_config(governor_bound)
    expected = build_expected_decision(
        current=current,
        previous=previous,
        baseline=baseline,
        paper_bound=paper_bound,
        governor_bound=governor_bound,
        current_producer_git_sha=current_producer,
        previous_producer_git_sha=previous_producer,
        paper_producer_git_sha=paper_producer,
        evaluated_at=evaluated_at,
    )
    decision = decision_bound.payload
    if decision != expected:
        fail("DECISION_INDEPENDENT_RECOMPUTATION_MISMATCH")
    if decision.get("status") != ELIGIBLE_STATUS:
        fail("DECISION_NOT_ELIGIBLE")
    if decision.get("reason_codes") != []:
        fail("DECISION_HAS_REASON_CODES")
    if decision.get("authority_boundaries") != {
        "paper_eligibility_authority": False,
        "paper_configuration_write_authority": False,
        "paper_trial_start_authority": False,
        "live_eligibility_authority": False,
        "execution_authority": False,
        "deployment_authority": False,
        "governor_self_approval_authority": False,
    }:
        fail("DECISION_AUTHORITY_BOUNDARY_INVALID")
    selected = decision.get("selected_entries")
    if not isinstance(selected, list) or not 1 <= len(selected) <= 4:
        fail("DECISION_SELECTED_UNIVERSE_INVALID")
    selected_entries = tuple(selected)
    selected_keys: set[ExactKey] = set()
    for index, item in enumerate(selected_entries):
        if not isinstance(item, dict):
            fail(f"DECISION_SELECTED_{index}_INVALID")
        key = common.exact_key_from_object(
            item.get("key"), f"DECISION_SELECTED_{index}"
        )
        if key in selected_keys:
            fail("DECISION_SELECTED_DUPLICATE")
        selected_keys.add(key)
        if item.get("evidence_class") not in {
            "REALIZED_AND_SELECTOR",
            "SELECTOR_EXPLORATION",
        }:
            fail("DECISION_SELECTION_ORIGIN_INVALID")
        if item.get("selection_sequence") != index + 1:
            fail("DECISION_SELECTION_ORDER_INVALID")
    valid_until = parse_required_timestamp(
        decision.get("valid_until"), "DECISION_VALID_UNTIL"
    )
    if valid_until != evaluated_at + dt.timedelta(
        seconds=POLICY["decision_validity_seconds"]
    ):
        fail("DECISION_VALID_UNTIL_MISMATCH")
    for source, bound in (
        ("DECISION", decision_bound),
        ("CURRENT_SNAPSHOT", current_bound),
        ("PREVIOUS_SNAPSHOT", previous_bound),
        ("PAPER_RUN_CONFIG", paper_bound),
        ("GOVERNOR_CONFIG", governor_bound),
    ):
        try:
            common.recheck_bound_input(bound, source)
        except common.GovernorInputError as error:
            fail(str(error))
    return Verification(
        decision_bound=decision_bound,
        bound_inputs=bound_inputs,
        decision=decision,
        expected_decision=expected,
        selected_entries=selected_entries,
        evaluated_at=evaluated_at,
        valid_until=valid_until,
    )


def recheck_verification_inputs(verification: Verification) -> None:
    sources = (
        "DECISION",
        "CURRENT_SNAPSHOT",
        "PREVIOUS_SNAPSHOT",
        "PAPER_RUN_CONFIG",
        "GOVERNOR_CONFIG",
    )
    for source, bound in zip(sources, verification.bound_inputs):
        try:
            common.recheck_bound_input(bound, source)
        except common.GovernorInputError as error:
            fail(str(error))


def trial_id(decision_id_value: str) -> str:
    return f"auto2d-paper-v2-{decision_id_value}"


def require_loopback_get_url(value: str | None) -> str:
    if not isinstance(value, str) or not value:
        fail("MARKS_URL_REQUIRED")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ControllerInputError("MARKS_URL_NOT_GET_ONLY_LOOPBACK") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path
    ):
        fail("MARKS_URL_NOT_GET_ONLY_LOOPBACK")
    if port is None:
        fail("MARKS_URL_EXPLICIT_PORT_REQUIRED")
    return value


def require_existing_directory(path: Path, field: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ControllerInputError(f"{field}_MISSING") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        fail(f"{field}_NOT_REAL_DIRECTORY")


def require_observe_source(path_value: str | None) -> tuple[Path, tuple[int, int]]:
    path = require_absolute_path(path_value, "OBSERVE_SOURCE_PATH")
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ControllerInputError("OBSERVE_SOURCE_MISSING") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        fail("OBSERVE_SOURCE_NOT_REGULAR")
    return path, (metadata.st_dev, metadata.st_ino)


def verify_repository(
    root_value: str | None, expected_git_sha: str | None
) -> tuple[Path, str]:
    root = require_absolute_path(root_value, "REPOSITORY_ROOT")
    require_existing_directory(root, "REPOSITORY_ROOT")
    expected = require_git_sha(expected_git_sha, "REPOSITORY_GIT_SHA")

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            fail("REPOSITORY_GIT_INSPECTION_FAILED")
        return result.stdout.strip()

    if Path(git("rev-parse", "--show-toplevel")) != root:
        fail("REPOSITORY_ROOT_MISMATCH")
    if git("rev-parse", "HEAD") != expected:
        fail("REPOSITORY_HEAD_MISMATCH")
    if git("status", "--porcelain", "--untracked-files=no"):
        fail("REPOSITORY_TRACKED_WORKTREE_DIRTY")
    return root, expected


def trial_bounds(verification: Verification, started_at: dt.datetime) -> dict[str, Any]:
    entry_deadline = started_at + dt.timedelta(seconds=POLICY["entry_window_seconds"])
    exit_only_deadline = entry_deadline + dt.timedelta(
        seconds=POLICY["exit_only_grace_seconds"]
    )
    hard_deadline = started_at + dt.timedelta(
        seconds=POLICY["controller_hard_runtime_seconds"]
    )
    if hard_deadline != exit_only_deadline:
        fail("CONTROLLER_BOUNDARY_CONFIGURATION_INCONSISTENT")
    return {
        "decision_evaluated_at": format_timestamp(verification.evaluated_at),
        "decision_valid_until": format_timestamp(verification.valid_until),
        "controller_started_at": format_timestamp(started_at),
        "entry_deadline": format_timestamp(entry_deadline),
        "exit_only_deadline": format_timestamp(exit_only_deadline),
        "hard_deadline": format_timestamp(hard_deadline),
        "max_selected_universe": POLICY["max_selected_entries"],
        "max_simultaneously_open_positions": POLICY[
            "max_simultaneously_open_paper_positions"
        ],
        "max_open_positions_per_pair_id": POLICY[
            "max_open_paper_positions_per_pair_id"
        ],
        "max_open_positions_per_full_instrument": POLICY[
            "max_open_paper_positions_per_full_instrument"
        ],
        "max_open_selector_exploration_positions": POLICY[
            "max_open_selector_exploration_positions"
        ],
        "max_open_positions_per_exact_key": POLICY["max_open_positions_per_exact_key"],
        "hold_window_bars": POLICY["hold_window_bars"],
        "cooldown_seconds": POLICY["cooldown_seconds"],
        "max_candidate_age_seconds": POLICY["max_candidate_age_seconds"],
        "max_automatic_start_decision_age_seconds": POLICY[
            "max_automatic_start_decision_age_seconds"
        ],
        "entry_window_seconds": POLICY["entry_window_seconds"],
        "exit_only_grace_seconds": POLICY["exit_only_grace_seconds"],
        "controller_hard_runtime_seconds": POLICY["controller_hard_runtime_seconds"],
    }


def authority_boundaries() -> dict[str, Any]:
    return {
        "paper_only": True,
        "live_order_authority": False,
        "exchange_order_routing_authority": False,
        "execution_service_post_authority": False,
        "deployment_authority": False,
        "service_configuration_authority": False,
    }


def governed_decision_reference(
    verification: Verification,
) -> dict[str, Any]:
    decision = verification.decision
    return {
        "path": str(verification.decision_bound.path),
        "sha256": verification.decision_bound.sha256,
        "decision_id": decision["decision_id"],
        "policy_envelope_sha256": decision["policy_envelope_sha256"],
        "schema_version": 2,
        "status": ELIGIBLE_STATUS,
        "independent_verification": {
            "verdict": "PASS",
            "recomputed_decision_id_matches": True,
            "recomputed_policy_envelope_sha256_matches": True,
            "raw_input_hashes_match": True,
            "rank_and_transition_recomputed": True,
            "decision_unexpired": True,
            "configuration_unchanged": True,
        },
    }


def selection_origin(
    selected_entry: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "key": selected_entry["key"],
        "evidence_class": selected_entry["evidence_class"],
        "lane_rank": selected_entry["lane_rank"],
        "selection_sequence": selected_entry["selection_sequence"],
    }


def manifest_record(
    *,
    verification: Verification,
    repository_git_sha: str,
    started_at: dt.datetime,
    recorded_at: dt.datetime,
    lifecycle_status: str,
    start_result: str,
    stop_reason: str | None,
    unresolved_open_position_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": PROVENANCE_MODE,
        "record_type": "TRIAL_MANIFEST",
        "trial_id": trial_id(str(verification.decision["decision_id"])),
        "recorded_at": format_timestamp(recorded_at),
        "repository_git_sha": repository_git_sha,
        "governed_decision": governed_decision_reference(verification),
        "trial_bounds": trial_bounds(verification, started_at),
        "append_only": True,
        "universe_immutable": True,
        "no_fallback": True,
        "automatic_restart": False,
        "selection_origin": None,
        "subject": {
            "dynamic_universe": [
                selection_origin(item) for item in verification.selected_entries
            ],
            "lifecycle_status": lifecycle_status,
            "exclusive_trial_root": True,
            "start_result": start_result,
            "stop_reason": stop_reason,
            "unresolved_open_position_count": unresolved_open_position_count,
        },
        "authority_boundaries": authority_boundaries(),
    }


def paper_binding_record(
    *,
    verification: Verification,
    repository_git_sha: str,
    started_at: dt.datetime,
    recorded_at: dt.datetime,
    selected_entry: Mapping[str, Any],
    record_type: str,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    if record_type == "PAPER_DECISION_BINDING":
        subject = {
            "paper_run_id": record["run_id"],
            "paper_decision_record_sha256": hashlib.sha256(
                canonical_bytes(record)
            ).hexdigest(),
            "decision_type": record["decision_type"],
            "paper_position_id": record.get("paper_position_id"),
        }
    elif record_type == "PAPER_POSITION_BINDING":
        subject = {
            "paper_run_id": paper.run_id(recorded_at),
            "paper_position_id": record["paper_position_id"],
            "paper_position_record_sha256": hashlib.sha256(
                canonical_bytes(record)
            ).hexdigest(),
            "position_status": record["status"],
        }
    else:
        fail("PROVENANCE_RECORD_TYPE_INVALID")
    return {
        "schema_version": 2,
        "mode": PROVENANCE_MODE,
        "record_type": record_type,
        "trial_id": trial_id(str(verification.decision["decision_id"])),
        "recorded_at": format_timestamp(recorded_at),
        "repository_git_sha": repository_git_sha,
        "governed_decision": governed_decision_reference(verification),
        "trial_bounds": trial_bounds(verification, started_at),
        "append_only": True,
        "universe_immutable": True,
        "no_fallback": True,
        "automatic_restart": False,
        "selection_origin": selection_origin(selected_entry),
        "subject": subject,
        "authority_boundaries": authority_boundaries(),
    }


def stable_read_bytes(
    path: Path,
    *,
    source: str,
    expected_identity: tuple[int, int] | None = None,
) -> bytes:
    try:
        path_lstat = path.lstat()
    except FileNotFoundError as error:
        raise ControllerInputError(f"{source}_MISSING") from error
    if stat.S_ISLNK(path_lstat.st_mode) or not stat.S_ISREG(path_lstat.st_mode):
        fail(f"{source}_NOT_REGULAR")
    if (
        expected_identity is not None
        and (
            path_lstat.st_dev,
            path_lstat.st_ino,
        )
        != expected_identity
    ):
        fail(f"{source}_IDENTITY_CHANGED")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ControllerInputError(f"{source}_OPEN_FAILED") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            fail(f"{source}_NOT_REGULAR")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if common.file_stat_identity(before) != common.file_stat_identity(after):
        fail(f"{source}_CHANGED_DURING_READ")
    if (path_lstat.st_dev, path_lstat.st_ino) != (
        before.st_dev,
        before.st_ino,
    ):
        fail(f"{source}_PATH_RACE")
    return b"".join(chunks)


def parse_jsonl_observe_rows(raw: bytes) -> list[dict[str, Any]]:
    if raw and not raw.endswith(b"\n"):
        fail("OBSERVE_SOURCE_TRAILING_PARTIAL")
    rows: list[dict[str, Any]] = []
    identities: dict[str, bytes] = {}
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            fail("OBSERVE_SOURCE_BLANK_LINE")
        try:
            row = common.parse_json_strict(line, f"OBSERVE_SOURCE_LINE_{line_number}")
        except common.GovernorInputError as error:
            fail(str(error))
        observe_key = row.get("observe_key")
        if not isinstance(observe_key, str) or not observe_key:
            fail("OBSERVE_SOURCE_OBSERVE_KEY_MISSING")
        prior = identities.get(observe_key)
        if prior is not None and prior != line:
            fail("OBSERVE_SOURCE_DUPLICATE_IDENTITY_CONFLICT")
        identities[observe_key] = line
        rows.append(row)
    unique = {str(row["observe_key"]): row for row in rows}
    return [
        unique[key]
        for key in sorted(
            unique,
            key=lambda item: (
                str(unique[item].get("observed_at", "")),
                str(unique[item].get("pair_id", "")),
                str(unique[item].get("selected_variant", "")),
                str(unique[item].get("direction_hint", "")),
                item,
            ),
        )
    ]


def actionable_observe_rows(
    rows: Sequence[Mapping[str, Any]],
    selected: Mapping[ExactKey, Mapping[str, Any]],
    processed_observe_keys: set[str],
) -> list[Mapping[str, Any]]:
    actionable: list[Mapping[str, Any]] = []
    for row in rows:
        observe_key = row["observe_key"]
        assert isinstance(observe_key, str)
        if observe_key in processed_observe_keys:
            continue
        direction = paper.direction_from_candidate(row)
        if direction in {None, "NONE"}:
            processed_observe_keys.add(observe_key)
            continue
        if direction not in ACTIONABLE_DIRECTIONS:
            fail("UNKNOWN_OBSERVE_DIRECTION")
        key = paper.candidate_key(row)
        if key is None:
            fail("OBSERVE_CANDIDATE_IDENTITY_INVALID")
        if key in selected:
            actionable.append(row)
        processed_observe_keys.add(observe_key)
    return actionable


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        return None


def adapt_paper_marks(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    adapted: list[dict[str, Any]] = []
    seen: set[tuple[ExactKey, str, float]] = set()
    for index, row in enumerate(rows):
        raw_mark_at = row.get("mark_at", row.get("exit_ts"))
        raw_net_bps = row.get("net_bps")
        # Open paper-trade rows are intentionally not marks.
        if raw_mark_at is None or raw_net_bps is None:
            continue
        mark_at = paper.parse_iso(raw_mark_at)
        net_bps = paper.nullable_number(raw_net_bps)
        if mark_at is None or net_bps is None:
            fail(f"MARKS_ROW_{index}_MALFORMED")
        direction = row.get("direction")
        if direction not in ACTIONABLE_DIRECTIONS:
            fail("REALIZED_MARK_DIRECTION_NON_ACTIONABLE")
        timeframe = row.get("timeframe", "1m")
        key = common.exact_key_from_object(
            {
                "pair_id": row.get("pair_id"),
                "timeframe": timeframe,
                "selected_variant": row.get("selected_variant"),
                "direction": direction,
            },
            f"MARKS_ROW_{index}",
        )
        canonical_mark_at = format_timestamp(mark_at)
        identity = (key, canonical_mark_at, net_bps)
        if identity in seen:
            continue
        seen.add(identity)
        adapted.append(
            {
                "pair_id": key[0],
                "timeframe": key[1],
                "selected_variant": key[2],
                "direction": key[3],
                "mark_at": canonical_mark_at,
                "source_type": "paper_trade_outcome",
                "net_bps": net_bps,
            }
        )
    return sorted(
        adapted,
        key=lambda row: (
            row["mark_at"],
            row["pair_id"],
            row["selected_variant"],
            row["direction"],
            row["net_bps"],
        ),
    )


def fetch_loopback_marks(url: str) -> tuple[list[dict[str, Any]], str]:
    require_loopback_get_url(url)
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200:
                fail("MARKS_HTTP_STATUS_INVALID")
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                fail("MARKS_RESPONSE_TOO_LARGE")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ControllerInputError("MARKS_GET_FAILED") from error
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=common.duplicate_rejecting_object,
            parse_constant=common.finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ControllerInputError("MARKS_MALFORMED_JSON") from error
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        if set(payload) != {"rows"}:
            fail("MARKS_RESPONSE_UNKNOWN_FIELD")
        rows = payload["rows"]
    else:
        fail("MARKS_RESPONSE_SHAPE_INVALID")
    if not all(isinstance(row, dict) for row in rows):
        fail("MARKS_RESPONSE_ROW_INVALID")
    return adapt_paper_marks(rows), hashlib.sha256(raw).hexdigest()


def append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    raw = json_file_bytes(record)
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            fail("OUTPUT_APPEND_TARGET_NOT_REGULAR")
        written = os.write(descriptor, raw)
        if written != len(raw):
            fail("OUTPUT_APPEND_SHORT_WRITE")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_exclusive(path: Path, raw: bytes, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        written = os.write(descriptor, raw)
        if written != len(raw):
            fail("OUTPUT_SHORT_WRITE")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_trial_paths(
    parent: Path,
    verification: Verification,
    *,
    parent_descriptor: int | None = None,
) -> TrialPaths:
    root = parent / trial_id(str(verification.decision["decision_id"]))
    if parent_descriptor is None:
        if root.exists() or root.is_symlink():
            fail("TRIAL_ROOT_ALREADY_EXISTS_NO_RESTART")
        try:
            root.mkdir(mode=0o700)
        except FileExistsError as error:
            raise ControllerInputError(
                "TRIAL_ROOT_ALREADY_EXISTS_NO_RESTART"
            ) from error
    else:
        try:
            os.stat(
                root.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            fail("TRIAL_ROOT_ALREADY_EXISTS_NO_RESTART")
        try:
            os.mkdir(
                root.name,
                mode=0o700,
                dir_fd=parent_descriptor,
            )
        except FileExistsError as error:
            raise ControllerInputError(
                "TRIAL_ROOT_ALREADY_EXISTS_NO_RESTART"
            ) from error
        descriptor_metadata = os.stat(
            root.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        path_metadata = root.lstat()
        if (
            not stat.S_ISDIR(descriptor_metadata.st_mode)
            or stat.S_ISLNK(path_metadata.st_mode)
            or not stat.S_ISDIR(path_metadata.st_mode)
            or (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
            != (path_metadata.st_dev, path_metadata.st_ino)
        ):
            fail("TRIAL_ROOT_PATH_RACE")
    return TrialPaths(
        root=root,
        binding=root / BINDING_NAME,
        provenance=root / PROVENANCE_NAME,
        events=root / EVENTS_NAME,
        paper_root=root / PAPER_ROOT_NAME,
    )


def controller_event(
    *,
    event_type: str,
    recorded_at: dt.datetime,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "mode": MODE,
        "event_type": event_type,
        "recorded_at": format_timestamp(recorded_at),
        "details": dict(details),
        "authority_boundaries": authority_boundaries(),
    }


def open_positions(
    positions: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [
        position
        for position in paper.latest_positions_by_id(positions).values()
        if position.get("status") == "OPEN"
    ]


def exposure_refusal(
    *,
    candidate_key: ExactKey,
    candidate_origin: Mapping[str, Any],
    positions: Sequence[Mapping[str, Any]],
    selected: Mapping[ExactKey, Mapping[str, Any]],
) -> str | None:
    opens = open_positions(positions)
    if len(opens) >= POLICY["max_simultaneously_open_paper_positions"]:
        return "MAX_SIMULTANEOUS_OPEN_POSITIONS"
    keys = [paper.position_key(position) for position in opens]
    valid_keys = [key for key in keys if key is not None]
    if len(valid_keys) != len(opens) or any(key not in selected for key in valid_keys):
        fail("OPEN_POSITION_OUTSIDE_IMMUTABLE_UNIVERSE")
    if any(key == candidate_key for key in valid_keys):
        return "MAX_OPEN_POSITIONS_PER_EXACT_KEY"
    if (
        sum(key[0] == candidate_key[0] for key in valid_keys)
        >= POLICY["max_open_paper_positions_per_pair_id"]
    ):
        return "MAX_OPEN_POSITIONS_PER_PAIR_ID"
    candidate_instruments = set(instrument_ids(candidate_key))
    for key in valid_keys:
        if candidate_instruments & set(instrument_ids(key)):
            return "MAX_OPEN_POSITIONS_PER_FULL_INSTRUMENT"
    if candidate_origin["evidence_class"] == "SELECTOR_EXPLORATION":
        exploration_open = sum(
            selected[key]["evidence_class"] == "SELECTOR_EXPLORATION"
            for key in valid_keys
        )
        if exploration_open >= POLICY["max_open_selector_exploration_positions"]:
            return "MAX_OPEN_SELECTOR_EXPLORATION_POSITIONS"
    return None


def selected_entry_map(
    verification: Verification,
) -> dict[ExactKey, Mapping[str, Any]]:
    result: dict[ExactKey, Mapping[str, Any]] = {}
    for index, item in enumerate(verification.selected_entries):
        key = common.exact_key_from_object(item["key"], f"SELECTED_ENTRY_{index}")
        result[key] = item
    return result


def persist_paper_result(
    *,
    result: paper.RunResult,
    paths: TrialPaths,
    verification: Verification,
    repository_git_sha: str,
    started_at: dt.datetime,
    observed_at: dt.datetime,
    selected: Mapping[ExactKey, Mapping[str, Any]],
) -> None:
    if not result.decisions and not result.positions:
        return
    decision_origins: list[Mapping[str, Any]] = []
    for decision in result.decisions:
        key = (
            str(decision.get("pair_id")),
            str(decision.get("timeframe")),
            str(decision.get("selected_variant")),
            str(decision.get("direction")),
        )
        origin = selected.get(key)
        if origin is None:
            fail("PAPER_DECISION_OUTSIDE_IMMUTABLE_UNIVERSE")
        decision_origins.append(origin)
    position_origins: list[Mapping[str, Any]] = []
    for position in result.positions:
        key = paper.position_key(position)
        if key is None or key not in selected:
            fail("PAPER_POSITION_OUTSIDE_IMMUTABLE_UNIVERSE")
        position_origins.append(selected[key])

    # Validate every paper record against the immutable controller universe
    # before the existing paper writer can create or append an artifact.
    paper.write_artifacts(result, paths.paper_root, observed_at)
    for decision, origin in zip(result.decisions, decision_origins):
        append_jsonl(
            paths.provenance,
            paper_binding_record(
                verification=verification,
                repository_git_sha=repository_git_sha,
                started_at=started_at,
                recorded_at=observed_at,
                selected_entry=origin,
                record_type="PAPER_DECISION_BINDING",
                record=decision,
            ),
        )
    for position, origin in zip(result.positions, position_origins):
        append_jsonl(
            paths.provenance,
            paper_binding_record(
                verification=verification,
                repository_git_sha=repository_git_sha,
                started_at=started_at,
                recorded_at=observed_at,
                selected_entry=origin,
                record_type="PAPER_POSITION_BINDING",
                record=position,
            ),
        )


def validate_start_time(verification: Verification, started_at: dt.datetime) -> None:
    age = (started_at - verification.evaluated_at).total_seconds()
    if age < 0:
        fail("CONTROLLER_START_BEFORE_DECISION")
    if age > POLICY["max_automatic_start_decision_age_seconds"]:
        fail("CONTROLLER_START_DECISION_STALE")
    if started_at >= verification.valid_until:
        fail("CONTROLLER_START_DECISION_EXPIRED")


def validate_wall_clock_start(
    verification: Verification,
    started_at: dt.datetime,
    wall_now: dt.datetime,
) -> None:
    now = wall_now.astimezone(dt.timezone.utc)
    if now < started_at:
        fail("CONTROLLER_STARTED_AT_IN_FUTURE")
    if (now - started_at).total_seconds() > CADENCE_SECONDS:
        fail("CONTROLLER_STARTED_AT_BINDING_STALE")
    if (now - verification.evaluated_at).total_seconds() > POLICY[
        "max_automatic_start_decision_age_seconds"
    ]:
        fail("CONTROLLER_ACTUAL_START_DECISION_STALE")
    if now >= verification.valid_until:
        fail("CONTROLLER_ACTUAL_START_DECISION_EXPIRED")


def prepare_runtime_bindings(
    args: argparse.Namespace,
) -> tuple[
    Verification,
    Path,
    str,
    dt.datetime,
    Path,
    tuple[int, int],
    str,
    Path,
]:
    repository_root, repository_git_sha = verify_repository(
        args.repository_root, args.repository_git_sha
    )
    verification = read_and_verify(args)
    started_at = parse_required_timestamp(
        args.controller_started_at, "CONTROLLER_STARTED_AT"
    )
    validate_start_time(verification, started_at)
    validate_wall_clock_start(
        verification,
        started_at,
        paper.utc_now(),
    )
    observe_source, observe_identity = require_observe_source(args.observe_source_jsonl)
    initial_observe_rows = parse_jsonl_observe_rows(
        stable_read_bytes(
            observe_source,
            source="OBSERVE_SOURCE",
            expected_identity=observe_identity,
        )
    )
    actionable_observe_rows(
        initial_observe_rows,
        selected_entry_map(verification),
        set(),
    )
    marks_url = require_loopback_get_url(args.marks_url)
    parent = require_absolute_path(args.trial_root_parent, "TRIAL_ROOT_PARENT")
    require_existing_directory(parent, "TRIAL_ROOT_PARENT")
    proposed_root = parent / trial_id(str(verification.decision["decision_id"]))
    if proposed_root.exists() or proposed_root.is_symlink():
        fail("TRIAL_ROOT_ALREADY_EXISTS_NO_RESTART")
    # Re-run the cheap repository checks after all potentially large evidence
    # reads so an exact-SHA binding cannot silently change underneath them.
    verify_repository(str(repository_root), repository_git_sha)
    recheck_verification_inputs(verification)
    return (
        verification,
        repository_root,
        repository_git_sha,
        started_at,
        observe_source,
        observe_identity,
        marks_url,
        parent,
    )


def run_verify_only(args: argparse.Namespace) -> dict[str, Any]:
    (
        verification,
        repository_root,
        repository_git_sha,
        started_at,
        observe_source,
        _observe_identity,
        marks_url,
        parent,
    ) = prepare_runtime_bindings(args)
    return {
        "mode": MODE,
        "status": "VERIFIED_NOT_STARTED",
        "verification": "PASS",
        "artifact_created": False,
        "network_accessed": False,
        "start_invoked": False,
        "repository_root": str(repository_root),
        "repository_git_sha": repository_git_sha,
        "decision_id": verification.decision["decision_id"],
        "decision_sha256": verification.decision_bound.sha256,
        "policy_envelope_sha256": verification.decision["policy_envelope_sha256"],
        "selected_entry_count": len(verification.selected_entries),
        "controller_started_at_binding": format_timestamp(started_at),
        "observe_source": str(observe_source),
        "marks_url": marks_url,
        "proposed_trial_root": str(
            parent / trial_id(str(verification.decision["decision_id"]))
        ),
        "authority_boundaries": authority_boundaries(),
    }


def create_initial_outputs(
    *,
    parent: Path,
    verification: Verification,
    repository_root: Path,
    repository_git_sha: str,
    started_at: dt.datetime,
    observe_source: Path,
    observe_identity: tuple[int, int],
    marks_url: str,
    parent_descriptor: int | None = None,
) -> TrialPaths:
    paths = create_trial_paths(
        parent,
        verification,
        parent_descriptor=parent_descriptor,
    )
    binding = {
        "mode": MODE,
        "trial_id": trial_id(str(verification.decision["decision_id"])),
        "repository_root": str(repository_root),
        "repository_git_sha": repository_git_sha,
        "controller_started_at": format_timestamp(started_at),
        "decision_path": str(verification.decision_bound.path),
        "decision_sha256": verification.decision_bound.sha256,
        "current_snapshot": {
            "path": str(verification.bound_inputs[1].path),
            "sha256": verification.bound_inputs[1].sha256,
            "producer_git_sha": verification.decision["current_snapshot"][
                "producer_git_sha"
            ],
        },
        "previous_snapshot": {
            "path": str(verification.bound_inputs[2].path),
            "sha256": verification.bound_inputs[2].sha256,
            "producer_git_sha": verification.decision["previous_snapshot"][
                "producer_git_sha"
            ],
        },
        "paper_run_config": {
            "path": str(verification.bound_inputs[3].path),
            "sha256": verification.bound_inputs[3].sha256,
            "producer_git_sha": verification.decision["paper_run_config"][
                "producer_git_sha"
            ],
        },
        "governor_config": {
            "path": str(verification.bound_inputs[4].path),
            "sha256": verification.bound_inputs[4].sha256,
        },
        "observe_source": {
            "path": str(observe_source),
            "device": observe_identity[0],
            "inode": observe_identity[1],
        },
        "marks_adapter": {
            "url": marks_url,
            "method": "GET",
            "loopback_only": True,
        },
        "trial_bounds": trial_bounds(verification, started_at),
        "universe": [selection_origin(item) for item in verification.selected_entries],
        "append_only": True,
        "universe_immutable": True,
        "no_fallback": True,
        "automatic_restart": False,
        "authority_boundaries": authority_boundaries(),
    }
    write_exclusive(paths.binding, json_file_bytes(binding))
    write_exclusive(paths.provenance, b"")
    write_exclusive(paths.events, b"")
    append_jsonl(
        paths.provenance,
        manifest_record(
            verification=verification,
            repository_git_sha=repository_git_sha,
            started_at=started_at,
            recorded_at=started_at,
            lifecycle_status="RUNNING",
            start_result="STARTED",
            stop_reason=None,
            unresolved_open_position_count=0,
        ),
    )
    append_jsonl(
        paths.events,
        controller_event(
            event_type="CONTROLLER_STARTED",
            recorded_at=started_at,
            details={
                "cadence_seconds": CADENCE_SECONDS,
                "decision_id": verification.decision["decision_id"],
                "selected_entry_count": len(verification.selected_entries),
            },
        ),
    )
    return paths


def run_controller_loop(
    *,
    verification: Verification,
    repository_root: Path,
    repository_git_sha: str,
    started_at: dt.datetime,
    observe_source: Path,
    observe_identity: tuple[int, int],
    marks_url: str,
    paths: TrialPaths,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    marks_fetcher: Callable[
        [str], tuple[list[dict[str, Any]], str]
    ] = fetch_loopback_marks,
) -> dict[str, Any]:
    selected = selected_entry_map(verification)
    paper_config = paper.Config(
        enabled=True,
        allowed_pair_variants=set(),
        allowed_pair_variant_directions={(key[0], key[2], key[3]) for key in selected},
        hold_window_bars=POLICY["hold_window_bars"],
        cooldown_seconds=POLICY["cooldown_seconds"],
        max_candidate_age_seconds=POLICY["max_candidate_age_seconds"],
        output_dir=paths.paper_root,
    )
    positions: list[dict[str, Any]] = []
    processed_observe_keys: set[str] = set()
    start_monotonic = monotonic()
    if not isinstance(start_monotonic, (int, float)):
        fail("MONOTONIC_CLOCK_INVALID")
    exit_only_recorded = False
    tick = 0

    while True:
        tick_started = monotonic()
        elapsed = tick_started - start_monotonic
        if elapsed < 0:
            fail("MONOTONIC_CLOCK_REVERSED")
        observed_at = started_at + dt.timedelta(seconds=int(elapsed))
        entry_open = elapsed < POLICY["entry_window_seconds"]
        hard_reached = elapsed >= POLICY["controller_hard_runtime_seconds"]

        verify_repository(str(repository_root), repository_git_sha)
        recheck_verification_inputs(verification)
        raw_observe = stable_read_bytes(
            observe_source,
            source="OBSERVE_SOURCE",
            expected_identity=observe_identity,
        )
        observe_rows = parse_jsonl_observe_rows(raw_observe)
        marks, marks_sha256 = marks_fetcher(marks_url)
        tick += 1
        append_jsonl(
            paths.events,
            controller_event(
                event_type="INPUT_TICK_CAPTURED",
                recorded_at=observed_at,
                details={
                    "tick": tick,
                    "observe_source_sha256": hashlib.sha256(raw_observe).hexdigest(),
                    "observe_row_count": len(observe_rows),
                    "marks_response_sha256": marks_sha256,
                    "mark_row_count": len(marks),
                    "entry_open": entry_open,
                },
            ),
        )

        exit_result = paper.maybe_exit_open_positions(
            config=paper_config,
            existing_positions=positions,
            marks=marks,
            observed_at=observed_at,
        )
        persist_paper_result(
            result=exit_result,
            paths=paths,
            verification=verification,
            repository_git_sha=repository_git_sha,
            started_at=started_at,
            observed_at=observed_at,
            selected=selected,
        )
        positions.extend(exit_result.positions)

        if entry_open and not hard_reached:
            candidates = actionable_observe_rows(
                observe_rows, selected, processed_observe_keys
            )
            for candidate in candidates:
                key = paper.candidate_key(candidate)
                if key is None:
                    fail("OBSERVE_CANDIDATE_IDENTITY_INVALID")
                refusal = exposure_refusal(
                    candidate_key=key,
                    candidate_origin=selected[key],
                    positions=positions,
                    selected=selected,
                )
                if refusal is not None:
                    append_jsonl(
                        paths.events,
                        controller_event(
                            event_type="PAPER_ENTRY_REFUSED_EXPOSURE",
                            recorded_at=observed_at,
                            details={
                                "observe_key": candidate["observe_key"],
                                "key": common.key_object(key),
                                "reason_code": refusal,
                            },
                        ),
                    )
                    continue
                entry_result = paper.evaluate_candidate(
                    config=paper_config,
                    candidate=candidate,
                    observed_at=observed_at,
                    existing_positions=positions,
                )
                persist_paper_result(
                    result=entry_result,
                    paths=paths,
                    verification=verification,
                    repository_git_sha=repository_git_sha,
                    started_at=started_at,
                    observed_at=observed_at,
                    selected=selected,
                )
                positions.extend(entry_result.positions)

        opens = open_positions(positions)
        if observed_at >= verification.valid_until:
            append_jsonl(
                paths.provenance,
                manifest_record(
                    verification=verification,
                    repository_git_sha=repository_git_sha,
                    started_at=started_at,
                    recorded_at=observed_at,
                    lifecycle_status="NO_GO",
                    start_result="STARTED",
                    stop_reason="DECISION_EXPIRED",
                    unresolved_open_position_count=len(opens),
                ),
            )
            return {
                "mode": MODE,
                "status": "NO_GO",
                "stop_reason": "DECISION_EXPIRED",
                "trial_id": trial_id(str(verification.decision["decision_id"])),
                "trial_root": str(paths.root),
                "ticks": tick,
                "unresolved_open_position_count": len(opens),
                "authority_boundaries": authority_boundaries(),
            }
        if not entry_open and not exit_only_recorded:
            append_jsonl(
                paths.provenance,
                manifest_record(
                    verification=verification,
                    repository_git_sha=repository_git_sha,
                    started_at=started_at,
                    recorded_at=observed_at,
                    lifecycle_status="EXIT_ONLY",
                    start_result="STARTED",
                    stop_reason="ENTRY_DEADLINE_REACHED",
                    unresolved_open_position_count=len(opens),
                ),
            )
            exit_only_recorded = True
        if not entry_open and not opens:
            append_jsonl(
                paths.provenance,
                manifest_record(
                    verification=verification,
                    repository_git_sha=repository_git_sha,
                    started_at=started_at,
                    recorded_at=observed_at,
                    lifecycle_status="COMPLETE",
                    start_result="STARTED",
                    stop_reason="NATURAL_COMPLETION",
                    unresolved_open_position_count=0,
                ),
            )
            return {
                "mode": MODE,
                "status": "COMPLETE",
                "stop_reason": "NATURAL_COMPLETION",
                "trial_id": trial_id(str(verification.decision["decision_id"])),
                "trial_root": str(paths.root),
                "ticks": tick,
                "unresolved_open_position_count": 0,
                "authority_boundaries": authority_boundaries(),
            }
        if hard_reached:
            append_jsonl(
                paths.provenance,
                manifest_record(
                    verification=verification,
                    repository_git_sha=repository_git_sha,
                    started_at=started_at,
                    recorded_at=observed_at,
                    lifecycle_status="NO_GO",
                    start_result="STARTED",
                    stop_reason="HARD_RUNTIME_REACHED",
                    unresolved_open_position_count=len(opens),
                ),
            )
            return {
                "mode": MODE,
                "status": "NO_GO",
                "stop_reason": "HARD_RUNTIME_REACHED",
                "trial_id": trial_id(str(verification.decision["decision_id"])),
                "trial_root": str(paths.root),
                "ticks": tick,
                "unresolved_open_position_count": len(opens),
                "authority_boundaries": authority_boundaries(),
            }

        tick_elapsed = monotonic() - tick_started
        if tick_elapsed < 0:
            fail("MONOTONIC_CLOCK_REVERSED")
        sleeper(max(0.0, CADENCE_SECONDS - tick_elapsed))


def run_start(args: argparse.Namespace) -> dict[str, Any]:
    (
        verification,
        repository_root,
        repository_git_sha,
        started_at,
        observe_source,
        observe_identity,
        marks_url,
        parent,
    ) = prepare_runtime_bindings(args)
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        parent_descriptor = os.open(parent, flags)
    except OSError as error:
        raise ControllerInputError("TRIAL_ROOT_PARENT_OPEN_FAILED") from error
    paths: TrialPaths | None = None
    try:
        parent_before = os.fstat(parent_descriptor)
        if not stat.S_ISDIR(parent_before.st_mode):
            fail("TRIAL_ROOT_PARENT_NOT_DIRECTORY")
        try:
            fcntl.flock(parent_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ControllerInputError("CONTROLLER_CONCURRENT_OWNER") from error
        recheck_verification_inputs(verification)
        verify_repository(str(repository_root), repository_git_sha)
        parent_path_metadata = parent.lstat()
        parent_after = os.fstat(parent_descriptor)
        if (
            stat.S_ISLNK(parent_path_metadata.st_mode)
            or not stat.S_ISDIR(parent_path_metadata.st_mode)
            or (parent_path_metadata.st_dev, parent_path_metadata.st_ino)
            != (parent_after.st_dev, parent_after.st_ino)
            or common.file_stat_identity(parent_before)
            != common.file_stat_identity(parent_after)
        ):
            fail("TRIAL_ROOT_PARENT_CHANGED")
        try:
            paths = create_initial_outputs(
                parent=parent,
                verification=verification,
                repository_root=repository_root,
                repository_git_sha=repository_git_sha,
                started_at=started_at,
                observe_source=observe_source,
                observe_identity=observe_identity,
                marks_url=marks_url,
                parent_descriptor=parent_descriptor,
            )
        except (ControllerInputError, OSError) as error:
            proposed_root = parent / trial_id(str(verification.decision["decision_id"]))
            try:
                root_metadata = proposed_root.lstat()
                root_created = not stat.S_ISLNK(root_metadata.st_mode) and stat.S_ISDIR(
                    root_metadata.st_mode
                )
            except FileNotFoundError:
                root_created = False
            code = (
                str(error)
                if isinstance(error, ControllerInputError)
                else "INITIAL_OUTPUT_CREATE_FAILED"
            )
            raise ControllerInputError(
                code,
                artifact_created=root_created,
                trial_root=str(proposed_root) if root_created else None,
            ) from error
        try:
            return run_controller_loop(
                verification=verification,
                repository_root=repository_root,
                repository_git_sha=repository_git_sha,
                started_at=started_at,
                observe_source=observe_source,
                observe_identity=observe_identity,
                marks_url=marks_url,
                paths=paths,
            )
        except (
            ControllerInputError,
            common.GovernorInputError,
            OSError,
            ValueError,
        ) as error:
            observed_at = paper.utc_now()
            try:
                persisted_positions = paper.read_persisted_positions(paths.paper_root)
                unresolved = len(open_positions(persisted_positions))
            except (OSError, ValueError, TypeError, KeyError):
                unresolved = POLICY["max_simultaneously_open_paper_positions"]
            if isinstance(error, (ControllerInputError, common.GovernorInputError)):
                code = str(error)
            elif isinstance(error, OSError):
                code = "RUNTIME_IO_ERROR"
            else:
                code = "RUNTIME_STATE_INVALID"
            if "CONCURRENT" in code or "IDENTITY" in code:
                stop_reason = "CONCURRENCY_IDENTITY_LOST"
            elif "GOVERNOR_CONFIG" in code or "POLICY" in code:
                stop_reason = "POLICY_HASH_CONFLICT"
            elif (
                "BOUND_INPUT" in code
                or "HASH_MISMATCH" in code
                or "CHANGED_BEFORE_OUTPUT" in code
                or "REPOSITORY_HEAD" in code
            ):
                stop_reason = "BOUND_INPUT_CHANGED"
            else:
                stop_reason = "MALFORMED_STATE"
            try:
                append_jsonl(
                    paths.provenance,
                    manifest_record(
                        verification=verification,
                        repository_git_sha=repository_git_sha,
                        started_at=started_at,
                        recorded_at=observed_at,
                        lifecycle_status="NO_GO",
                        start_result="STARTED",
                        stop_reason=stop_reason,
                        unresolved_open_position_count=unresolved,
                    ),
                )
                append_jsonl(
                    paths.events,
                    controller_event(
                        event_type="CONTROLLER_FAIL_CLOSED",
                        recorded_at=observed_at,
                        details={
                            "error_code": code,
                            "stop_reason": stop_reason,
                            "unresolved_open_position_count": unresolved,
                        },
                    ),
                )
            except (OSError, ControllerInputError):
                pass
            raise ControllerInputError(
                code,
                artifact_created=True,
                trial_root=str(paths.root),
            ) from error
    finally:
        os.close(parent_descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify-only",
        action="store_true",
        help="Read and independently verify all bindings; create nothing.",
    )
    mode.add_argument(
        "--start",
        action="store_true",
        help="Start one foreground bounded paper-only controller.",
    )
    parser.add_argument(
        "--enabled",
        action="store_true",
        help="Required in addition to --start.",
    )
    parser.add_argument("--repository-root")
    parser.add_argument("--repository-git-sha")
    parser.add_argument("--decision-json")
    parser.add_argument("--decision-sha256")
    parser.add_argument("--current-snapshot-json")
    parser.add_argument("--current-snapshot-sha256")
    parser.add_argument("--current-snapshot-producer-git-sha")
    parser.add_argument("--previous-snapshot-json")
    parser.add_argument("--previous-snapshot-sha256")
    parser.add_argument("--previous-snapshot-producer-git-sha")
    parser.add_argument("--paper-run-config-json")
    parser.add_argument("--paper-run-config-sha256")
    parser.add_argument("--paper-run-config-producer-git-sha")
    parser.add_argument("--governor-config-json")
    parser.add_argument("--governor-config-sha256")
    parser.add_argument("--evaluated-at")
    parser.add_argument("--prior-active-set-source")
    parser.add_argument("--controller-started-at")
    parser.add_argument("--observe-source-jsonl")
    parser.add_argument("--marks-url")
    parser.add_argument("--trial-root-parent")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.verify_only and not args.start:
        print(json.dumps(DISABLED_DIAGNOSTIC, sort_keys=True, separators=(",", ":")))
        return 0
    if args.start and not args.enabled:
        print(
            json.dumps(
                {
                    "mode": MODE,
                    "status": "INPUT_REJECTED",
                    "error_code": "START_REQUIRES_EXPLICIT_ENABLED_GATE",
                    "artifact_created": False,
                    "start_invoked": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    if args.verify_only and args.enabled:
        print(
            json.dumps(
                {
                    "mode": MODE,
                    "status": "INPUT_REJECTED",
                    "error_code": "VERIFY_ONLY_MUST_REMAIN_READ_ONLY",
                    "artifact_created": False,
                    "start_invoked": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    try:
        result = run_start(args) if args.start else run_verify_only(args)
    except (
        ControllerInputError,
        common.GovernorInputError,
        OSError,
        ValueError,
    ) as error:
        artifact_created = bool(
            isinstance(error, ControllerInputError) and error.artifact_created
        )
        if isinstance(error, (ControllerInputError, common.GovernorInputError)):
            error_code = str(error)
        elif isinstance(error, OSError):
            error_code = "INPUT_OR_RUNTIME_IO_ERROR"
        else:
            error_code = "INPUT_OR_RUNTIME_STATE_INVALID"
        print(
            json.dumps(
                {
                    "mode": MODE,
                    "status": "NO_GO" if artifact_created else "INPUT_REJECTED",
                    "error_code": error_code,
                    "artifact_created": artifact_created,
                    "trial_root": (
                        error.trial_root
                        if isinstance(error, ControllerInputError)
                        else None
                    ),
                    "automatic_retry": False,
                    "repair_or_cleanup_attempted": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") != "NO_GO" else 2


if __name__ == "__main__":
    sys.exit(main())
