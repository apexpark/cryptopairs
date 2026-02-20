use common_types::DataIntegrityReport;
use common_types::{IntegrityStatus, Timeframe};
use tokio_postgres::NoTls;

#[derive(Debug, Clone, Copy)]
pub struct ExecutionGateConfig {
    pub min_coverage_pct: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct RiskCapsConfig {
    pub per_pair_max_qty: f64,
    pub gross_max_qty: f64,
    pub max_leverage: f64,
    pub daily_loss_limit_usd: f64,
    pub entry_cooldown_seconds: i64,
}

#[derive(Debug, Clone, Copy)]
pub struct RiskCheckInput {
    pub active_pair_qty: f64,
    pub active_gross_qty: f64,
    pub request_qty: f64,
    pub leverage: f64,
    pub daily_loss_usd: f64,
    pub seconds_since_last_entry: Option<i64>,
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
    risk_decision: GateDecision,
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
        ReconcileDecision::Allowed => {}
        ReconcileDecision::Blocked(reason) => return OrderIntentDecision::Blocked(reason),
    }
    match risk_decision {
        GateDecision::Allowed => OrderIntentDecision::Accepted,
        GateDecision::Blocked(reason) => OrderIntentDecision::Blocked(reason),
    }
}

pub fn evaluate_risk_caps(
    action: OrderIntentAction,
    input: RiskCheckInput,
    config: RiskCapsConfig,
) -> GateDecision {
    if !matches!(action, OrderIntentAction::Entry) {
        return GateDecision::Allowed;
    }
    if !input.request_qty.is_finite() || input.request_qty <= 0.0 {
        return GateDecision::Blocked(
            "risk gate blocked signal: request_qty must be finite and > 0".to_string(),
        );
    }
    if !input.active_pair_qty.is_finite() || !input.active_gross_qty.is_finite() {
        return GateDecision::Blocked(
            "risk gate blocked signal: active exposure snapshot is invalid".to_string(),
        );
    }
    if !input.leverage.is_finite() {
        return GateDecision::Blocked(
            "risk gate blocked signal: leverage snapshot is invalid".to_string(),
        );
    }
    if !input.daily_loss_usd.is_finite() {
        return GateDecision::Blocked(
            "risk gate blocked signal: daily loss snapshot is invalid".to_string(),
        );
    }

    let projected_pair_qty = input.active_pair_qty + input.request_qty;
    if projected_pair_qty > config.per_pair_max_qty {
        return GateDecision::Blocked(format!(
            "risk gate blocked signal: per_pair_cap exceeded projected_pair_qty={projected_pair_qty:.4} cap={:.4}",
            config.per_pair_max_qty
        ));
    }

    let projected_gross_qty = input.active_gross_qty + input.request_qty;
    if projected_gross_qty > config.gross_max_qty {
        return GateDecision::Blocked(format!(
            "risk gate blocked signal: gross_cap exceeded projected_gross_qty={projected_gross_qty:.4} cap={:.4}",
            config.gross_max_qty
        ));
    }

    if input.leverage > config.max_leverage {
        return GateDecision::Blocked(format!(
            "risk gate blocked signal: leverage exceeded leverage={:.4} cap={:.4}",
            input.leverage, config.max_leverage
        ));
    }

    if input.daily_loss_usd >= config.daily_loss_limit_usd {
        return GateDecision::Blocked(format!(
            "risk gate blocked signal: daily_loss exceeded daily_loss_usd={:.4} cap={:.4}",
            input.daily_loss_usd, config.daily_loss_limit_usd
        ));
    }

    if config.entry_cooldown_seconds > 0 {
        if let Some(seconds_since_last_entry) = input.seconds_since_last_entry {
            if seconds_since_last_entry < config.entry_cooldown_seconds {
                return GateDecision::Blocked(format!(
                    "risk gate blocked signal: cooldown active seconds_since_last_entry={seconds_since_last_entry} cooldown_seconds={}",
                    config.entry_cooldown_seconds
                ));
            }
        }
    }

    GateDecision::Allowed
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
        can_transition_state, evaluate_integrity_gate, evaluate_order_intent, evaluate_risk_caps,
        normalize_side, parse_integrity_status, ExecutionGateConfig, GateDecision,
        OrderIntentAction, OrderIntentDecision, OrderLifecycleState, ReconcileDecision,
        RiskCapsConfig, RiskCheckInput,
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
            GateDecision::Allowed,
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
            GateDecision::Allowed,
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
            GateDecision::Blocked("risk failed".to_string()),
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
            GateDecision::Allowed,
        );
        assert!(matches!(decision, OrderIntentDecision::Blocked(_)));
    }

    #[test]
    fn order_intent_blocks_when_risk_gate_blocks() {
        let decision = evaluate_order_intent(
            OrderIntentAction::Entry,
            false,
            GateDecision::Allowed,
            ReconcileDecision::Allowed,
            GateDecision::Blocked("risk cap".to_string()),
        );
        assert!(matches!(decision, OrderIntentDecision::Blocked(_)));
    }

    #[test]
    fn risk_caps_block_when_per_pair_cap_exceeded() {
        let decision = evaluate_risk_caps(
            OrderIntentAction::Entry,
            RiskCheckInput {
                active_pair_qty: 4.0,
                active_gross_qty: 8.0,
                request_qty: 2.0,
                leverage: 1.2,
                daily_loss_usd: 10.0,
                seconds_since_last_entry: Some(120),
            },
            RiskCapsConfig {
                per_pair_max_qty: 5.0,
                gross_max_qty: 20.0,
                max_leverage: 3.0,
                daily_loss_limit_usd: 500.0,
                entry_cooldown_seconds: 30,
            },
        );
        assert!(matches!(decision, GateDecision::Blocked(_)));
    }

    #[test]
    fn risk_caps_allow_entry_when_limits_are_safe() {
        let decision = evaluate_risk_caps(
            OrderIntentAction::Entry,
            RiskCheckInput {
                active_pair_qty: 2.0,
                active_gross_qty: 6.0,
                request_qty: 1.0,
                leverage: 1.2,
                daily_loss_usd: 30.0,
                seconds_since_last_entry: Some(120),
            },
            RiskCapsConfig {
                per_pair_max_qty: 5.0,
                gross_max_qty: 20.0,
                max_leverage: 3.0,
                daily_loss_limit_usd: 500.0,
                entry_cooldown_seconds: 30,
            },
        );
        assert_eq!(decision, GateDecision::Allowed);
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
