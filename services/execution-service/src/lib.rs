use common_types::DataIntegrityReport;

#[derive(Debug, Clone, Copy)]
pub struct ExecutionGateConfig {
    pub min_coverage_pct: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GateDecision {
    Allowed,
    Blocked(String),
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

#[cfg(test)]
mod tests {
    use super::{evaluate_integrity_gate, ExecutionGateConfig, GateDecision};
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
}
