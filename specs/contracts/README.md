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
