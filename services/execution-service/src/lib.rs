use common_types::DataIntegrityReport;
use common_types::{IntegrityStatus, Timeframe};
use tokio_postgres::NoTls;

#[derive(Debug, Clone, Copy)]
pub struct ExecutionGateConfig {
    pub min_coverage_pct: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GateDecision {
    Allowed,
    Blocked(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OrderIntentDecision {
    Accepted,
    Blocked(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReconcileDecision {
    Allowed,
    Blocked(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrderLifecycleState {
    New,
    Approved,
    PendingSubmit,
    Acknowledged,
    PartiallyFilled,
    Filled,
    Canceled,
    Rejected,
    Expired,
}

impl OrderLifecycleState {
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "NEW" => Some(Self::New),
            "APPROVED" => Some(Self::Approved),
            "PENDING_SUBMIT" => Some(Self::PendingSubmit),
            "ACKNOWLEDGED" => Some(Self::Acknowledged),
            "PARTIALLY_FILLED" => Some(Self::PartiallyFilled),
            "FILLED" => Some(Self::Filled),
            "CANCELED" => Some(Self::Canceled),
            "REJECTED" => Some(Self::Rejected),
            "EXPIRED" => Some(Self::Expired),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::New => "NEW",
            Self::Approved => "APPROVED",
            Self::PendingSubmit => "PENDING_SUBMIT",
            Self::Acknowledged => "ACKNOWLEDGED",
            Self::PartiallyFilled => "PARTIALLY_FILLED",
            Self::Filled => "FILLED",
            Self::Canceled => "CANCELED",
            Self::Rejected => "REJECTED",
            Self::Expired => "EXPIRED",
        }
    }
}

pub fn can_transition_state(from: OrderLifecycleState, to: OrderLifecycleState) -> bool {
    matches!(
        (from, to),
        (OrderLifecycleState::New, OrderLifecycleState::Approved)
            | (
                OrderLifecycleState::Approved,
                OrderLifecycleState::PendingSubmit
            )
            | (
                OrderLifecycleState::PendingSubmit,
                OrderLifecycleState::Acknowledged
            )
            | (
                OrderLifecycleState::PendingSubmit,
                OrderLifecycleState::Rejected
            )
            | (
                OrderLifecycleState::Acknowledged,
                OrderLifecycleState::PartiallyFilled
            )
            | (
                OrderLifecycleState::Acknowledged,
                OrderLifecycleState::Filled
            )
            | (
                OrderLifecycleState::Acknowledged,
                OrderLifecycleState::Canceled
            )
            | (
                OrderLifecycleState::Acknowledged,
                OrderLifecycleState::Rejected
            )
            | (
                OrderLifecycleState::Acknowledged,
                OrderLifecycleState::Expired
            )
            | (
                OrderLifecycleState::PartiallyFilled,
                OrderLifecycleState::Filled
            )
            | (
                OrderLifecycleState::PartiallyFilled,
                OrderLifecycleState::Canceled
            )
            | (
                OrderLifecycleState::PartiallyFilled,
                OrderLifecycleState::Rejected
            )
            | (
                OrderLifecycleState::PartiallyFilled,
                OrderLifecycleState::Expired
            )
            | (
                OrderLifecycleState::PendingSubmit,
                OrderLifecycleState::Expired
            )
    )
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrderIntentAction {
    Entry,
    Exit,
    EmergencyStopClose,
}

impl OrderIntentAction {
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "ENTRY" => Some(Self::Entry),
            "EXIT" => Some(Self::Exit),
            "EMERGENCY_STOP_CLOSE" => Some(Self::EmergencyStopClose),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Entry => "ENTRY",
            Self::Exit => "EXIT",
            Self::EmergencyStopClose => "EMERGENCY_STOP_CLOSE",
        }
    }
}

pub fn evaluate_integrity_gate(
    report: &DataIntegrityReport,
    config: ExecutionGateConfig,
) -> GateDecision {
    if report.is_live_eligible(config.min_coverage_pct) {
        GateDecision::Allowed
    } else {
        GateDecision::Blocked(format!(
            "integrity gate blocked signal: status={} coverage_pct={:.4} threshold_pct={:.4}",
            report.status.as_str(),
            report.coverage_pct,
            config.min_coverage_pct
        ))
    }
}

pub fn evaluate_order_intent(
    action: OrderIntentAction,
    kill_switch_active: bool,
    gate_decision: GateDecision,
    reconcile_decision: ReconcileDecision,
) -> OrderIntentDecision {
    if matches!(action, OrderIntentAction::EmergencyStopClose) {
        return OrderIntentDecision::Accepted;
    }

    if kill_switch_active {
        return OrderIntentDecision::Blocked(
            "kill switch is active; order intent blocked".to_string(),
        );
    }
    match gate_decision {
        GateDecision::Allowed => {}
        GateDecision::Blocked(reason) => return OrderIntentDecision::Blocked(reason),
    }
    match reconcile_decision {
        ReconcileDecision::Allowed => OrderIntentDecision::Accepted,
        ReconcileDecision::Blocked(reason) => OrderIntentDecision::Blocked(reason),
    }
}

pub fn normalize_side(value: &str) -> Option<&'static str> {
    match value {
        "BUY" | "buy" | "Buy" => Some("BUY"),
        "SELL" | "sell" | "Sell" => Some("SELL"),
        _ => None,
    }
}

pub async fn evaluate_integrity_gate_from_store(
    postgres_url: &str,
    instrument: &str,
    timeframe: Timeframe,
    min_coverage_pct: f64,
) -> anyhow::Result<GateDecision> {
    let (client, connection) = tokio_postgres::connect(postgres_url, NoTls).await?;
    tokio::spawn(async move {
        let _ = connection.await;
    });

    let row = client
        .query_opt(
            "SELECT status, coverage_pct
             FROM data_quality_intervals
             WHERE instrument=$1 AND timeframe=$2
             ORDER BY checked_at DESC
             LIMIT 1",
            &[&instrument, &timeframe.as_str()],
        )
        .await?;

    let Some(row) = row else {
        return Ok(GateDecision::Blocked(format!(
            "integrity gate blocked signal: no integrity history for instrument={instrument} timeframe={}",
            timeframe.as_str()
        )));
    };

    let status_raw: String = row.get(0);
    let coverage_pct: f64 = row.get(1);
    let status = parse_integrity_status(&status_raw).unwrap_or(IntegrityStatus::Failed);

    let report = DataIntegrityReport {
        status,
        coverage_pct,
        missing_ranges: vec![],
        last_verified_at: chrono::Utc::now(),
        warnings: vec![],
    };
    Ok(evaluate_integrity_gate(
        &report,
        ExecutionGateConfig { min_coverage_pct },
    ))
}

fn parse_integrity_status(value: &str) -> Option<IntegrityStatus> {
    match value {
        "COMPLETE" => Some(IntegrityStatus::Complete),
        "PARTIAL_BACKFILLED" => Some(IntegrityStatus::PartialBackfilled),
        "INCOMPLETE" => Some(IntegrityStatus::Incomplete),
        "STALE" => Some(IntegrityStatus::Stale),
        "FAILED" => Some(IntegrityStatus::Failed),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        can_transition_state, evaluate_integrity_gate, evaluate_order_intent, normalize_side,
        parse_integrity_status, ExecutionGateConfig, GateDecision, OrderIntentAction,
        OrderIntentDecision, OrderLifecycleState, ReconcileDecision,
    };
    use chrono::Utc;
    use common_types::{DataIntegrityReport, IntegrityStatus};

    #[test]
    fn gate_blocks_when_coverage_below_threshold() {
        let report = DataIntegrityReport {
            status: IntegrityStatus::Incomplete,
            coverage_pct: 99.4,
            missing_ranges: vec![],
            last_verified_at: Utc::now(),
            warnings: vec![],
        };
        let decision = evaluate_integrity_gate(
            &report,
            ExecutionGateConfig {
                min_coverage_pct: 99.5,
            },
        );
        assert!(matches!(decision, GateDecision::Blocked(_)));
    }

    #[test]
    fn gate_allows_when_coverage_and_status_pass() {
        let report = DataIntegrityReport {
            status: IntegrityStatus::Complete,
            coverage_pct: 100.0,
            missing_ranges: vec![],
            last_verified_at: Utc::now(),
            warnings: vec![],
        };
        let decision = evaluate_integrity_gate(
            &report,
            ExecutionGateConfig {
                min_coverage_pct: 99.5,
            },
        );
        assert_eq!(decision, GateDecision::Allowed);
    }

    #[test]
    fn parse_integrity_status_handles_known_values() {
        assert_eq!(
            parse_integrity_status("COMPLETE"),
            Some(IntegrityStatus::Complete)
        );
        assert_eq!(parse_integrity_status("UNKNOWN"), None);
    }

    #[test]
    fn order_intent_blocks_when_kill_switch_active() {
        let decision = evaluate_order_intent(
            OrderIntentAction::Entry,
            true,
            GateDecision::Allowed,
            ReconcileDecision::Allowed,
        );
        assert!(matches!(decision, OrderIntentDecision::Blocked(_)));
    }

    #[test]
    fn order_intent_accepts_when_gate_allows_and_kill_switch_off() {
        let decision = evaluate_order_intent(
            OrderIntentAction::Exit,
            false,
            GateDecision::Allowed,
            ReconcileDecision::Allowed,
        );
        assert_eq!(decision, OrderIntentDecision::Accepted);
    }

    #[test]
    fn emergency_stop_close_is_allowed_even_when_gated() {
        let decision = evaluate_order_intent(
            OrderIntentAction::EmergencyStopClose,
            true,
            GateDecision::Blocked("integrity failed".to_string()),
            ReconcileDecision::Blocked("reconcile failed".to_string()),
        );
        assert_eq!(decision, OrderIntentDecision::Accepted);
    }

    #[test]
    fn order_intent_blocks_when_reconcile_blocked() {
        let decision = evaluate_order_intent(
            OrderIntentAction::Entry,
            false,
            GateDecision::Allowed,
            ReconcileDecision::Blocked("drift exceeded".to_string()),
        );
        assert!(matches!(decision, OrderIntentDecision::Blocked(_)));
    }

    #[test]
    fn normalize_side_accepts_buy_sell_variants() {
        assert_eq!(normalize_side("BUY"), Some("BUY"));
        assert_eq!(normalize_side("sell"), Some("SELL"));
        assert_eq!(normalize_side("HOLD"), None);
    }

    #[test]
    fn lifecycle_transition_rules_are_deterministic() {
        assert!(can_transition_state(
            OrderLifecycleState::New,
            OrderLifecycleState::Approved
        ));
        assert!(can_transition_state(
            OrderLifecycleState::PendingSubmit,
            OrderLifecycleState::Rejected
        ));
        assert!(can_transition_state(
            OrderLifecycleState::Acknowledged,
            OrderLifecycleState::Filled
        ));
        assert!(can_transition_state(
            OrderLifecycleState::Acknowledged,
            OrderLifecycleState::Expired
        ));
        assert!(can_transition_state(
            OrderLifecycleState::PartiallyFilled,
            OrderLifecycleState::Expired
        ));
        assert!(!can_transition_state(
            OrderLifecycleState::Filled,
            OrderLifecycleState::Acknowledged
        ));
    }

    #[test]
    fn lifecycle_state_parse_round_trip() {
        let states = [
            OrderLifecycleState::New,
            OrderLifecycleState::Approved,
            OrderLifecycleState::PendingSubmit,
            OrderLifecycleState::Acknowledged,
            OrderLifecycleState::PartiallyFilled,
            OrderLifecycleState::Filled,
            OrderLifecycleState::Canceled,
            OrderLifecycleState::Rejected,
            OrderLifecycleState::Expired,
        ];

        for state in states {
            let raw = state.as_str();
            assert_eq!(OrderLifecycleState::parse(raw), Some(state));
        }
        assert_eq!(OrderLifecycleState::parse("UNKNOWN"), None);
    }
}
