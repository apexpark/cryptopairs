mod strategy_service_bin {
    #![allow(dead_code)]
    #![allow(clippy::items_after_test_module)]

    include!("../src/main.rs");

    #[cfg(test)]
    mod repository_integration {
        use super::*;
        use chrono::{DateTime, TimeZone, Utc};
        use common_types::Timeframe;
        use std::fs;
        use std::path::PathBuf;
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::time::{SystemTime, UNIX_EPOCH};
        use strategy_service::{
            CostGateDiagnostics, PairCue, PairEvaluationOutput, PortfolioHint,
            SelectedSignalConfig, SetupGateDiagnostics, ShadowMlDiagnostics,
            SignalFlatlineDiagnostics, TradeGateDiagnostics, VariantEvaluation,
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
            let settings = StrategySettings::from_env();

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
                    &settings,
                )
                .await?;
            assert_transition_counts(&initialize_summary, 1, 0, 0, 0);
            assert_eq!(initialize_summary.selected_rows_written, 1);
            assert_eq!(initialize_summary.drift_rows_written, 0);
            assert!(fixture
                .drift_decisions_for(initialize_pair, timeframe)
                .await?
                .is_empty());

            let unchanged_pair = "B6_RECORD_UNCHANGED";
            fixture
                .repository
                .upsert_selected_signal(
                    unchanged_pair,
                    timeframe,
                    "VOL_NORMALIZED",
                    1.5,
                    &selected_signal_config("VOL_NORMALIZED", test_time(1_778_000_010)?),
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
                    &settings,
                )
                .await?;
            assert_transition_counts(&unchanged_summary, 0, 1, 0, 0);
            assert_eq!(unchanged_summary.selected_rows_written, 1);
            assert_eq!(unchanged_summary.drift_rows_written, 0);
            assert!(fixture
                .drift_decisions_for(unchanged_pair, timeframe)
                .await?
                .is_empty());

            let promote_pair = "B6_RECORD_PROMOTE";
            fixture
                .repository
                .upsert_selected_signal(
                    promote_pair,
                    timeframe,
                    "ROBUST_Z",
                    1.0,
                    &selected_signal_config("ROBUST_Z", test_time(1_778_000_020)?),
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
                    &settings,
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
                    &selected_signal_config("ROBUST_Z", test_time(1_778_000_030)?),
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
                    &settings,
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
                    &selected_signal_config("ROBUST_Z", test_time(1_778_100_000)?),
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
                    &selected_signal_config("VOL_NORMALIZED", latest_updated_at),
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

        #[tokio::test]
        async fn reoptimize_lease_acquire_succeeds_once() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("reoptimize_lease_acquire_succeeds_once").await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_lease_once";
            let now = test_time(1_779_000_001)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::ManualApi,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );

            let lease = fixture
                .repository
                .acquire_reoptimize_run_lease(run_id, "owner-a", 60, now)
                .await?
                .expect("first owner acquires lease");
            assert_eq!(lease.lease_owner, "owner-a");
            assert_eq!(lease.lease_generation, 1);

            let second = fixture
                .repository
                .acquire_reoptimize_run_lease(run_id, "owner-b", 60, now)
                .await?;
            assert!(second.is_none());

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_concurrent_lease_acquire_refuses_second_owner() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("reoptimize_concurrent_lease_acquire_refuses_second_owner")
                    .await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_concurrent_lease";
            let now = test_time(1_779_000_101)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::ManualApi,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );

            let (owner_a, owner_b) = tokio::join!(
                fixture
                    .repository
                    .acquire_reoptimize_run_lease(run_id, "owner-a", 60, now),
                fixture
                    .repository
                    .acquire_reoptimize_run_lease(run_id, "owner-b", 60, now),
            );
            let acquired = [owner_a?, owner_b?]
                .into_iter()
                .filter(Option::is_some)
                .count();
            assert_eq!(acquired, 1);

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_heartbeat_requires_matching_owner_generation() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("reoptimize_heartbeat_requires_matching_owner_generation")
                    .await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_heartbeat_owner_generation";
            let now = test_time(1_779_000_201)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::Scheduled,
                        &[Timeframe::FifteenMinutes],
                        now,
                    )
                    .await?
            );
            let lease = fixture
                .repository
                .acquire_reoptimize_run_lease(run_id, "owner-a", 60, now)
                .await?
                .expect("lease acquired");

            assert!(
                !fixture
                    .repository
                    .heartbeat_reoptimize_run_lease(
                        run_id,
                        "owner-b",
                        lease.lease_generation,
                        60,
                        test_time(1_779_000_211)?,
                    )
                    .await?
            );
            assert!(
                !fixture
                    .repository
                    .heartbeat_reoptimize_run_lease(
                        run_id,
                        "owner-a",
                        lease.lease_generation + 1,
                        60,
                        test_time(1_779_000_212)?,
                    )
                    .await?
            );
            assert!(
                fixture
                    .repository
                    .heartbeat_reoptimize_run_lease(
                        run_id,
                        "owner-a",
                        lease.lease_generation,
                        60,
                        test_time(1_779_000_213)?,
                    )
                    .await?
            );

            let state = fixture
                .repository
                .fetch_reoptimize_run_state(run_id)
                .await?
                .expect("run state");
            assert_eq!(state.heartbeat_at, Some(test_time(1_779_000_213)?));

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_checkpoint_requires_matching_lease_and_persists_progress(
        ) -> anyhow::Result<()> {
            let Some(fixture) = PgFixture::connect(
                "reoptimize_checkpoint_requires_matching_lease_and_persists_progress",
            )
            .await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_checkpoint_progress";
            let now = test_time(1_779_000_251)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::Scheduled,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );
            let lease = fixture
                .repository
                .acquire_reoptimize_run_lease(run_id, "owner-a", 60, now)
                .await?
                .expect("lease acquired");
            let progress_json = serde_json::json!({
                "phase": "PAIR_EVALUATION",
                "pairs_completed": 2
            });
            let summary_json = serde_json::json!({
                "status": "RUNNING",
                "budgets": { "budget_state": "WITHIN_BUDGET" }
            });

            let wrong_owner = fixture
                .repository
                .checkpoint_reoptimize_run(AsyncReoptimizeCheckpoint {
                    run_id,
                    lease_owner: "owner-b",
                    lease_generation: lease.lease_generation,
                    lease_ttl_seconds: 60,
                    status: AsyncReoptimizeRunStatus::Running,
                    progress_json: &progress_json,
                    summary_json: &summary_json,
                    now: test_time(1_779_000_260)?,
                })
                .await?;
            assert!(wrong_owner.is_none());

            let updated = fixture
                .repository
                .checkpoint_reoptimize_run(AsyncReoptimizeCheckpoint {
                    run_id,
                    lease_owner: "owner-a",
                    lease_generation: lease.lease_generation,
                    lease_ttl_seconds: 60,
                    status: AsyncReoptimizeRunStatus::Running,
                    progress_json: &progress_json,
                    summary_json: &summary_json,
                    now: test_time(1_779_000_261)?,
                })
                .await?
                .expect("matching owner checkpoints progress");
            assert_eq!(updated.status, AsyncReoptimizeRunStatus::Running);
            let persisted_progress: serde_json::Value =
                serde_json::from_str(&updated.progress_json)?;
            let persisted_summary: serde_json::Value = serde_json::from_str(&updated.summary_json)?;
            assert_eq!(persisted_progress["pairs_completed"], 2);
            assert_eq!(
                persisted_summary["budgets"]["budget_state"],
                "WITHIN_BUDGET"
            );

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_expired_lease_moves_to_expired_fail_closed() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("reoptimize_expired_lease_moves_to_expired_fail_closed").await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_expired_lease";
            let now = test_time(1_779_000_301)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::Recovery,
                        &[Timeframe::OneHour],
                        now,
                    )
                    .await?
            );
            fixture
                .repository
                .acquire_reoptimize_run_lease(run_id, "owner-a", 5, now)
                .await?
                .expect("lease acquired");

            let expired = fixture
                .repository
                .expire_reoptimize_leases(test_time(1_779_000_307)?)
                .await?;
            assert_eq!(expired.len(), 1);
            assert_eq!(expired[0].run_id, run_id);
            assert_eq!(expired[0].status, AsyncReoptimizeRunStatus::Expired);
            assert_eq!(
                expired[0].recommendation,
                AsyncReoptimizeRecommendation::Hold.as_str()
            );
            assert!(expired[0]
                .fail_closed_reasons_json
                .contains(AsyncReoptimizeFailClosedReason::LeaseLost.as_str()));

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_cancellation_transition_cannot_become_succeeded() -> anyhow::Result<()>
        {
            let Some(fixture) =
                PgFixture::connect("reoptimize_cancellation_transition_cannot_become_succeeded")
                    .await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_cancel_not_success";
            let now = test_time(1_779_000_401)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::MaintenanceReport,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );
            let lease = fixture
                .repository
                .acquire_reoptimize_run_lease(run_id, "owner-a", 60, now)
                .await?
                .expect("lease acquired");
            let canceled = fixture
                .repository
                .request_reoptimize_run_cancel(run_id, test_time(1_779_000_410)?)
                .await?
                .expect("cancel accepted");
            assert_eq!(canceled.status, AsyncReoptimizeRunStatus::CancelRequested);

            let artifact_manifest = serde_json::json!({
                "status": "SUCCEEDED",
                "artifacts": []
            });
            let progress_json = serde_json::json!({});
            let summary_json = serde_json::json!({
                "status": "SUCCEEDED",
                "budgets": { "budget_state": "WITHIN_BUDGET" }
            });
            let finalized = fixture
                .repository
                .complete_reoptimize_run(AsyncReoptimizeCompletion {
                    run_id,
                    lease_owner: "owner-a",
                    lease_generation: lease.lease_generation,
                    requested_status: AsyncReoptimizeRunStatus::Succeeded,
                    recommendation: AsyncReoptimizeRecommendation::PromotionCandidateAvailable,
                    fail_closed_reasons: &[],
                    artifact_manifest_json: &artifact_manifest,
                    progress_json: &progress_json,
                    summary_json: &summary_json,
                    now: test_time(1_779_000_420)?,
                })
                .await?
                .expect("completion observed cancellation");
            assert_eq!(finalized.status, AsyncReoptimizeRunStatus::Canceled);
            assert_eq!(
                finalized.recommendation,
                AsyncReoptimizeRecommendation::Hold.as_str()
            );
            assert!(finalized
                .fail_closed_reasons_json
                .contains(AsyncReoptimizeFailClosedReason::Canceled.as_str()));
            let persisted_summary: serde_json::Value =
                serde_json::from_str(&finalized.summary_json)?;
            assert_eq!(persisted_summary["status"], "CANCELED");
            let persisted_manifest: serde_json::Value =
                serde_json::from_str(&finalized.artifact_manifest_json)?;
            assert_eq!(persisted_manifest["status"], "CANCELED");

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_completion_persists_generated_artifact_manifest() -> anyhow::Result<()>
        {
            let Some(fixture) =
                PgFixture::connect("reoptimize_completion_persists_generated_artifact_manifest")
                    .await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_generated_manifest";
            let now = test_time(1_779_000_451)?;
            let completed_at = test_time(1_779_000_460)?;
            let artifact_root = temp_dir("reoptimize-generated-manifest")?;
            let mut settings = StrategySettings::from_env();
            settings.reopt_artifacts_root = artifact_root.to_string_lossy().to_string();
            settings.reopt_max_artifact_bytes = 1024 * 1024;
            settings.timeframes = vec![Timeframe::OneMinute];
            settings.pairs = vec![PairSpec {
                left: "PF_XBTUSD".to_string(),
                right: "PF_ETHUSD".to_string(),
            }];

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::Scheduled,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );
            let lease = fixture
                .repository
                .acquire_reoptimize_run_lease(run_id, "owner-a", 120, now)
                .await?
                .expect("lease acquired");
            let mut progress = AsyncReoptimizeRunnerProgress::new(
                settings.timeframes.clone(),
                settings.pairs.len(),
            );
            progress.phase = AsyncReoptimizePhase::Terminal;
            progress.completed_timeframe_count = 1;
            progress.pairs_completed = 1;
            progress.last_heartbeat_at = Some(completed_at);
            let progress_json = progress.to_json();
            let errors = Vec::<ReoptError>::new();
            let summary_json = async_reoptimize_summary_json(
                run_id,
                AsyncReoptimizeRunStatus::Succeeded,
                AsyncReoptimizeTriggerSource::Scheduled,
                &settings,
                &progress_json,
                &errors,
                None,
            );
            let artifact_manifest =
                write_async_reoptimize_artifacts(AsyncReoptimizeArtifactWriteInput {
                    settings: &settings,
                    run_id,
                    status: AsyncReoptimizeRunStatus::Succeeded,
                    trigger_source: AsyncReoptimizeTriggerSource::Scheduled,
                    progress_json: &progress_json,
                    summary_json: &summary_json,
                    errors: &errors,
                    recommendation: AsyncReoptimizeRecommendation::PromotionCandidateAvailable,
                    fail_closed_reasons: &[],
                    generated_at: completed_at,
                })?;

            let finalized = fixture
                .repository
                .complete_reoptimize_run(AsyncReoptimizeCompletion {
                    run_id,
                    lease_owner: "owner-a",
                    lease_generation: lease.lease_generation,
                    requested_status: AsyncReoptimizeRunStatus::Succeeded,
                    recommendation: AsyncReoptimizeRecommendation::PromotionCandidateAvailable,
                    fail_closed_reasons: &[],
                    artifact_manifest_json: &artifact_manifest,
                    progress_json: &progress_json,
                    summary_json: &summary_json,
                    now: completed_at,
                })
                .await?
                .expect("completion persisted");
            assert_eq!(finalized.status, AsyncReoptimizeRunStatus::Succeeded);
            let persisted_manifest: serde_json::Value =
                serde_json::from_str(&finalized.artifact_manifest_json)?;
            assert!(async_reoptimize_artifact_manifest_has_contract_shape(
                &persisted_manifest
            ));
            assert_eq!(
                persisted_manifest["artifact_download_route"],
                "DEFERRED_NO_DOWNLOAD_ROUTE"
            );
            assert!(artifact_root
                .join(format!("runs/{run_id}/manifest.json"))
                .is_file());

            let response = async_reoptimize_status_response_from_state(
                &finalized,
                &settings,
                completed_at,
                &[],
            );
            assert_eq!(response.status, "SUCCEEDED");
            assert!(response.artifact_manifest.is_some());
            assert_eq!(
                response.recommendation.decision,
                AsyncReoptimizeRecommendation::PromotionCandidateAvailable.as_str()
            );

            fs::remove_dir_all(&artifact_root)?;
            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_active_run_single_flight_refuses_second_queue() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("reoptimize_active_run_single_flight_refuses_second_queue")
                    .await?
            else {
                return Ok(());
            };
            let now = test_time(1_779_000_501)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        "reopt_state_single_flight_a",
                        AsyncReoptimizeTriggerSource::Scheduled,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );
            assert!(
                !fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        "reopt_state_single_flight_b",
                        AsyncReoptimizeTriggerSource::ManualApi,
                        &[Timeframe::FifteenMinutes],
                        test_time(1_779_000_502)?,
                    )
                    .await?
            );

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_latest_and_active_state_reads_support_api_status() -> anyhow::Result<()>
        {
            let Some(fixture) =
                PgFixture::connect("reoptimize_latest_and_active_state_reads_support_api_status")
                    .await?
            else {
                return Ok(());
            };
            let first_run_id = "reopt_state_api_latest_a";
            let second_run_id = "reopt_state_api_latest_b";
            let now = test_time(1_779_000_601)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        first_run_id,
                        AsyncReoptimizeTriggerSource::ManualApi,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );
            let latest = fixture
                .repository
                .fetch_latest_reoptimize_run_state()
                .await?
                .expect("latest run state");
            assert_eq!(latest.run_id, first_run_id);
            assert_eq!(latest.requested_timeframes, "1m");

            let canceled = fixture
                .repository
                .request_reoptimize_run_cancel(first_run_id, test_time(1_779_000_602)?)
                .await?
                .expect("queued run canceled");
            assert_eq!(canceled.status, AsyncReoptimizeRunStatus::Canceled);

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        second_run_id,
                        AsyncReoptimizeTriggerSource::ManualApi,
                        &[Timeframe::OneMinute, Timeframe::FifteenMinutes],
                        test_time(1_779_000_603)?,
                    )
                    .await?
            );

            let latest = fixture
                .repository
                .fetch_latest_reoptimize_run_state()
                .await?
                .expect("latest run state after second enqueue");
            assert_eq!(latest.run_id, second_run_id);
            assert_eq!(latest.requested_timeframes, "1m,15m");

            let active = fixture
                .repository
                .fetch_active_reoptimize_run_state()
                .await?
                .expect("active run state");
            assert_eq!(active.run_id, second_run_id);
            assert_eq!(active.status, AsyncReoptimizeRunStatus::Queued);

            Ok(())
        }

        #[tokio::test]
        async fn reoptimize_worker_can_discover_api_queued_run_for_lease() -> anyhow::Result<()> {
            let Some(fixture) =
                PgFixture::connect("reoptimize_worker_can_discover_api_queued_run_for_lease")
                    .await?
            else {
                return Ok(());
            };
            let run_id = "reopt_state_api_worker_pickup";
            let now = test_time(1_779_000_701)?;

            assert!(
                fixture
                    .repository
                    .enqueue_reoptimize_run_state(
                        run_id,
                        AsyncReoptimizeTriggerSource::ManualApi,
                        &[Timeframe::OneMinute],
                        now,
                    )
                    .await?
            );

            let queued = fixture
                .repository
                .fetch_next_queued_reoptimize_run_state()
                .await?
                .expect("worker can find API-created queued run");
            assert_eq!(queued.run_id, run_id);
            assert_eq!(queued.trigger_source, "MANUAL_API");

            let lease = fixture
                .repository
                .acquire_reoptimize_run_lease(
                    &queued.run_id,
                    "strategy-service:reoptimize-worker",
                    60,
                    test_time(1_779_000_702)?,
                )
                .await?
                .expect("worker can lease queued run");
            assert_eq!(lease.run_id, run_id);

            assert!(fixture
                .repository
                .fetch_next_queued_reoptimize_run_state()
                .await?
                .is_none());

            Ok(())
        }

        fn assert_transition_counts(
            summary: &PersistSummary,
            initialize: usize,
            unchanged: usize,
            promotions: usize,
            locks: usize,
        ) {
            assert_eq!(summary.transition_counts.initialize_decisions, initialize);
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
                    selected_signal_config: selected_signal_config(selected_variant, evaluated_at),
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
                flatline_diagnostics: SignalFlatlineDiagnostics {
                    status: "HEALTHY".to_string(),
                    window_bars: 720,
                    z_stddev: 1.0,
                    z_p95_minus_p5: 2.0,
                    zero_crossings: 3,
                    entry_band_crossings: 1,
                    max_abs_z: 2.1,
                    rationale_codes: vec![],
                },
            }
        }

        fn selected_signal_config(
            variant: &str,
            updated_at: DateTime<Utc>,
        ) -> SelectedSignalConfig {
            SelectedSignalConfig {
                variant: variant.to_string(),
                entry_band: 1.8,
                exit_band: 0.6,
                stop_band: 3.2,
                lookback_bars: 520,
                hold_bars: 20,
                max_half_life_bars: 120.0,
                train_bars: 64_800,
                validation_bars: 30_240,
                source: "B6_REPOSITORY_TEST".to_string(),
                updated_at,
            }
        }

        fn test_time(seconds: i64) -> anyhow::Result<DateTime<Utc>> {
            Utc.timestamp_opt(seconds, 0)
                .single()
                .ok_or_else(|| anyhow::anyhow!("invalid test timestamp {}", seconds))
        }

        fn temp_dir(name: &str) -> anyhow::Result<PathBuf> {
            let mut path = std::env::temp_dir();
            let stamp = Utc::now().timestamp_nanos_opt().unwrap_or_default();
            let counter = SCHEMA_COUNTER.fetch_add(1, Ordering::SeqCst);
            path.push(format!("cryptopairs-strategy-{name}-{stamp}-{counter:03}"));
            fs::create_dir_all(&path)?;
            Ok(path)
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
