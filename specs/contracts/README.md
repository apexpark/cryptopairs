# Contracts

Contracts are the canonical, machine-readable definitions of system interfaces.

- JSON Schema is recommended for events/messages.
- Each schema SHOULD include a version identifier.
- Update `specs/examples/` whenever schemas change.

Current baseline contracts:
- `specs/contracts/data_query_request.schema.json`
- `specs/contracts/data_query_response.schema.json`
- `specs/contracts/candle.schema.json`
- `specs/contracts/integrity_status.schema.json`
- `specs/contracts/integrity_history_response.schema.json`
- `specs/contracts/execution_decision_response.schema.json`
- `specs/contracts/reconcile_run_response.schema.json`
- `specs/contracts/execution_kill_switch_state.schema.json`
- `specs/contracts/execution_order_intent_request.schema.json`
- `specs/contracts/execution_order_intent_response.schema.json`
- `specs/contracts/execution_order_lifecycle_state_machine.schema.json`
- `specs/contracts/execution_order_state_history_response.schema.json`
- `specs/contracts/execution_dispatch_response.schema.json`
- `specs/contracts/execution_order_event_ingest_request.schema.json`
- `specs/contracts/execution_order_event_ingest_response.schema.json`
- `specs/contracts/strategy_pairs_cues_response.schema.json`
- `specs/contracts/strategy_pairs_backtest_response.schema.json`
- `specs/contracts/strategy_pairs_reoptimize_response.schema.json`
- `specs/contracts/strategy_pairs_cost_gate_response.schema.json`
- `specs/contracts/strategy_pairs_portfolio_plan_response.schema.json`
