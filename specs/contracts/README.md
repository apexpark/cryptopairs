# Contracts

Contracts are the canonical, machine-readable definitions of system interfaces.

- JSON Schema is recommended for events/messages.
- Each schema SHOULD include a version identifier.
- Update `specs/examples/` whenever schemas change.

Current baseline contracts:
- `specs/contracts/account_snapshot_response.schema.json`
- `specs/contracts/account_reconcile_response.schema.json`
- `specs/contracts/account_observability_summary_response.schema.json`
- `specs/contracts/hosted_secrets_rotation_policy.schema.json`
- `specs/contracts/data_query_request.schema.json`
- `specs/contracts/data_query_response.schema.json`
- `specs/contracts/data_market_metrics_response.schema.json`
- `specs/contracts/candle.schema.json`
- `specs/contracts/integrity_status.schema.json`
- `specs/contracts/integrity_history_response.schema.json`
- `specs/contracts/execution_decision_response.schema.json`
- `specs/contracts/reconcile_run_response.schema.json`
- `specs/contracts/execution_kill_switch_state.schema.json`
- `specs/contracts/execution_order_intent_request.schema.json`
- `specs/contracts/execution_order_intent_response.schema.json`
- `specs/contracts/execution_portfolio_positions_response.schema.json`
- `specs/contracts/execution_observability_summary_response.schema.json`
- `specs/contracts/execution_order_lifecycle_state_machine.schema.json`
- `specs/contracts/execution_order_state_history_response.schema.json`
- `specs/contracts/execution_dispatch_response.schema.json`
- `specs/contracts/execution_kraken_normalization_matrix.schema.json`
- `specs/contracts/execution_order_event_ingest_request.schema.json`
- `specs/contracts/execution_order_event_ingest_response.schema.json`
- `specs/contracts/strategy_pairs_cues_response.schema.json`
- `specs/contracts/strategy_pairs_backtest_response.schema.json`
- `specs/contracts/strategy_pairs_live_z_response.schema.json`
- `specs/contracts/strategy_pairs_reoptimize_response.schema.json`
- `specs/contracts/strategy_pairs_cost_gate_response.schema.json`
- `specs/contracts/strategy_pairs_portfolio_plan_response.schema.json`
- `specs/contracts/strategy_tuning_report.schema.json`
