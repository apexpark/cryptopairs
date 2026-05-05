mod strategy_service_bin {
    #![allow(dead_code)]
    #![allow(clippy::items_after_test_module)]

    include!("../src/main.rs");

    #[cfg(test)]
    mod repository_integration {
        use super::*;
        use chrono::{DateTime, TimeZone, Utc};
        use common_types::Timeframe;
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::time::{SystemTime, UNIX_EPOCH};
        use strategy_service::{
            CostGateDiagnostics, PairCue, PairEvaluationOutput, PortfolioHint,
            SetupGateDiagnostics, ShadowMlDiagnostics, TradeGateDiagnostics, VariantEvaluation,
        };
        use tokio::task::JoinHandle;
        use tokio_postgres::{Client, NoTls};

        const TEST_DATABASE_URL_ENV: &str = "STRATEGY_TEST_DATABASE_URL";
        static SCHEMA_COUNTER: AtomicUsize = AtomicUsize::new(0);

        struct PgFixture {
            database_url: String,
            schema: String,
            client: std::sync::Arc<Client>,
            repository: StrategyRepository,
            connection_task: JoinHandle<()>,
        }

        impl PgFixture {
            async fn connect(test_name: &str) -> anyhow::Result<Option<Self>> {
                let database_url = match std::env::var(TEST_DATABASE_URL_ENV) {
                    Ok(value) if !value.trim().is_empty() => value,
                    _ if matches!(std::env::var("CI").as_deref(), Ok("true")) => {
                        anyhow::bail!(
                            "{TEST_DATABASE_URL_ENV} must be set when CI=true for {test_name}"
                        );
                    }
                    _ => {
                        println!("SKIPPED {test_name}: {TEST_DATABASE_URL_ENV} unset");
                        return Ok(None);
                    }
                };

                let schema = next_schema_name()?;
                let (raw_client, connection) =
                    tokio_postgres::connect(&database_url, NoTls).await?;
                let connection_task = tokio::spawn(async move {
                    if let Err(error) = connection.await {
                        eprintln!("repository integration postgres connection ended: {error}");
                    }
                });
                let client = std::sync::Arc::new(raw_client);
                client
                    .batch_execute(&format!("CREATE SCHEMA {}", quote_identifier(&schema)))
                    .await?;
                client
                    .batch_execute(&format!(
                        "SET search_path TO {}, public",
                        quote_identifier(&schema)
                    ))
                    .await?;

                let repository = StrategyRepository {
                    client: std::sync::Arc::clone(&client),
                };
                repository.ensure_schema().await?;

                Ok(Some(Self {
                    database_url,
                    schema,
                    client,
                    repository,
                    connection_task,
                }))
            }

            async fn selected_signal_count(&self) -> anyhow::Result<i64> {
                let row = self
                    .client
                    .query_one("SELECT COUNT(*) FROM strategy_selected_signal", &[])
                    .await?;
                Ok(row.get(0))
            }

            async fn selected_signal_for(
                &self,
                pair_id: &str,
                timeframe: Timeframe,
            ) -> anyhow::Result<(String, f64, DateTime<Utc>)> {
                let row = self
                    .client
                    .query_one(
                        "SELECT signal_variant, opportunity_score, updated_at
                         FROM strategy_selected_signal
                         WHERE pair_id=$1 AND timeframe=$2",
                        &[&pair_id, &timeframe.as_str()],
                    )
                    .await?;
                Ok((row.get(0), row.get(1), row.get(2)))
            }

            async fn drift_decisions_for(
                &self,
                pair_id: &str,
                timeframe: Timeframe,
            ) -> anyhow::Result<Vec<String>> {
                let rows = self
                    .client
                    .query(
                        "SELECT decision
                         FROM strategy_champion_drift_events
                         WHERE pair_id=$1 AND timeframe=$2
                         ORDER BY event_at",
                        &[&pair_id, &timeframe.as_str()],
                    )
                    .await?;
                Ok(rows.into_iter().map(|row| row.get(0)).collect())
            }

            async fn drift_row_count(&self) -> anyhow::Result<i64> {
                let row = self
                    .client
                    .query_one("SELECT COUNT(*) FROM strategy_champion_drift_events", &[])
                    .await?;
                Ok(row.get(0))
            }
        }

        impl Drop for PgFixture {
            fn drop(&mut self) {
                self.connection_task.abort();
                if let Err(error) = drop_schema_blocking(&self.database_url, &self.schema) {
                    eprintln!(
                        "FAILED to drop postgres test schema {}: {error:#}",
                        self.schema
                    );
                }
            }
        }

        #[tokio::test]
        async fn record_evaluation_writes_selected_and_drift_rows() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("record_evaluation_writes_selected_and_drift_rows").await?
            else {
                return Ok(());
            };
            let timeframe = Timeframe::OneMinute;

            let initialize_pair = "B6_RECORD_INITIALIZE";
            let initialize_summary = fixture
                .repository
                .record_evaluation(
                    timeframe,
                    &evaluation(
                        initialize_pair,
                        "VOL_NORMALIZED",
                        2.0,
                        1.0,
                        2.0,
                        test_time(1_778_000_001)?,
                    ),
                    0.25,
                )
                .await?;
            assert_transition_counts(&initialize_summary, 1, 0, 0, 0);
            assert_eq!(initialize_summary.selected_rows_written, 1);
            assert_eq!(initialize_summary.drift_rows_written, 0);
            assert!(
                fixture
                    .drift_decisions_for(initialize_pair, timeframe)
                    .await?
                    .is_empty()
            );

            let unchanged_pair = "B6_RECORD_UNCHANGED";
            fixture
                .repository
                .upsert_selected_signal(
                    unchanged_pair,
                    timeframe,
                    "VOL_NORMALIZED",
                    1.5,
                    test_time(1_778_000_010)?,
                )
                .await?;
            let unchanged_summary = fixture
                .repository
                .record_evaluation(
                    timeframe,
                    &evaluation(
                        unchanged_pair,
                        "VOL_NORMALIZED",
                        2.1,
                        1.0,
                        2.1,
                        test_time(1_778_000_011)?,
                    ),
                    0.25,
                )
                .await?;
            assert_transition_counts(&unchanged_summary, 0, 1, 0, 0);
            assert_eq!(unchanged_summary.selected_rows_written, 1);
            assert_eq!(unchanged_summary.drift_rows_written, 0);
            assert!(
                fixture
                    .drift_decisions_for(unchanged_pair, timeframe)
                    .await?
                    .is_empty()
            );

            let promote_pair = "B6_RECORD_PROMOTE";
            fixture
                .repository
                .upsert_selected_signal(
                    promote_pair,
                    timeframe,
                    "ROBUST_Z",
                    1.0,
                    test_time(1_778_000_020)?,
                )
                .await?;
            let promote_summary = fixture
                .repository
                .record_evaluation(
                    timeframe,
                    &evaluation(
                        promote_pair,
                        "VOL_NORMALIZED",
                        2.0,
                        1.0,
                        2.0,
                        test_time(1_778_000_021)?,
                    ),
                    0.25,
                )
                .await?;
            assert_transition_counts(&promote_summary, 0, 0, 1, 0);
            assert_eq!(promote_summary.selected_rows_written, 1);
            assert_eq!(promote_summary.drift_rows_written, 1);
            assert_eq!(
                fixture.drift_decisions_for(promote_pair, timeframe).await?,
                vec!["PROMOTE_CHALLENGER".to_string()]
            );

            let keep_pair = "B6_RECORD_KEEP";
            fixture
                .repository
                .upsert_selected_signal(
                    keep_pair,
                    timeframe,
                    "ROBUST_Z",
                    1.0,
                    test_time(1_778_000_030)?,
                )
                .await?;
            let keep_summary = fixture
                .repository
                .record_evaluation(
                    timeframe,
                    &evaluation(
                        keep_pair,
                        "VOL_NORMALIZED",
                        1.1,
                        1.0,
                        1.1,
                        test_time(1_778_000_031)?,
                    ),
                    0.25,
                )
                .await?;
            assert_transition_counts(&keep_summary, 0, 0, 0, 1);
            assert_eq!(keep_summary.selected_rows_written, 1);
            assert_eq!(keep_summary.drift_rows_written, 1);
            assert_eq!(
                fixture.drift_decisions_for(keep_pair, timeframe).await?,
                vec!["KEEP_CHAMPION".to_string()]
            );

            assert_eq!(fixture.selected_signal_count().await?, 4);
            assert_eq!(fixture.drift_row_count().await?, 2);

            let (keep_variant, keep_score, _) =
                fixture.selected_signal_for(keep_pair, timeframe).await?;
            assert_eq!(keep_variant, "ROBUST_Z");
            assert!((keep_score - 1.0).abs() < f64::EPSILON);

            Ok(())
        }

        #[tokio::test]
        async fn upsert_selected_signal_on_conflict_keeps_latest_row() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("upsert_selected_signal_on_conflict_keeps_latest_row").await?
            else {
                return Ok(());
            };
            let pair_id = "B6_UPSERT_SELECTED_SIGNAL";
            let timeframe = Timeframe::FifteenMinutes;
            let latest_updated_at = test_time(1_778_100_060)?;

            fixture
                .repository
                .upsert_selected_signal(
                    pair_id,
                    timeframe,
                    "ROBUST_Z",
                    1.25,
                    test_time(1_778_100_000)?,
                )
                .await?;
            fixture
                .repository
                .upsert_selected_signal(
                    pair_id,
                    timeframe,
                    "VOL_NORMALIZED",
                    2.75,
                    latest_updated_at,
                )
                .await?;

            assert_eq!(fixture.selected_signal_count().await?, 1);
            let (variant, score, updated_at) =
                fixture.selected_signal_for(pair_id, timeframe).await?;
            assert_eq!(variant, "VOL_NORMALIZED");
            assert!((score - 2.75).abs() < f64::EPSILON);
            assert_eq!(updated_at, latest_updated_at);

            Ok(())
        }

        fn assert_transition_counts(
            summary: &PersistSummary,
            initialize: usize,
            unchanged: usize,
            promotions: usize,
            locks: usize,
        ) {
            assert_eq!(
                summary.transition_counts.initialize_decisions,
                initialize
            );
            assert_eq!(summary.transition_counts.unchanged_decisions, unchanged);
            assert_eq!(summary.transition_counts.champion_promotions, promotions);
            assert_eq!(summary.transition_counts.champion_locks, locks);
        }

        fn evaluation(
            pair_id: &str,
            selected_variant: &str,
            selected_score: f64,
            champion_score: f64,
            challenger_score: f64,
            evaluated_at: DateTime<Utc>,
        ) -> PairEvaluationOutput {
            PairEvaluationOutput {
                cue: PairCue {
                    pair_id: pair_id.to_string(),
                    left_instrument: format!("{pair_id}_LEFT"),
                    right_instrument: format!("{pair_id}_RIGHT"),
                    timeframe: Timeframe::OneMinute.as_str().to_string(),
                    regime: "CALM".to_string(),
                    selected_variant: selected_variant.to_string(),
                    direction_hint: "NONE".to_string(),
                    spread_z: 0.0,
                    opportunity_score: selected_score,
                    confidence_band: "MEDIUM".to_string(),
                    entry_band: 1.8,
                    exit_band: 0.6,
                    stop_band: 3.2,
                    expected_hold_bars: 12,
                    cost_estimate_bps: 1.0,
                    setup_actionable: false,
                    actionable: false,
                    rationale_codes: vec!["B6_REPOSITORY_TEST".to_string()],
                    setup_gate: SetupGateDiagnostics::unavailable(vec![]),
                    cost_gate: CostGateDiagnostics::unavailable(vec![]),
                    trade_gate: TradeGateDiagnostics::unavailable(vec![]),
                    portfolio_hint: PortfolioHint::unavailable(vec![]),
                    shadow_ml: ShadowMlDiagnostics::unavailable(vec![]),
                    selection_state: None,
                    evaluated_at,
                },
                variants: vec![
                    VariantEvaluation {
                        variant: "ROBUST_Z".to_string(),
                        score_last: champion_score,
                        sample_count: 100,
                        win_rate: 0.56,
                        edge_bps: champion_score,
                        reliability: 0.7,
                        regime_fit: 0.8,
                        opportunity_score: champion_score,
                        shadow_success_probability: None,
                        shadow_rank_score: None,
                        rationale_codes: vec!["B6_CHAMPION".to_string()],
                    },
                    VariantEvaluation {
                        variant: "VOL_NORMALIZED".to_string(),
                        score_last: challenger_score,
                        sample_count: 100,
                        win_rate: 0.57,
                        edge_bps: challenger_score,
                        reliability: 0.7,
                        regime_fit: 0.8,
                        opportunity_score: challenger_score,
                        shadow_success_probability: None,
                        shadow_rank_score: None,
                        rationale_codes: vec!["B6_CHALLENGER".to_string()],
                    },
                ],
                half_life_bars: 12.0,
                hedge_ratio: 1.0,
                hedge_ratio_stability: 0.1,
                spread_vol_bps: 2.0,
                stored_champion_variant: None,
                stored_champion_projection: None,
            }
        }

        fn test_time(seconds: i64) -> anyhow::Result<DateTime<Utc>> {
            Utc.timestamp_opt(seconds, 0)
                .single()
                .ok_or_else(|| anyhow::anyhow!("invalid test timestamp {}", seconds))
        }

        fn next_schema_name() -> anyhow::Result<String> {
            let unix_seconds = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
            let process_id = std::process::id();
            let counter = SCHEMA_COUNTER.fetch_add(1, Ordering::SeqCst);
            Ok(format!(
                "strategy_test_{unix_seconds}_{process_id}_{counter:03}"
            ))
        }

        fn quote_identifier(identifier: &str) -> String {
            format!("\"{}\"", identifier.replace('"', "\"\""))
        }

        fn drop_schema_blocking(database_url: &str, schema: &str) -> anyhow::Result<()> {
            let database_url = database_url.to_string();
            let schema = schema.to_string();
            let handle = std::thread::spawn(move || -> anyhow::Result<()> {
                let runtime = tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()?;
                runtime.block_on(async move {
                    let (client, connection) =
                        tokio_postgres::connect(&database_url, NoTls).await?;
                    let connection_task = tokio::spawn(async move {
                        let _ = connection.await;
                    });
                    let result = client
                        .batch_execute(&format!(
                            "DROP SCHEMA IF EXISTS {} CASCADE",
                            quote_identifier(&schema)
                        ))
                        .await;
                    drop(client);
                    connection_task.abort();
                    result.map_err(anyhow::Error::from)
                })
            });

            match handle.join() {
                Ok(result) => result,
                Err(_) => anyhow::bail!("postgres schema cleanup thread panicked"),
            }
        }
    }
}
