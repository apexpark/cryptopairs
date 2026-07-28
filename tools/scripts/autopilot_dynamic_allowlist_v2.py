#!/usr/bin/env python3
"""Build or verify one offline AUTO-2C v2 governed allowlist decision.

The tool is disabled by default. Explicit ``--enabled`` invocation reads only
exactly bound local evidence files and exclusively creates one non-actuating
JSON decision plus one deterministic Markdown report. ``--verify-only`` reads
the same bound inputs and existing outputs, reconstructs the result, and
creates nothing. Neither mode can alter paper/live eligibility, runtime
configuration, services, orders, or deployments.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Optional

import autopilot_dynamic_allowlist as v1


DISABLED_MODE = "auto2c_v2_governor"
DECISION_MODE = "governed_dynamic_allowlist_decision"
DISABLED_DIAGNOSTIC = {
    "artifact_created": False,
    "mode": DISABLED_MODE,
    "status": "DISABLED",
}

POLICY_VERSION = "auto2c-v2-paper-automatic-acceptance-1"
OUTPUT_JSON_NAME = "autopilot_dynamic_allowlist_decision_v2.json"
OUTPUT_MARKDOWN_NAME = "autopilot_dynamic_allowlist_decision_v2.md"
PRIOR_SOURCE = "STATIC_PAPER_ALLOWLIST"
UNSUPPORTED_PRIOR_SOURCE = "PREVIOUS_ACCEPTED_V2_PAPER_UNIVERSE"

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

GOVERNOR_CONFIG = {
    "policy_version": POLICY_VERSION,
    "policy": POLICY,
}

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
SelectorKey = tuple[str, str, str, Optional[str]]


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
    evidence: v1.SnapshotEvidence
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
            "key": v1.key_object(self.key),
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
            "key": v1.key_object(self.candidate.key),
            "evidence_class": self.candidate.evidence_class,
            "lane_rank": self.candidate.lane_rank,
            "selection_sequence": self.sequence,
            "selection_rule": self.rule,
        }


@dataclasses.dataclass(frozen=True)
class Evaluation:
    decision: dict[str, Any]
    markdown: str
    bound_inputs: tuple[v1.BoundInput, ...]


@dataclasses.dataclass(frozen=True)
class RawBoundFile:
    path: Path
    expected_sha256: str
    sha256: str
    raw_bytes: bytes
    stat_identity: tuple[int, int, int, int]


def policy_envelope_sha256() -> str:
    return hashlib.sha256(
        v1.canonical_json_bytes(
            {
                "policy_version": POLICY_VERSION,
                "policy": POLICY,
            }
        )
    ).hexdigest()


def prior_active_set_sha256(baseline: frozenset[ExactKey]) -> str:
    return hashlib.sha256(
        v1.canonical_json_bytes(
            [v1.key_object(key) for key in sorted(baseline)]
        )
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
        v1.canonical_json_bytes(
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


def require_distinct_bound_inputs(inputs: Sequence[v1.BoundInput]) -> None:
    paths = [str(item.path) for item in inputs]
    identities = [item.stat_identity[:2] for item in inputs]
    if len(paths) != len(set(paths)):
        v1.fail("BOUND_INPUT_PATH_REUSED")
    if len(identities) != len(set(identities)):
        v1.fail("BOUND_INPUT_FILE_REUSED")


def selector_metrics(value: object, field: str) -> SelectorMetrics | None:
    row = v1.require_exact_keys(
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
    rows = v1.require_integer(row["rows_observed"], f"{field}_ROWS")
    counts = v1.require_exact_keys(
        row["bucket_counts"],
        {"TRADE_NOW", "WATCHLIST", "EXCLUDED"},
        f"{field}_BUCKETS",
    )
    trade_now = v1.require_integer(counts["TRADE_NOW"], f"{field}_TRADE_NOW")
    ratio = v1.require_number(row["time_in_tradable_now_ratio"], f"{field}_RATIO")
    assert ratio is not None
    summary = row.get("stated_net_edge_bps_summary")
    if summary is None:
        return None
    summary_row = v1.require_exact_keys(
        summary,
        {"min", "max", "mean"},
        f"{field}_EDGE",
    )
    mean = v1.require_number(
        summary_row["mean"],
        f"{field}_EDGE_MEAN",
        nullable=True,
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
    return SelectorMetrics(
        selector_row_count=rows,
        trade_now_count=trade_now,
        time_in_trade_now_ratio=ratio,
        selector_stated_mean_net_edge_bps=mean,
    )


def extract_selector_metrics(
    snapshot: v1.SnapshotEvidence,
    role: str,
) -> dict[ExactKey, SelectorMetrics]:
    selector_view = snapshot.bound.payload.get("selector_view")
    if not isinstance(selector_view, dict):
        v1.fail(f"{role}_SELECTOR_VIEW_MISSING")
    values = selector_view.get("selector_view_prominent")
    if not isinstance(values, list):
        v1.fail(f"{role}_SELECTOR_PROMINENT_INVALID")
    result: dict[ExactKey, SelectorMetrics] = {}
    for index, value in enumerate(values):
        row = v1.require_exact_keys(
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
        key = v1.exact_key_from_object(
            {
                "pair_id": row["pair_id"],
                "timeframe": row["timeframe"],
                "selected_variant": row["selected_variant"],
                "direction": direction,
            },
            f"{role}_SELECTOR_PROMINENT_{index}",
        )
        metrics = selector_metrics(
            row["metrics"],
            f"{role}_SELECTOR_PROMINENT_{index}_METRICS",
        )
        if metrics is not None:
            result[key] = metrics
    return result


def extract_realized_metrics(
    snapshot: v1.SnapshotEvidence,
    role: str,
) -> dict[ExactKey, RealizedMetrics]:
    values = snapshot.bound.payload["selected"]
    if not isinstance(values, list):
        v1.fail(f"{role}_SELECTED_NOT_ARRAY")
    result: dict[ExactKey, RealizedMetrics] = {}
    for index, value in enumerate(values):
        row = v1.require_exact_keys(
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
        key = v1.exact_key_from_object(
            {
                "pair_id": row["pair_id"],
                "timeframe": row["timeframe"],
                "selected_variant": row["selected_variant"],
                "direction": row["direction"],
            },
            f"{role}_SELECTED_{index}",
        )
        metrics = v1.require_exact_keys(
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
        score = v1.require_exact_keys(
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
        total = v1.require_number(
            score["total_score"],
            f"{role}_SELECTED_{index}_TOTAL_SCORE",
        )
        assert total is not None
        result[key] = RealizedMetrics(
            total_b2c_score=total,
            closed_position_count=v1.require_integer(
                metrics["closed_positions"],
                f"{role}_SELECTED_{index}_CLOSED",
                1,
            ),
        )
    return result


def validate_snapshot_v2(
    bound: v1.BoundInput,
    role: str,
) -> SnapshotDetails:
    evidence = v1.validate_snapshot(bound, role)
    if evidence.schema_version != 2:
        v1.fail(f"{role}_SNAPSHOT_NOT_SCHEMA_V2")
    if (
        evidence.selector_prominent is None
        or evidence.selector_marginal is None
        or not evidence.selector_churn_available
    ):
        v1.fail(f"{role}_SELECTOR_EVIDENCE_INCOMPLETE")
    if evidence.generated_at.microsecond or evidence.source_cutoff_at.microsecond:
        v1.fail(f"{role}_SNAPSHOT_TIMESTAMP_NOT_CANONICAL_SECONDS")
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
    selector_keys = (
        set(current.selector_prominent_metrics)
        & set(previous.selector_prominent_metrics)
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
            key in current.evidence.selected
            and key in previous.evidence.selected
        )
        absent_both = (
            key not in current_realized_sets
            and key not in previous_realized_sets
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
        for index, candidate in enumerate(sorted(lane, key=candidate_rank), 1):
            ranked.append(dataclasses.replace(candidate, lane_rank=index))
    return ranked


def instrument_ids(key: ExactKey) -> tuple[str, str]:
    left, right = key[0].split("__")
    return left, right


def concentration_failure(
    selected: Sequence[Candidate],
    candidate: Candidate,
    baseline: frozenset[ExactKey],
) -> str | None:
    proposed = [item.key for item in selected] + [candidate.key]
    pair_variant = Counter((key[0], key[1], key[2]) for key in proposed)
    if (
        pair_variant[(candidate.key[0], candidate.key[1], candidate.key[2])]
        > POLICY["max_directions_per_pair_variant"]
    ):
        return "SKIPPED_PAIR_CONCENTRATION"
    pairs = Counter(key[0] for key in proposed)
    if pairs[candidate.key[0]] > POLICY["max_entries_per_pair_id"]:
        return "SKIPPED_PAIR_CONCENTRATION"
    instruments: Counter[str] = Counter()
    addition_instruments: Counter[str] = Counter()
    for key in proposed:
        for instrument in instrument_ids(key):
            instruments[instrument] += 1
            if key not in baseline:
                addition_instruments[instrument] += 1
    if any(
        count > POLICY["max_entries_per_full_instrument"]
        for count in instruments.values()
    ):
        return "SKIPPED_INSTRUMENT_CONCENTRATION"
    if any(
        count > POLICY["max_new_additions_per_full_instrument"]
        for count in addition_instruments.values()
    ):
        return "SKIPPED_ADDITION_INSTRUMENT_CONCENTRATION"
    return None


def outcome(candidate: Candidate, reason: str) -> dict[str, Any]:
    return {
        "key": v1.key_object(candidate.key),
        "evidence_class": candidate.evidence_class,
        "lane_rank": candidate.lane_rank,
        "reason_code": reason,
    }


def reservation_transition_safety(
    candidate: Candidate,
    realized: Sequence[Candidate],
    baseline: frozenset[ExactKey],
) -> tuple[bool, str | None]:
    simulated = [candidate]
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
        transition_is_valid(selections, [candidate], baseline),
        first_concentration_failure,
    )


def allocate_candidates(
    candidates: Sequence[Candidate],
    baseline: frozenset[ExactKey],
) -> tuple[list[Selection], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    realized = [
        candidate
        for candidate in candidates
        if candidate.evidence_class == "REALIZED_AND_SELECTOR"
    ]
    exploration = [
        candidate
        for candidate in candidates
        if candidate.evidence_class == "SELECTOR_EXPLORATION"
    ]
    selected: list[Candidate] = []
    selections: list[Selection] = []
    steps: list[dict[str, Any]] = []
    truncated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    processed: set[ExactKey] = set()

    def record_skip(candidate: Candidate, reason: str) -> None:
        skipped.append(outcome(candidate, reason))
        steps.append(
            {
                "step": len(steps) + 1,
                "rule": "SKIP_CONCENTRATION_AND_CONTINUE",
                "candidate_key": v1.key_object(candidate.key),
                "result": "SKIPPED",
            }
        )
        processed.add(candidate.key)

    def process(candidate: Candidate, rule: str) -> None:
        step = len(steps) + 1
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
                result = "SELECTED"
                selected.append(candidate)
                selections.append(Selection(candidate, len(selected), rule))
                step_rule = rule
        steps.append(
            {
                "step": step,
                "rule": step_rule,
                "candidate_key": v1.key_object(candidate.key),
                "result": result,
            }
        )
        processed.add(candidate.key)

    for candidate in exploration:
        transition_safe, prospective_reason = reservation_transition_safety(
            candidate,
            realized,
            baseline,
        )
        if not transition_safe and prospective_reason is not None:
            record_skip(candidate, prospective_reason)
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
        item.candidate.evidence_class == "SELECTOR_EXPLORATION"
        for item in selections
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


def gate_results(reasons: Sequence[str]) -> tuple[dict[str, Any], dict[str, int]]:
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
    snapshot: SnapshotDetails,
    producer_git_sha: str,
) -> dict[str, Any]:
    evidence = snapshot.evidence
    return {
        "path": str(evidence.bound.path),
        "sha256": evidence.bound.sha256,
        "producer_git_sha": producer_git_sha,
        "schema_version": 2,
        "generated_at": v1.format_timestamp(evidence.generated_at),
        "source_cutoff_at": v1.format_timestamp(evidence.source_cutoff_at),
        "selector_config_sha256": hashlib.sha256(
            v1.canonical_json_bytes(v1.SELECTOR_CONFIG)
        ).hexdigest(),
        "selector_view_present": True,
        "selector_view_churn_available": True,
    }


def concentration_calculations(
    proposed: frozenset[ExactKey],
    additions: frozenset[ExactKey],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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


def build_decision(
    *,
    current: SnapshotDetails,
    previous: SnapshotDetails,
    baseline: frozenset[ExactKey],
    paper: v1.BoundInput,
    governor: v1.BoundInput,
    current_producer_git_sha: str,
    previous_producer_git_sha: str,
    paper_producer_git_sha: str,
    evaluated_at: dt.datetime,
) -> dict[str, Any]:
    if current.evidence.bound.sha256 == previous.evidence.bound.sha256:
        v1.fail("SNAPSHOT_HASH_REUSED")
    if current.evidence.source_cutoff_at <= previous.evidence.source_cutoff_at:
        v1.fail("SOURCE_CUTOFF_ORDER_INVALID")
    if current.evidence.source_cutoff_at > evaluated_at:
        v1.fail("CURRENT_SOURCE_FROM_FUTURE")
    v1.validate_static_comparison(current.evidence, baseline, "CURRENT")
    v1.validate_static_comparison(previous.evidence, baseline, "PREVIOUS")
    v1.validate_current_churn(current.evidence, previous.evidence)

    separation_seconds = (
        current.evidence.source_cutoff_at
        - previous.evidence.source_cutoff_at
    ).total_seconds()
    age_seconds = (
        evaluated_at - current.evidence.source_cutoff_at
    ).total_seconds()
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
            candidates,
            baseline,
        )
        if not transition_is_valid(selections, candidates, baseline):
            reasons.append("TRANSITION_LIMITS_UNSATISFIABLE")
            selections = []
            steps = []
            truncated = []
            skipped = []

    status = (
        "GOVERNOR_BLOCKED"
        if reasons
        else "POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION"
    )
    proposed = frozenset(item.candidate.key for item in selections)
    additions = proposed - baseline if not reasons else frozenset()
    removals = baseline - proposed if not reasons else frozenset()
    retained = proposed & baseline if not reasons else frozenset()
    change_count = len(additions) + len(removals)
    churn_denominator = max(POLICY["churn_floor_capacity"], len(baseline))
    churn_ratio = change_count / churn_denominator if selections else 0
    pair_counts, pair_variant_counts, instrument_counts = concentration_calculations(
        proposed,
        additions,
    )
    gates, gate_summary = gate_results(reasons)
    evaluated_text = v1.format_timestamp(evaluated_at)
    valid_until = v1.format_timestamp(
        evaluated_at + dt.timedelta(seconds=POLICY["decision_validity_seconds"])
    )
    policy_hash = policy_envelope_sha256()
    prior_hash = prior_active_set_sha256(baseline)

    decision = {
        "schema_version": 2,
        "mode": DECISION_MODE,
        "policy_version": POLICY_VERSION,
        "decision_id": decision_id(
            current_snapshot_sha256=current.evidence.bound.sha256,
            previous_snapshot_sha256=previous.evidence.bound.sha256,
            paper_run_config_sha256=paper.sha256,
            governor_config_sha256=governor.sha256,
            policy_hash=policy_hash,
            prior_set_hash=prior_hash,
            evaluated_at=evaluated_text,
        ),
        "policy_envelope_sha256": policy_hash,
        "status": status,
        "evaluated_at": evaluated_text,
        "valid_until": valid_until,
        "current_snapshot": snapshot_reference(
            current,
            current_producer_git_sha,
        ),
        "previous_snapshot": snapshot_reference(
            previous,
            previous_producer_git_sha,
        ),
        "paper_run_config": {
            "path": str(paper.path),
            "sha256": paper.sha256,
            "producer_git_sha": paper_producer_git_sha,
            "static_allowlist_mode": "pair_variant_direction",
            "static_allowlist_entry_count": len(baseline),
        },
        "governor_config_source": {
            "path": str(governor.path),
            "sha256": governor.sha256,
        },
        "selector_config": v1.SELECTOR_CONFIG,
        "policy": POLICY,
        "prior_active_set_source": PRIOR_SOURCE,
        "prior_active_set_sha256": prior_hash,
        "prior_active_entries": [
            v1.key_object(key) for key in sorted(baseline)
        ],
        "candidates": [candidate.as_dict() for candidate in candidates],
        "selection_steps": steps,
        "selected_entries": [selection.as_dict() for selection in selections],
        "truncated_candidates": truncated,
        "skipped_candidates": skipped,
        "additions": [v1.key_object(key) for key in sorted(additions)],
        "removals": [v1.key_object(key) for key in sorted(removals)],
        "retained_entries": [v1.key_object(key) for key in sorted(retained)],
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
            "candidate_overflow_behavior": "DETERMINISTIC_TRUNCATE_AND_RECORD",
            "concentration_overflow_behavior": "SKIP_AND_CONTINUE",
            "selection_allocation": (
                "RESERVE_BEST_EXPLORATION_ADDITION_FILL_REALIZED_"
                "ALLOW_SECOND_ADDITION"
            ),
            "fallback_behavior": "NO_FALLBACK",
            "policy_hash_formula": "SHA256_CANONICAL_JSON_POLICY_VERSION_AND_POLICY",
            "decision_id_formula": (
                "SHA256_CANONICAL_JSON_BOUND_INPUT_HASHES_POLICY_HASH_"
                "PRIOR_SET_HASH_EVALUATED_AT"
            ),
            "serialization_behavior": "MINIFIED_KEY_SORTED_UTF8_NO_TRAILING_NEWLINE",
            "input_behavior": "READ_ONLY_RAW_HASH_BOUND_STABLE_FILES",
            "output_behavior": "EXCLUSIVE_CREATE_NO_OVERWRITE_REPAIR_OR_REUSE",
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
        "authority": "non_actuating_requires_independent_auto2d_verification",
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
    validate_decision_semantics(decision)
    return decision


def validate_decision_semantics(decision: Mapping[str, Any]) -> None:
    policy_hash = hashlib.sha256(
        v1.canonical_json_bytes(
            {
                "policy_version": decision["policy_version"],
                "policy": decision["policy"],
            }
        )
    ).hexdigest()
    if decision["policy_envelope_sha256"] != policy_hash:
        v1.fail("OUTPUT_POLICY_HASH_MISMATCH")
    baseline = v1.exact_key_set(
        decision["prior_active_entries"],
        "OUTPUT_PRIOR_ACTIVE",
        allow_empty=False,
    )
    prior_hash = prior_active_set_sha256(baseline)
    if decision["prior_active_set_sha256"] != prior_hash:
        v1.fail("OUTPUT_PRIOR_SET_HASH_MISMATCH")
    expected_id = decision_id(
        current_snapshot_sha256=decision["current_snapshot"]["sha256"],
        previous_snapshot_sha256=decision["previous_snapshot"]["sha256"],
        paper_run_config_sha256=decision["paper_run_config"]["sha256"],
        governor_config_sha256=decision["governor_config_source"]["sha256"],
        policy_hash=policy_hash,
        prior_set_hash=prior_hash,
        evaluated_at=decision["evaluated_at"],
    )
    if decision["decision_id"] != expected_id:
        v1.fail("OUTPUT_DECISION_ID_MISMATCH")
    selected = {
        v1.exact_key_from_object(item["key"], "OUTPUT_SELECTED")
        for item in decision["selected_entries"]
    }
    if len(selected) != len(decision["selected_entries"]):
        v1.fail("OUTPUT_SELECTED_DUPLICATE")
    additions = v1.exact_key_set(decision["additions"], "OUTPUT_ADDITIONS")
    removals = v1.exact_key_set(decision["removals"], "OUTPUT_REMOVALS")
    retained = v1.exact_key_set(decision["retained_entries"], "OUTPUT_RETAINED")
    if decision["status"] != "GOVERNOR_BLOCKED" and (
        additions != selected - baseline
        or removals != baseline - selected
        or retained != selected & baseline
    ):
        v1.fail("OUTPUT_TRANSITION_MISMATCH")
    if decision["status"] == "GOVERNOR_BLOCKED":
        empty_fields = (
            "selection_steps",
            "selected_entries",
            "truncated_candidates",
            "skipped_candidates",
            "additions",
            "removals",
            "retained_entries",
        )
        if any(decision[name] for name in empty_fields):
            v1.fail("OUTPUT_BLOCKED_NONEMPTY")
    elif (
        decision["status"] != "POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION"
        or not selected
        or decision["reason_codes"]
    ):
        v1.fail("OUTPUT_STATUS_INVALID")
    if any(decision["authority_boundaries"].values()):
        v1.fail("OUTPUT_AUTHORITY_INVALID")


def render_markdown(decision: Mapping[str, Any]) -> str:
    selected = decision["selected_entries"]
    reasons = decision["reason_codes"]
    lines = [
        "# AUTO-2C v2 Governed Dynamic-Allowlist Decision",
        "",
        f"- Decision ID: `{decision['decision_id']}`",
        f"- Status: `{decision['status']}`",
        f"- Evaluated at: `{decision['evaluated_at']}`",
        f"- Valid until: `{decision['valid_until']}`",
        f"- Policy envelope SHA-256: `{decision['policy_envelope_sha256']}`",
        f"- Prior active-set SHA-256: `{decision['prior_active_set_sha256']}`",
        "",
        "## Authority",
        "",
        "This output is advisory and non-actuating. It cannot change paper",
        "configuration, grant eligibility, start a trial, route an order, deploy,",
        "or approve itself. A later AUTO-2D controller must independently",
        "recompute and verify every bound input and policy result.",
        "",
        "## Bound inputs",
        "",
        (
            f"- Current snapshot: `{decision['current_snapshot']['path']}` "
            f"(`{decision['current_snapshot']['sha256']}`)"
        ),
        (
            f"- Previous snapshot: `{decision['previous_snapshot']['path']}` "
            f"(`{decision['previous_snapshot']['sha256']}`)"
        ),
        (
            f"- Paper run config: `{decision['paper_run_config']['path']}` "
            f"(`{decision['paper_run_config']['sha256']}`)"
        ),
        (
            f"- Governor config: `{decision['governor_config_source']['path']}` "
            f"(`{decision['governor_config_source']['sha256']}`)"
        ),
        "",
        "## Result",
        "",
        f"- Qualifying candidates: {len(decision['candidates'])}",
        f"- Selected entries: {len(selected)}",
        f"- Additions: {len(decision['additions'])}",
        f"- Removals: {len(decision['removals'])}",
        f"- Churn ratio: {decision['calculations']['churn_ratio']}",
        f"- Reasons: {', '.join(reasons) if reasons else 'none'}",
        "",
        "## Selected exact keys",
        "",
    ]
    if selected:
        lines.extend(
            f"- `{key_text(v1.exact_key_from_object(item['key'], 'MARKDOWN_KEY'))}` "
            f"({item['evidence_class']}, rank {item['lane_rank']})"
            for item in selected
        )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Fail-closed and lifecycle boundaries",
            "",
            "- `NONE` and null selector directions remain distinct and non-actionable.",
            "- Unknown selector directions and non-actionable realized directions are rejected.",
            "- Realized-paper and selector-view evidence are never numerically merged.",
            "- Candidate overflow is deterministically truncated and recorded.",
            "- There is no fallback, overwrite, repair, output-root reuse, or automatic restart.",
            "- Expiry or any independent verification mismatch prevents later AUTO-2D use.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_output_paths(
    output_json_value: str | None,
    output_markdown_value: str | None,
    *,
    must_be_absent: bool,
) -> tuple[Path, Path, Path]:
    output_json = v1.require_absolute_path(output_json_value, "OUTPUT_JSON")
    output_markdown = v1.require_absolute_path(
        output_markdown_value,
        "OUTPUT_MARKDOWN",
    )
    if output_json.name != OUTPUT_JSON_NAME:
        v1.fail("OUTPUT_JSON_NAME_INVALID")
    if output_markdown.name != OUTPUT_MARKDOWN_NAME:
        v1.fail("OUTPUT_MARKDOWN_NAME_INVALID")
    if output_json.parent != output_markdown.parent:
        v1.fail("OUTPUT_PARENT_MISMATCH")
    root = output_json.parent
    if must_be_absent:
        if root.exists() or root.is_symlink():
            v1.fail("OUTPUT_ROOT_EXISTS")
        parent = root.parent
        try:
            parent_stat = parent.lstat()
        except FileNotFoundError as error:
            raise v1.GovernorInputError("OUTPUT_ROOT_PARENT_MISSING") from error
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            v1.fail("OUTPUT_ROOT_PARENT_INVALID")
    return root, output_json, output_markdown


def read_bound_raw(
    path_value: str | None,
    expected_sha256: str | None,
    source: str,
) -> RawBoundFile:
    path = v1.require_absolute_path(path_value, f"{source}_PATH")
    expected = v1.require_sha256(expected_sha256, f"{source}_SHA256")
    try:
        path_lstat = path.lstat()
    except FileNotFoundError as error:
        raise v1.GovernorInputError(f"{source}_MISSING") from error
    if stat.S_ISLNK(path_lstat.st_mode):
        v1.fail(f"{source}_SYMLINK")
    if not stat.S_ISREG(path_lstat.st_mode):
        v1.fail(f"{source}_NOT_REGULAR")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise v1.GovernorInputError(f"{source}_OPEN_FAILED") from error
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(before.st_mode) or v1.file_stat_identity(before) != v1.file_stat_identity(after):
        v1.fail(f"{source}_CHANGED_DURING_READ")
    if (path_lstat.st_dev, path_lstat.st_ino) != (before.st_dev, before.st_ino):
        v1.fail(f"{source}_PATH_RACE")
    raw = b"".join(chunks)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        v1.fail(f"{source}_HASH_MISMATCH")
    return RawBoundFile(
        path=path,
        expected_sha256=expected,
        sha256=actual,
        raw_bytes=raw,
        stat_identity=v1.file_stat_identity(after),
    )


def recheck_bound_raw(bound: RawBoundFile, source: str) -> None:
    refreshed = read_bound_raw(
        str(bound.path),
        bound.expected_sha256,
        source,
    )
    if refreshed.stat_identity != bound.stat_identity:
        v1.fail(f"{source}_CHANGED_DURING_VERIFICATION")


def read_and_evaluate(args: argparse.Namespace) -> Evaluation:
    current_producer = v1.require_git_sha(
        args.current_snapshot_producer_git_sha,
        "CURRENT_SNAPSHOT_PRODUCER_GIT_SHA",
    )
    previous_producer = v1.require_git_sha(
        args.previous_snapshot_producer_git_sha,
        "PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA",
    )
    paper_producer = v1.require_git_sha(
        args.paper_run_config_producer_git_sha,
        "PAPER_RUN_CONFIG_PRODUCER_GIT_SHA",
    )
    if args.prior_active_set_source != PRIOR_SOURCE:
        if args.prior_active_set_source == UNSUPPORTED_PRIOR_SOURCE:
            v1.fail("PREVIOUS_ACCEPTED_V2_PAPER_UNIVERSE_NOT_IMPLEMENTED")
        v1.fail("PRIOR_ACTIVE_SET_SOURCE_INVALID")
    evaluated_at = v1.parse_timestamp(args.evaluated_at, "EVALUATED_AT")
    if evaluated_at.microsecond:
        v1.fail("EVALUATED_AT_NOT_CANONICAL_SECONDS")

    current_bound = v1.read_bound_input(
        args.current_snapshot_json,
        args.current_snapshot_sha256,
        "CURRENT_SNAPSHOT",
    )
    previous_bound = v1.read_bound_input(
        args.previous_snapshot_json,
        args.previous_snapshot_sha256,
        "PREVIOUS_SNAPSHOT",
    )
    paper = v1.read_bound_input(
        args.paper_run_config_json,
        args.paper_run_config_sha256,
        "PAPER_RUN_CONFIG",
    )
    governor = v1.read_bound_input(
        args.governor_config_json,
        args.governor_config_sha256,
        "GOVERNOR_CONFIG",
    )
    bound_inputs = (current_bound, previous_bound, paper, governor)
    require_distinct_bound_inputs(bound_inputs)
    if governor.payload != GOVERNOR_CONFIG:
        v1.fail("GOVERNOR_CONFIG_MISMATCH")
    baseline = v1.validate_paper_config(paper)
    current = validate_snapshot_v2(current_bound, "CURRENT")
    previous = validate_snapshot_v2(previous_bound, "PREVIOUS")
    decision = build_decision(
        current=current,
        previous=previous,
        baseline=baseline,
        paper=paper,
        governor=governor,
        current_producer_git_sha=current_producer,
        previous_producer_git_sha=previous_producer,
        paper_producer_git_sha=paper_producer,
        evaluated_at=evaluated_at,
    )
    return Evaluation(
        decision=decision,
        markdown=render_markdown(decision),
        bound_inputs=bound_inputs,
    )


def recheck_inputs(inputs: Sequence[v1.BoundInput]) -> None:
    for source, bound in zip(
        ("CURRENT_SNAPSHOT", "PREVIOUS_SNAPSHOT", "PAPER_RUN_CONFIG", "GOVERNOR_CONFIG"),
        inputs,
    ):
        v1.recheck_bound_input(bound, source)


def run_enabled(args: argparse.Namespace) -> dict[str, Any]:
    root, output_json, output_markdown = validate_output_paths(
        args.output_json,
        args.output_markdown,
        must_be_absent=True,
    )
    evaluation = read_and_evaluate(args)
    json_bytes = v1.canonical_json_bytes(evaluation.decision)
    markdown_bytes = evaluation.markdown.encode("utf-8")
    recheck_inputs(evaluation.bound_inputs)
    if root.exists() or root.is_symlink():
        v1.fail("OUTPUT_ROOT_EXISTS")
    v1.write_outputs_exclusively(
        root,
        output_json,
        output_markdown,
        json_bytes,
        markdown_bytes,
    )
    written_json = read_bound_raw(
        str(output_json),
        hashlib.sha256(json_bytes).hexdigest(),
        "OUTPUT_JSON",
    )
    written_markdown = read_bound_raw(
        str(output_markdown),
        hashlib.sha256(markdown_bytes).hexdigest(),
        "OUTPUT_MARKDOWN",
    )
    if (
        written_json.raw_bytes != json_bytes
        or written_markdown.raw_bytes != markdown_bytes
    ):
        v1.fail("OUTPUT_POSTWRITE_MISMATCH")
    recheck_inputs(evaluation.bound_inputs)
    return {
        "artifact_created": True,
        "decision_id": evaluation.decision["decision_id"],
        "json_sha256": hashlib.sha256(json_bytes).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown_bytes).hexdigest(),
        "mode": DECISION_MODE,
        "output_root": str(root),
        "status": evaluation.decision["status"],
    }


def run_verify_only(args: argparse.Namespace) -> dict[str, Any]:
    _root, output_json, output_markdown = validate_output_paths(
        args.output_json,
        args.output_markdown,
        must_be_absent=False,
    )
    expected_json = read_bound_raw(
        str(output_json),
        args.expected_output_json_sha256,
        "OUTPUT_JSON",
    )
    expected_markdown = read_bound_raw(
        str(output_markdown),
        args.expected_output_markdown_sha256,
        "OUTPUT_MARKDOWN",
    )
    evaluation = read_and_evaluate(args)
    reconstructed_json = v1.canonical_json_bytes(evaluation.decision)
    reconstructed_markdown = evaluation.markdown.encode("utf-8")
    recheck_inputs(evaluation.bound_inputs)
    recheck_bound_raw(expected_json, "OUTPUT_JSON")
    recheck_bound_raw(expected_markdown, "OUTPUT_MARKDOWN")
    if expected_json.raw_bytes != reconstructed_json:
        v1.fail("OUTPUT_JSON_RECONSTRUCTION_MISMATCH")
    if expected_markdown.raw_bytes != reconstructed_markdown:
        v1.fail("OUTPUT_MARKDOWN_RECONSTRUCTION_MISMATCH")
    return {
        "artifact_created": False,
        "decision_id": evaluation.decision["decision_id"],
        "json_sha256": expected_json.sha256,
        "markdown_sha256": expected_markdown.sha256,
        "mode": DECISION_MODE,
        "output_root": str(output_json.parent),
        "status": evaluation.decision["status"],
        "verification": "PASS",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--enabled",
        action="store_true",
        help="Run one offline non-actuating v2 governor evaluation.",
    )
    mode.add_argument(
        "--verify-only",
        action="store_true",
        help="Read and reconstruct existing outputs without creating files.",
    )
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
    parser.add_argument("--output-json")
    parser.add_argument("--output-markdown")
    parser.add_argument("--expected-output-json-sha256")
    parser.add_argument("--expected-output-markdown-sha256")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.enabled and not args.verify_only:
        print(
            json.dumps(
                DISABLED_DIAGNOSTIC,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    try:
        result = run_verify_only(args) if args.verify_only else run_enabled(args)
    except v1.GovernorInputError as error:
        print(
            json.dumps(
                {
                    "artifact_created": False,
                    "error_code": error.code,
                    "mode": DECISION_MODE,
                    "status": "INPUT_REJECTED",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "artifact_created": False,
                    "error_code": "FILESYSTEM_OPERATION_FAILED",
                    "mode": DECISION_MODE,
                    "status": "INPUT_REJECTED",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
