# Web App

Current MVP UI is a lightweight operator console for manual trading controls.

## Run
Serve `apps/web/index.html` with any static file server, for example:

```bash
cd apps/web
python3 -m http.server 5173
```

Then open `http://127.0.0.1:5173`.

## Dependencies
- `strategy-service` on `:8083` for cue context (future wiring)
- `execution-service` on `:8082` for kill switch, decision, and order intent
- `account-service` on `:8081` for reconcile status

## Scope
- Safety readiness checks (kill switch, integrity gate, reconcile gate)
- Manual `ENTRY` / `EXIT` / `EMERGENCY_STOP_CLOSE` submissions
- Immediate response rendering with explicit blocked reasons
