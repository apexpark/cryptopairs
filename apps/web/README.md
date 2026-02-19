# Web App

Manual-first operator console for pairs spread trading.

## Prerequisites
- Node.js 20+
- Running backend services (`data-service`, `account-service`, `execution-service`, `strategy-service`)

## Run
```bash
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`.

## Build and Test
```bash
npm run test -- --run
npm run build
```

## Environment Variables
- `VITE_DATA_SERVICE_BASE_URL` (default `http://127.0.0.1:8080`)
- `VITE_ACCOUNT_SERVICE_BASE_URL` (default `http://127.0.0.1:8081`)
- `VITE_EXECUTION_SERVICE_BASE_URL` (default `http://127.0.0.1:8082`)
- `VITE_STRATEGY_SERVICE_BASE_URL` (default `http://127.0.0.1:8083`)

## Current Scope
- Trade page with manual spread controls:
  - Stop prerequisite (method + value)
  - Long/short spread entry
  - Add/reduce exposure
  - Close spread action
  - Execution lifecycle-aware dispatch flow:
    - intent submit
    - dispatch attempt
    - per-leg lifecycle/history status
- Data Quality page backed by live integrity history
- Analytics page:
  - Hypothetical equity curve
  - Historical z-score with entry/exit/stop markers
- Portfolio and Markets pages with live strategy context
- Fail-closed gate handling:
  - kill switch
  - integrity gate decisions
  - reconciliation status
  - dispatch fails closed by default unless execution-service is in simulate-ack mode
