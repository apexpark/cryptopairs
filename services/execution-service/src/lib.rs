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
        evaluate_integrity_gate, parse_integrity_status, ExecutionGateConfig, GateDecision,
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
}
