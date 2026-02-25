use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use chrono::{DateTime, Utc};
use common_types::Timeframe;
use execution_service::{
    can_transition_state, evaluate_integrity_gate_from_store, evaluate_order_intent,
    evaluate_risk_caps, normalize_side, GateDecision, OrderIntentAction, OrderIntentDecision,
    OrderLifecycleState, ReconcileDecision, RiskCapsConfig, RiskCheckInput,
};
use hmac::{Hmac, Mac};
use reqwest::header::{HeaderMap, HeaderValue, CONTENT_TYPE};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256, Sha512};
use std::collections::HashMap;
use std::fs;
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::time::{sleep, Duration};
use tokio_postgres::{types::ToSql, Client, NoTls};
use tower_http::cors::{Any, CorsLayer};
use tracing::info;

#[derive(Clone)]
struct AppState {
    repository: Arc<ExecutionRepository>,
    postgres_url: Arc<String>,
    account_service_url: Arc<String>,
    http_client: reqwest::Client,
    default_min_coverage_pct: f64,
    dispatch_mode: DispatchMode,
    kraken_live: Option<Arc<KrakenLiveClient>>,
    ack_watchdog: AckWatchdogConfig,
    open_orders_poller: OpenOrdersPollerConfig,
    order_status_lookup: OrderStatusLookupConfig,
    trigger_reconcile_on_terminal: bool,
    risk_caps: RiskCapsConfig,
    risk_max_snapshot_age_seconds: i64,
    observability_thresholds: ExecutionObservabilityThresholds,
}

#[derive(Debug, Clone, Copy)]
enum DispatchMode {
    FailClosed,
    SimulateAck,
    LiveKraken,
}

impl DispatchMode {
    fn parse(value: &str) -> Self {
        match value {
            "simulate_ack" => Self::SimulateAck,
            "live_kraken" => Self::LiveKraken,
            _ => Self::FailClosed,
        }
    }
}

fn normalize_secret_value(raw: String) -> Option<String> {
    let trimmed = raw.trim().to_string();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed)
    }
}

fn resolve_secret_value(
    base_key: &str,
    direct_value: Option<String>,
    file_path: Option<String>,
) -> Result<String, String> {
    if let Some(normalized) = direct_value.and_then(normalize_secret_value) {
        return Ok(normalized);
    }
    if let Some(path) = file_path.and_then(normalize_secret_value) {
        let content = fs::read_to_string(&path)
            .map_err(|error| format!("failed to read {base_key}_FILE: {error}"))?;
        if let Some(normalized) = normalize_secret_value(content) {
            return Ok(normalized);
        }
        return Err(format!("{base_key}_FILE file is empty"));
    }
    Err(format!("missing {base_key} or {base_key}_FILE"))
}

fn read_secret_env_or_file(base_key: &str) -> Result<String, String> {
    resolve_secret_value(
        base_key,
        std::env::var(base_key).ok(),
        std::env::var(format!("{base_key}_FILE")).ok(),
    )
}

impl KrakenLiveClient {
    fn from_env() -> Result<Self, String> {
        let api_key = read_secret_env_or_file("KRAKEN_FUTURES_API_KEY")?;
        let api_secret_b64 = read_secret_env_or_file("KRAKEN_FUTURES_API_SECRET")?;
        let base_url = std::env::var("KRAKEN_FUTURES_API_BASE_URL")
            .unwrap_or_else(|_| "https://futures.kraken.com".to_string());
        let endpoint_path = std::env::var("KRAKEN_FUTURES_SENDORDER_PATH")
            .unwrap_or_else(|_| "/derivatives/api/v3/sendorder".to_string());
        let open_orders_path = std::env::var("KRAKEN_FUTURES_OPENORDERS_PATH")
            .unwrap_or_else(|_| "/derivatives/api/v3/openorders".to_string());
        let order_status_path = std::env::var("KRAKEN_FUTURES_ORDER_STATUS_PATH")
            .unwrap_or_else(|_| "/derivatives/api/v3/orders/status".to_string());
        if !endpoint_path.starts_with('/') {
            return Err("KRAKEN_FUTURES_SENDORDER_PATH must start with '/'".to_string());
        }
        if !open_orders_path.starts_with('/') {
            return Err("KRAKEN_FUTURES_OPENORDERS_PATH must start with '/'".to_string());
        }
        if !order_status_path.starts_with('/') {
            return Err("KRAKEN_FUTURES_ORDER_STATUS_PATH must start with '/'".to_string());
        }
        Ok(Self {
            http_client: reqwest::Client::new(),
            base_url,
            endpoint_path,
            open_orders_path,
            order_status_path,
            api_key,
            api_secret_b64,
        })
    }

    async fn submit_order(
        &self,
        intent: &OrderIntentRecord,
    ) -> Result<LiveDispatchSuccess, String> {
        if intent.exchange != "kraken_futures" {
            return Err(format!(
                "live_kraken mode only supports exchange=kraken_futures, got {}",
                intent.exchange
            ));
        }

        let side = if intent.side == "BUY" { "buy" } else { "sell" };
        let nonce = Utc::now().timestamp_millis().to_string();
        let post_data = format!(
            "orderType=mkt&symbol={}&side={}&size={}&cliOrdId={}",
            urlencoding::encode(&intent.instrument),
            side,
            intent.qty,
            urlencoding::encode(&intent.idempotency_key)
        );
        let authent = sign_kraken_futures_payload(
            &post_data,
            &nonce,
            &self.endpoint_path,
            &self.api_secret_b64,
        )?;
        let url = format!("{}{}", self.base_url, self.endpoint_path);

        let mut headers = HeaderMap::new();
        headers.insert(
            CONTENT_TYPE,
            HeaderValue::from_static("application/x-www-form-urlencoded"),
        );
        headers.insert(
            "APIKey",
            HeaderValue::from_str(&self.api_key)
                .map_err(|_| "invalid API key header".to_string())?,
        );
        headers.insert(
            "Nonce",
            HeaderValue::from_str(&nonce).map_err(|_| "invalid nonce header".to_string())?,
        );
        headers.insert(
            "Authent",
            HeaderValue::from_str(&authent).map_err(|_| "invalid authent header".to_string())?,
        );

        let response = self
            .http_client
            .post(url)
            .headers(headers)
            .body(post_data)
            .send()
            .await
            .map_err(|error| format!("kraken live submit request failed: {error}"))?;

        let status = response.status().as_u16();
        let body = response
            .text()
            .await
            .map_err(|error| format!("kraken live submit response read failed: {error}"))?;

        if status != 200 {
            return Err(format!(
                "kraken live submit http status {status}: {}",
                summarize_response(&body)
            ));
        }

        parse_kraken_submit_response(&body)
    }

    async fn fetch_open_orders(&self) -> Result<HashMap<String, KrakenOpenOrder>, String> {
        let nonce = Utc::now().timestamp_millis().to_string();
        let post_data = String::new();
        let authent = sign_kraken_futures_payload(
            &post_data,
            &nonce,
            &self.open_orders_path,
            &self.api_secret_b64,
        )?;
        let url = format!("{}{}", self.base_url, self.open_orders_path);

        let mut headers = HeaderMap::new();
        headers.insert(
            CONTENT_TYPE,
            HeaderValue::from_static("application/x-www-form-urlencoded"),
        );
        headers.insert(
            "APIKey",
            HeaderValue::from_str(&self.api_key)
                .map_err(|_| "invalid API key header".to_string())?,
        );
        headers.insert(
            "Nonce",
            HeaderValue::from_str(&nonce).map_err(|_| "invalid nonce header".to_string())?,
        );
        headers.insert(
            "Authent",
            HeaderValue::from_str(&authent).map_err(|_| "invalid authent header".to_string())?,
        );

        let response = self
            .http_client
            .get(url)
            .headers(headers)
            .send()
            .await
            .map_err(|error| format!("kraken openorders request failed: {error}"))?;
        let status = response.status().as_u16();
        let body = response
            .text()
            .await
            .map_err(|error| format!("kraken openorders response read failed: {error}"))?;
        if status != 200 {
            return Err(format!(
                "kraken openorders http status {status}: {}",
                summarize_response(&body)
            ));
        }
        parse_kraken_open_orders_response(&body)
    }

    async fn fetch_order_status_by_query(
        &self,
        order_id: &str,
        query_key: &str,
    ) -> Result<Option<KrakenStatusOrder>, String> {
        let nonce = Utc::now().timestamp_millis().to_string();
        let post_data = String::new();
        let uri_component = build_uri_component(&self.order_status_path, &[(query_key, order_id)]);
        let authent =
            sign_kraken_futures_payload(&post_data, &nonce, &uri_component, &self.api_secret_b64)?;
        let url = format!("{}{}", self.base_url, uri_component);

        let mut headers = HeaderMap::new();
        headers.insert(
            CONTENT_TYPE,
            HeaderValue::from_static("application/x-www-form-urlencoded"),
        );
        headers.insert(
            "APIKey",
            HeaderValue::from_str(&self.api_key)
                .map_err(|_| "invalid API key header".to_string())?,
        );
        headers.insert(
            "Nonce",
            HeaderValue::from_str(&nonce).map_err(|_| "invalid nonce header".to_string())?,
        );
        headers.insert(
            "Authent",
            HeaderValue::from_str(&authent).map_err(|_| "invalid authent header".to_string())?,
        );

        let response = self
            .http_client
            .get(url)
            .headers(headers)
            .send()
            .await
            .map_err(|error| format!("kraken order status request failed: {error}"))?;
        let status = response.status().as_u16();
        let body = response
            .text()
            .await
            .map_err(|error| format!("kraken order status response read failed: {error}"))?;
        if status != 200 {
            return Err(format!(
                "kraken order status http status {status}: {}",
                summarize_response(&body)
            ));
        }
        let parsed = parse_kraken_order_status_response(&body)?;
        Ok(parsed.into_iter().find(|order| order.order_id == order_id))
    }
}

fn build_uri_component(endpoint_path: &str, query_pairs: &[(&str, &str)]) -> String {
    if query_pairs.is_empty() {
        return endpoint_path.to_string();
    }

    let query = query_pairs
        .iter()
        .map(|(key, value)| {
            format!(
                "{}={}",
                urlencoding::encode(key),
                urlencoding::encode(value)
            )
        })
        .collect::<Vec<_>>()
        .join("&");
    format!("{endpoint_path}?{query}")
}

fn sign_kraken_futures_payload(
    post_data: &str,
    nonce: &str,
    uri_component: &str,
    api_secret_b64: &str,
) -> Result<String, String> {
    let sha_input = format!("{post_data}{nonce}{uri_component}");
    let sha_digest = Sha256::digest(sha_input.as_bytes());
    let encoded_post_data = urlencoding::encode(post_data).into_owned();

    let mut signing_input = Vec::with_capacity(encoded_post_data.len() + sha_digest.len());
    signing_input.extend_from_slice(encoded_post_data.as_bytes());
    signing_input.extend_from_slice(&sha_digest);

    let secret = BASE64_STANDARD
        .decode(api_secret_b64)
        .map_err(|_| "KRAKEN_FUTURES_API_SECRET is not valid base64".to_string())?;
    let mut mac =
        Hmac::<Sha512>::new_from_slice(&secret).map_err(|_| "invalid hmac secret".to_string())?;
    mac.update(&signing_input);
    let signature = mac.finalize().into_bytes();
    Ok(BASE64_STANDARD.encode(signature))
}

fn parse_kraken_submit_response(body: &str) -> Result<LiveDispatchSuccess, String> {
    let payload: serde_json::Value = serde_json::from_str(body)
        .map_err(|error| format!("kraken response decode failed: {error}"))?;

    let mut status_text = None;
    if let Some(status) = payload
        .get("sendStatus")
        .and_then(|value| value.get("status"))
        .and_then(serde_json::Value::as_str)
    {
        status_text = Some(status.to_string());
    }

    let order_id = extract_order_id(&payload);
    let is_success = matches!(
        status_text.as_deref(),
        Some("placed") | Some("attempted") | Some("received")
    );
    if !is_success {
        let reason = payload
            .get("error")
            .and_then(serde_json::Value::as_str)
            .map(ToString::to_string)
            .or_else(|| status_text.clone())
            .unwrap_or_else(|| {
                format!(
                    "unexpected kraken sendorder payload: {}",
                    summarize_response(body)
                )
            });
        return Err(reason);
    }
    let Some(exchange_order_id) = order_id else {
        return Err("kraken sendorder response missing order id".to_string());
    };
    Ok(LiveDispatchSuccess {
        exchange_order_id,
        reason: "dispatch acknowledged by kraken live adapter".to_string(),
    })
}

fn parse_kraken_open_orders_response(
    body: &str,
) -> Result<HashMap<String, KrakenOpenOrder>, String> {
    let payload: KrakenOpenOrdersResponse = serde_json::from_str(body)
        .map_err(|error| format!("kraken openorders decode failed: {error}"))?;
    if payload.result != "success" {
        return Err(format!(
            "kraken openorders returned non-success result={}",
            payload.result
        ));
    }
    let mut by_id = HashMap::new();
    for order in payload.open_orders {
        if order.order_id.trim().is_empty() {
            continue;
        }
        by_id.insert(order.order_id.clone(), order);
    }
    Ok(by_id)
}

fn parse_kraken_order_status_response(body: &str) -> Result<Vec<KrakenStatusOrder>, String> {
    let payload: KrakenOrderStatusResponse = serde_json::from_str(body)
        .map_err(|error| format!("kraken order status decode failed: {error}"))?;
    if payload.result != "success" {
        return Err(format!(
            "kraken order status returned non-success result={}",
            payload.result
        ));
    }
    Ok(payload
        .orders
        .into_iter()
        .filter(|order| !order.order_id.trim().is_empty())
        .collect())
}

fn extract_order_id(payload: &serde_json::Value) -> Option<String> {
    if let Some(id) = payload
        .get("sendStatus")
        .and_then(|value| value.get("order_id"))
        .and_then(serde_json::Value::as_str)
    {
        return Some(id.to_string());
    }
    if let Some(id) = payload
        .get("sendStatus")
        .and_then(|value| value.get("orderId"))
        .and_then(serde_json::Value::as_str)
    {
        return Some(id.to_string());
    }
    payload
        .get("sendStatus")
        .and_then(|value| value.get("orderEvents"))
        .and_then(serde_json::Value::as_array)
        .and_then(|events| {
            events.iter().find_map(|event| {
                event
                    .get("order")
                    .and_then(|order| order.get("orderId"))
                    .and_then(serde_json::Value::as_str)
                    .map(ToString::to_string)
            })
        })
}

fn summarize_response(body: &str) -> String {
    const MAX_LEN: usize = 220;
    if body.len() <= MAX_LEN {
        body.to_string()
    } else {
        format!("{}...", &body[..MAX_LEN])
    }
}

#[derive(Clone)]
struct KrakenLiveClient {
    http_client: reqwest::Client,
    base_url: String,
    endpoint_path: String,
    open_orders_path: String,
    order_status_path: String,
    api_key: String,
    api_secret_b64: String,
}

#[derive(Debug)]
struct LiveDispatchSuccess {
    exchange_order_id: String,
    reason: String,
}

#[derive(Debug, Clone, Copy)]
struct AckWatchdogConfig {
    poll_interval_seconds: u64,
    expire_after_seconds: u64,
    batch_limit: i64,
}

#[derive(Debug, Clone, Copy)]
struct OpenOrdersPollerConfig {
    enabled: bool,
    poll_interval_seconds: u64,
    batch_limit: i64,
}

#[derive(Debug, Clone)]
struct OrderStatusLookupConfig {
    enabled: bool,
    query_key: String,
}

#[derive(Debug, Clone, Copy)]
struct ExecutionObservabilityThresholds {
    risk_block_ratio_p2: f64,
    dispatch_reject_ratio_p2: f64,
    stale_ack_count_p1: i64,
    reconcile_block_count_p1: i64,
}

#[derive(Debug, Clone)]
struct LiveTrackedOrder {
    idempotency_key: String,
    exchange_order_id: String,
    current_state: OrderLifecycleState,
}

#[derive(Debug, Clone, Copy)]
struct AccountSnapshotRow {
    ts: DateTime<Utc>,
    equity: f64,
    margin_used: f64,
}

#[derive(Debug, Deserialize)]
struct AccountServiceSnapshotResponse {
    snapshot: Option<AccountSnapshotPayload>,
}

#[derive(Debug, Deserialize)]
struct AccountSnapshotPayload {
    #[allow(dead_code)]
    exchange: String,
    #[allow(dead_code)]
    account_id: String,
    ts: DateTime<Utc>,
    equity: f64,
    #[allow(dead_code)]
    balance: f64,
    margin_used: f64,
    #[allow(dead_code)]
    unrealized_pnl: f64,
    #[allow(dead_code)]
    realized_pnl: f64,
}

#[derive(Debug, Deserialize)]
struct AccountServiceReconcileResponse {
    reconcile: Option<AccountReconcilePayload>,
}

#[derive(Debug, Deserialize)]
struct AccountReconcilePayload {
    #[allow(dead_code)]
    exchange: String,
    #[allow(dead_code)]
    account_id: String,
    #[allow(dead_code)]
    ts: DateTime<Utc>,
    status: String,
    drift_notional: f64,
    notes: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct KrakenOpenOrdersResponse {
    result: String,
    #[serde(default)]
    open_orders: Vec<KrakenOpenOrder>,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct KrakenOpenOrder {
    #[serde(alias = "order_id")]
    order_id: String,
    status: Option<String>,
    filled_size: Option<f64>,
    unfilled_size: Option<f64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct KrakenOrderStatusResponse {
    result: String,
    #[serde(default)]
    orders: Vec<KrakenStatusOrder>,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct KrakenStatusOrder {
    #[serde(alias = "order_id")]
    order_id: String,
    status: String,
    filled: Option<f64>,
    quantity: Option<f64>,
}

#[derive(Clone)]
struct ExecutionRepository {
    client: Arc<Client>,
}

impl ExecutionRepository {
    async fn connect(connection_string: &str) -> anyhow::Result<Self> {
        let (client, connection) = tokio_postgres::connect(connection_string, NoTls).await?;
        tokio::spawn(async move {
            if let Err(error) = connection.await {
                tracing::error!(error = %error, "execution-service postgres connection ended");
            }
        });

        let repository = Self {
            client: Arc::new(client),
        };
        repository.ensure_schema().await?;
        Ok(repository)
    }

    async fn ensure_schema(&self) -> anyhow::Result<()> {
        self.client
            .batch_execute(
                "CREATE TABLE IF NOT EXISTS execution_control (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    kill_switch_active BOOLEAN NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CHECK (id = 1)
                 );
                 CREATE TABLE IF NOT EXISTS execution_control_events (
                    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    kill_switch_active BOOLEAN NOT NULL,
                    reason TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT 'system'
                 );
                 CREATE TABLE IF NOT EXISTS execution_order_intents (
                    idempotency_key TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL DEFAULT 'kraken_futures',
                    account_id TEXT NOT NULL DEFAULT 'default',
                    pair_id TEXT,
                    instrument TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    action TEXT NOT NULL,
                    spread_direction TEXT,
                    spread_z DOUBLE PRECISION,
                    side TEXT NOT NULL,
                    qty DOUBLE PRECISION NOT NULL,
                    operator_confirmed BOOLEAN NOT NULL,
                    operator_id TEXT,
                    min_coverage_pct DOUBLE PRECISION NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                 );
                 CREATE TABLE IF NOT EXISTS execution_order_state_events (
                    idempotency_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT 'system',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (idempotency_key, state, created_at)
                 );
                 CREATE TABLE IF NOT EXISTS execution_dispatch_attempts (
                    idempotency_key TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    result_state TEXT NOT NULL,
                    exchange_order_id TEXT,
                    reason TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT 'execution-service',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (idempotency_key, attempt_no)
                 );
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS exchange TEXT NOT NULL DEFAULT 'kraken_futures';
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS account_id TEXT NOT NULL DEFAULT 'default';
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS action TEXT NOT NULL DEFAULT 'ENTRY';
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS operator_confirmed BOOLEAN NOT NULL DEFAULT FALSE;
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS operator_id TEXT;
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS pair_id TEXT;
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS spread_direction TEXT;
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS spread_z DOUBLE PRECISION;",
            )
            .await?;
        Ok(())
    }

    async fn get_kill_switch_state(&self) -> anyhow::Result<KillSwitchState> {
        let row = self
            .client
            .query_opt(
                "SELECT kill_switch_active, reason, updated_at
                 FROM execution_control
                 WHERE id = 1",
                &[],
            )
            .await?;

        if let Some(row) = row {
            Ok(KillSwitchState {
                active: row.get(0),
                reason: row.get(1),
                updated_at: row.get(2),
            })
        } else {
            Ok(KillSwitchState {
                active: true,
                reason: "unknown kill switch state; defaulting to blocked".to_string(),
                updated_at: Utc::now(),
            })
        }
    }

    async fn set_kill_switch_state(
        &self,
        active: bool,
        reason: &str,
        actor: &str,
    ) -> anyhow::Result<KillSwitchState> {
        let now = Utc::now();
        self.client
            .execute(
                "INSERT INTO execution_control (id, kill_switch_active, reason, updated_at)
                 VALUES (1, $1, $2, $3)
                 ON CONFLICT (id) DO UPDATE SET
                   kill_switch_active = EXCLUDED.kill_switch_active,
                   reason = EXCLUDED.reason,
                   updated_at = EXCLUDED.updated_at",
                &[&active, &reason, &now],
            )
            .await?;

        self.client
            .execute(
                "INSERT INTO execution_control_events (ts, kill_switch_active, reason, actor)
                 VALUES ($1, $2, $3, $4)",
                &[&now as &(dyn ToSql + Sync), &active, &reason, &actor],
            )
            .await?;

        Ok(KillSwitchState {
            active,
            reason: reason.to_string(),
            updated_at: now,
        })
    }

    async fn fetch_order_intent(
        &self,
        idempotency_key: &str,
    ) -> anyhow::Result<Option<OrderIntentRecord>> {
        let row = self
            .client
            .query_opt(
                "SELECT idempotency_key, instrument, timeframe, action, side, qty,
                        operator_confirmed, operator_id, min_coverage_pct, exchange, account_id,
                        pair_id, spread_direction, spread_z, decision, reason, created_at
                 FROM execution_order_intents
                 WHERE idempotency_key = $1",
                &[&idempotency_key],
            )
            .await?;

        Ok(row.map(|row| OrderIntentRecord {
            idempotency_key: row.get(0),
            instrument: row.get(1),
            timeframe: row.get(2),
            action: row.get(3),
            side: row.get(4),
            qty: row.get(5),
            operator_confirmed: row.get(6),
            operator_id: row.get(7),
            min_coverage_pct: row.get(8),
            exchange: row.get(9),
            account_id: row.get(10),
            pair_id: row.get(11),
            spread_direction: row.get(12),
            spread_z: row.get(13),
            decision: row.get(14),
            reason: row.get(15),
            created_at: row.get(16),
        }))
    }

    async fn fetch_order_intent_by_exchange_order_id(
        &self,
        exchange_order_id: &str,
    ) -> anyhow::Result<Option<OrderIntentRecord>> {
        let row = self
            .client
            .query_opt(
                "SELECT i.idempotency_key, i.instrument, i.timeframe, i.action, i.side, i.qty,
                        i.operator_confirmed, i.operator_id, i.min_coverage_pct, i.exchange, i.account_id,
                        i.pair_id, i.spread_direction, i.spread_z, i.decision, i.reason, i.created_at
                 FROM execution_order_intents i
                 JOIN execution_dispatch_attempts d
                   ON d.idempotency_key = i.idempotency_key
                WHERE d.exchange_order_id = $1
                 ORDER BY d.created_at DESC
                 LIMIT 1",
                &[&exchange_order_id],
            )
            .await?;

        Ok(row.map(|row| OrderIntentRecord {
            idempotency_key: row.get(0),
            instrument: row.get(1),
            timeframe: row.get(2),
            action: row.get(3),
            side: row.get(4),
            qty: row.get(5),
            operator_confirmed: row.get(6),
            operator_id: row.get(7),
            min_coverage_pct: row.get(8),
            exchange: row.get(9),
            account_id: row.get(10),
            pair_id: row.get(11),
            spread_direction: row.get(12),
            spread_z: row.get(13),
            decision: row.get(14),
            reason: row.get(15),
            created_at: row.get(16),
        }))
    }

    async fn insert_order_intent(&self, record: &OrderIntentRecord) -> anyhow::Result<()> {
        self.client
            .execute(
                "INSERT INTO execution_order_intents
                 (idempotency_key, instrument, timeframe, action, side, qty,
                  operator_confirmed, operator_id, min_coverage_pct, exchange, account_id,
                  pair_id, spread_direction, spread_z, decision, reason, created_at)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                 ON CONFLICT (idempotency_key) DO NOTHING",
                &[
                    &record.idempotency_key as &(dyn ToSql + Sync),
                    &record.instrument,
                    &record.timeframe,
                    &record.action,
                    &record.side,
                    &record.qty,
                    &record.operator_confirmed,
                    &record.operator_id,
                    &record.min_coverage_pct,
                    &record.exchange,
                    &record.account_id,
                    &record.pair_id,
                    &record.spread_direction,
                    &record.spread_z,
                    &record.decision,
                    &record.reason,
                    &record.created_at,
                ],
            )
            .await?;
        self.record_state_event(
            &record.idempotency_key,
            OrderLifecycleState::New,
            "intent persisted",
            "execution-service",
        )
        .await?;

        let follow_up_state = if record.decision == "ACCEPTED" {
            OrderLifecycleState::Approved
        } else {
            OrderLifecycleState::Rejected
        };
        self.record_state_event(
            &record.idempotency_key,
            follow_up_state,
            &record.reason,
            "execution-service",
        )
        .await?;
        Ok(())
    }

    async fn fetch_active_pair_qty(
        &self,
        exchange: &str,
        account_id: &str,
        instrument: &str,
    ) -> anyhow::Result<f64> {
        let row = self
            .client
            .query_one(
                "SELECT COALESCE(SUM(
                    CASE
                      WHEN i.action = 'ENTRY' THEN i.qty
                      WHEN i.action IN ('EXIT', 'EMERGENCY_STOP_CLOSE') THEN -i.qty
                      ELSE 0
                    END
                 ), 0.0) AS active_qty
                 FROM execution_order_intents i
                 JOIN (
                    SELECT DISTINCT ON (idempotency_key)
                      idempotency_key, state, created_at
                    FROM execution_order_state_events
                    ORDER BY idempotency_key, created_at DESC
                 ) latest
                    ON latest.idempotency_key = i.idempotency_key
                 WHERE i.exchange = $1
                   AND i.account_id = $2
                   AND i.instrument = $3
                   AND i.decision = 'ACCEPTED'
                   AND latest.state IN ('APPROVED', 'PENDING_SUBMIT', 'ACKNOWLEDGED', 'PARTIALLY_FILLED', 'FILLED')",
                &[&exchange, &account_id, &instrument],
            )
            .await?;
        let active_qty: f64 = row.get(0);
        Ok(active_qty.max(0.0))
    }

    async fn fetch_active_gross_qty(
        &self,
        exchange: &str,
        account_id: &str,
    ) -> anyhow::Result<f64> {
        let row = self
            .client
            .query_one(
                "SELECT COALESCE(SUM(ABS(net_qty)), 0.0) AS gross_qty
                 FROM (
                    SELECT i.instrument,
                           SUM(
                             CASE
                               WHEN i.action = 'ENTRY' THEN i.qty
                               WHEN i.action IN ('EXIT', 'EMERGENCY_STOP_CLOSE') THEN -i.qty
                               ELSE 0
                             END
                           ) AS net_qty
                    FROM execution_order_intents i
                    JOIN (
                        SELECT DISTINCT ON (idempotency_key)
                          idempotency_key, state, created_at
                        FROM execution_order_state_events
                        ORDER BY idempotency_key, created_at DESC
                    ) latest
                      ON latest.idempotency_key = i.idempotency_key
                    WHERE i.exchange = $1
                      AND i.account_id = $2
                      AND i.decision = 'ACCEPTED'
                      AND latest.state IN ('APPROVED', 'PENDING_SUBMIT', 'ACKNOWLEDGED', 'PARTIALLY_FILLED', 'FILLED')
                    GROUP BY i.instrument
                 ) exposures",
                &[&exchange, &account_id],
            )
            .await?;
        let gross_qty: f64 = row.get(0);
        Ok(gross_qty.max(0.0))
    }

    async fn fetch_last_accepted_entry_ts(
        &self,
        exchange: &str,
        account_id: &str,
        instrument: &str,
    ) -> anyhow::Result<Option<DateTime<Utc>>> {
        let row = self
            .client
            .query_opt(
                "SELECT created_at
                 FROM execution_order_intents
                 WHERE exchange=$1
                   AND account_id=$2
                   AND instrument=$3
                   AND action='ENTRY'
                   AND decision='ACCEPTED'
                 ORDER BY created_at DESC
                 LIMIT 1",
                &[&exchange, &account_id, &instrument],
            )
            .await?;
        Ok(row.map(|row| row.get(0)))
    }

    async fn fetch_spread_ledger_events(
        &self,
        exchange: &str,
        account_id: &str,
    ) -> anyhow::Result<Vec<SpreadLedgerEvent>> {
        let rows = self
            .client
            .query(
                "SELECT i.pair_id, i.action, i.spread_direction, i.spread_z, i.qty, i.created_at
                 FROM execution_order_intents i
                 JOIN (
                    SELECT DISTINCT ON (idempotency_key)
                      idempotency_key, state, created_at
                    FROM execution_order_state_events
                    ORDER BY idempotency_key, created_at DESC
                 ) latest
                   ON latest.idempotency_key = i.idempotency_key
                 WHERE i.exchange = $1
                   AND i.account_id = $2
                   AND i.decision = 'ACCEPTED'
                   AND i.pair_id IS NOT NULL
                   AND i.pair_id <> ''
                   AND latest.state IN ('ACKNOWLEDGED', 'PARTIALLY_FILLED', 'FILLED')
                 ORDER BY i.created_at ASC",
                &[&exchange, &account_id],
            )
            .await?;
        Ok(rows
            .iter()
            .map(|row| SpreadLedgerEvent {
                pair_id: row.get(0),
                action: row.get(1),
                spread_direction: row.get(2),
                spread_z: row.get(3),
                qty: row.get(4),
                created_at: row.get(5),
            })
            .collect())
    }

    async fn record_state_event(
        &self,
        idempotency_key: &str,
        state: OrderLifecycleState,
        reason: &str,
        actor: &str,
    ) -> anyhow::Result<()> {
        self.client
            .execute(
                "INSERT INTO execution_order_state_events
                 (idempotency_key, state, reason, actor, created_at)
                 VALUES ($1,$2,$3,$4,NOW())",
                &[&idempotency_key, &state.as_str(), &reason, &actor],
            )
            .await?;
        Ok(())
    }

    async fn fetch_order_state_history(
        &self,
        idempotency_key: &str,
    ) -> anyhow::Result<Vec<OrderStateEvent>> {
        let rows = self
            .client
            .query(
                "SELECT state, reason, actor, created_at
                 FROM execution_order_state_events
                 WHERE idempotency_key = $1
                 ORDER BY created_at ASC",
                &[&idempotency_key],
            )
            .await?;
        Ok(rows
            .iter()
            .map(|row| OrderStateEvent {
                state: row.get(0),
                reason: row.get(1),
                actor: row.get(2),
                created_at: row.get(3),
            })
            .collect())
    }

    async fn fetch_latest_order_state(
        &self,
        idempotency_key: &str,
    ) -> anyhow::Result<Option<OrderLifecycleState>> {
        let row = self
            .client
            .query_opt(
                "SELECT state
                 FROM execution_order_state_events
                 WHERE idempotency_key = $1
                 ORDER BY created_at DESC
                 LIMIT 1",
                &[&idempotency_key],
            )
            .await?;
        let Some(row) = row else {
            return Ok(None);
        };
        let state_raw: String = row.get(0);
        Ok(OrderLifecycleState::parse(&state_raw))
    }

    async fn insert_dispatch_attempt(
        &self,
        idempotency_key: &str,
        result_state: OrderLifecycleState,
        exchange_order_id: Option<&str>,
        reason: &str,
        actor: &str,
    ) -> anyhow::Result<DispatchAttempt> {
        let next_attempt_row = self
            .client
            .query_one(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1
                 FROM execution_dispatch_attempts
                 WHERE idempotency_key = $1",
                &[&idempotency_key],
            )
            .await?;
        let attempt_no: i32 = next_attempt_row.get(0);
        let created_at = Utc::now();
        self.client
            .execute(
                "INSERT INTO execution_dispatch_attempts
                 (idempotency_key, attempt_no, result_state, exchange_order_id, reason, actor, created_at)
                 VALUES ($1,$2,$3,$4,$5,$6,$7)",
                &[
                    &idempotency_key,
                    &attempt_no,
                    &result_state.as_str(),
                    &exchange_order_id,
                    &reason,
                    &actor,
                    &created_at as &(dyn ToSql + Sync),
                ],
            )
            .await?;
        Ok(DispatchAttempt {
            attempt_no,
            result_state: result_state.as_str().to_string(),
            exchange_order_id: exchange_order_id.map(ToString::to_string),
            reason: reason.to_string(),
            actor: actor.to_string(),
            created_at,
        })
    }

    async fn fetch_dispatch_attempts(
        &self,
        idempotency_key: &str,
    ) -> anyhow::Result<Vec<DispatchAttempt>> {
        let rows = self
            .client
            .query(
                "SELECT attempt_no, result_state, exchange_order_id, reason, actor, created_at
                 FROM execution_dispatch_attempts
                 WHERE idempotency_key = $1
                 ORDER BY attempt_no ASC",
                &[&idempotency_key],
            )
            .await?;
        Ok(rows
            .iter()
            .map(|row| DispatchAttempt {
                attempt_no: row.get(0),
                result_state: row.get(1),
                exchange_order_id: row.get(2),
                reason: row.get(3),
                actor: row.get(4),
                created_at: row.get(5),
            })
            .collect())
    }

    async fn fetch_latest_exchange_order_id(
        &self,
        idempotency_key: &str,
    ) -> anyhow::Result<Option<String>> {
        let row = self
            .client
            .query_opt(
                "SELECT exchange_order_id
                 FROM execution_dispatch_attempts
                 WHERE idempotency_key = $1
                   AND exchange_order_id IS NOT NULL
                 ORDER BY attempt_no DESC
                 LIMIT 1",
                &[&idempotency_key],
            )
            .await?;
        Ok(row.map(|row| row.get(0)))
    }

    async fn fetch_stale_acknowledged_orders(
        &self,
        expire_after_seconds: i64,
        limit: i64,
    ) -> anyhow::Result<Vec<String>> {
        let rows = self
            .client
            .query(
                "SELECT latest.idempotency_key
                 FROM (
                   SELECT DISTINCT ON (idempotency_key)
                     idempotency_key, state, created_at
                   FROM execution_order_state_events
                   ORDER BY idempotency_key, created_at DESC
                 ) latest
                 WHERE latest.state = 'ACKNOWLEDGED'
                   AND latest.created_at <= NOW() - ($1::BIGINT * INTERVAL '1 second')
                 ORDER BY latest.created_at ASC
                 LIMIT $2",
                &[&expire_after_seconds, &limit],
            )
            .await?;

        Ok(rows.iter().map(|row| row.get(0)).collect())
    }

    async fn fetch_live_tracked_orders(&self, limit: i64) -> anyhow::Result<Vec<LiveTrackedOrder>> {
        let rows = self
            .client
            .query(
                "SELECT i.idempotency_key, latest.state, d.exchange_order_id
                 FROM execution_order_intents i
                 JOIN (
                   SELECT DISTINCT ON (idempotency_key)
                     idempotency_key, state, created_at
                   FROM execution_order_state_events
                   ORDER BY idempotency_key, created_at DESC
                 ) latest
                   ON latest.idempotency_key = i.idempotency_key
                 JOIN (
                   SELECT DISTINCT ON (idempotency_key)
                     idempotency_key, exchange_order_id, attempt_no
                   FROM execution_dispatch_attempts
                   WHERE exchange_order_id IS NOT NULL
                   ORDER BY idempotency_key, attempt_no DESC
                 ) d
                   ON d.idempotency_key = i.idempotency_key
                 WHERE i.exchange = 'kraken_futures'
                   AND latest.state IN ('ACKNOWLEDGED', 'PARTIALLY_FILLED')
                 ORDER BY i.created_at ASC
                 LIMIT $1",
                &[&limit],
            )
            .await?;

        Ok(rows
            .iter()
            .filter_map(|row| {
                let idempotency_key: String = row.get(0);
                let state_raw: String = row.get(1);
                let exchange_order_id: String = row.get(2);
                let current_state = OrderLifecycleState::parse(&state_raw)?;
                Some(LiveTrackedOrder {
                    idempotency_key,
                    exchange_order_id,
                    current_state,
                })
            })
            .collect())
    }

    async fn fetch_observability_metrics(
        &self,
        exchange: &str,
        account_id: &str,
        window_minutes: i64,
        stale_ack_seconds: i64,
    ) -> anyhow::Result<ExecutionObservabilityMetricsRaw> {
        let bounded_window = window_minutes.max(1);
        let intents_row = self
            .client
            .query_one(
                "SELECT
                    COUNT(*) AS intents_total,
                    COUNT(*) FILTER (WHERE decision='BLOCKED') AS intents_blocked,
                    COUNT(*) FILTER (WHERE decision='BLOCKED' AND reason LIKE 'risk gate blocked signal:%') AS risk_blocked,
                    COUNT(*) FILTER (WHERE decision='BLOCKED' AND reason LIKE 'integrity gate blocked signal:%') AS integrity_blocked,
                    COUNT(*) FILTER (WHERE decision='BLOCKED' AND reason LIKE 'reconcile gate blocked signal:%') AS reconcile_blocked,
                    COUNT(*) FILTER (WHERE decision='BLOCKED' AND reason = 'kill switch is active; order intent blocked') AS kill_switch_blocked
                 FROM execution_order_intents
                 WHERE exchange=$1
                   AND account_id=$2
                   AND created_at >= NOW() - ($3::BIGINT * INTERVAL '1 minute')",
                &[&exchange, &account_id, &bounded_window],
            )
            .await?;
        let dispatch_row = self
            .client
            .query_one(
                "SELECT
                    COUNT(*) AS dispatch_total,
                    COUNT(*) FILTER (WHERE result_state='REJECTED') AS dispatch_rejected,
                    COUNT(*) FILTER (WHERE result_state='ACKNOWLEDGED') AS dispatch_acknowledged
                 FROM execution_dispatch_attempts
                 WHERE created_at >= NOW() - ($1::BIGINT * INTERVAL '1 minute')",
                &[&bounded_window],
            )
            .await?;
        let stale_ack_row = self
            .client
            .query_one(
                "SELECT COUNT(*) AS stale_ack_count
                 FROM (
                    SELECT DISTINCT ON (idempotency_key)
                      idempotency_key, state, created_at
                    FROM execution_order_state_events
                    ORDER BY idempotency_key, created_at DESC
                 ) latest
                 JOIN execution_order_intents i
                   ON i.idempotency_key = latest.idempotency_key
                 WHERE i.exchange=$1
                   AND i.account_id=$2
                   AND latest.state='ACKNOWLEDGED'
                   AND latest.created_at <= NOW() - ($3::BIGINT * INTERVAL '1 second')",
                &[&exchange, &account_id, &stale_ack_seconds.max(1)],
            )
            .await?;

        Ok(ExecutionObservabilityMetricsRaw {
            intents_total: intents_row.get(0),
            intents_blocked: intents_row.get(1),
            risk_blocked: intents_row.get(2),
            integrity_blocked: intents_row.get(3),
            reconcile_blocked: intents_row.get(4),
            kill_switch_blocked: intents_row.get(5),
            dispatch_total: dispatch_row.get(0),
            dispatch_rejected: dispatch_row.get(1),
            dispatch_acknowledged: dispatch_row.get(2),
            stale_ack_count: stale_ack_row.get(0),
        })
    }
}

#[derive(Debug, Deserialize)]
struct DecisionQuery {
    instrument: String,
    timeframe: String,
    min_coverage_pct: Option<f64>,
}

#[derive(Debug, Serialize)]
struct DecisionResponse {
    instrument: String,
    timeframe: String,
    decision: &'static str,
    reason: Option<String>,
    min_coverage_pct: f64,
    evaluated_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
struct UpdateKillSwitchRequest {
    active: bool,
    reason: String,
    actor: Option<String>,
}

#[derive(Debug, Serialize)]
struct KillSwitchState {
    active: bool,
    reason: String,
    updated_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
struct OrderIntentRequest {
    idempotency_key: String,
    exchange: String,
    account_id: String,
    pair_id: Option<String>,
    instrument: String,
    timeframe: String,
    action: String,
    spread_direction: Option<String>,
    spread_z: Option<f64>,
    side: String,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<String>,
    min_coverage_pct: Option<f64>,
}

#[derive(Debug, Serialize)]
struct OrderIntentResponse {
    idempotency_key: String,
    exchange: String,
    account_id: String,
    pair_id: Option<String>,
    instrument: String,
    timeframe: String,
    action: String,
    spread_direction: Option<String>,
    spread_z: Option<f64>,
    side: String,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<String>,
    min_coverage_pct: f64,
    decision: String,
    reason: Option<String>,
    evaluated_at: DateTime<Utc>,
}

#[derive(Debug)]
struct OrderIntentRecord {
    idempotency_key: String,
    exchange: String,
    account_id: String,
    pair_id: Option<String>,
    instrument: String,
    timeframe: String,
    action: String,
    spread_direction: Option<String>,
    spread_z: Option<f64>,
    side: String,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<String>,
    min_coverage_pct: f64,
    decision: String,
    reason: String,
    created_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
struct OrderStateHistoryQuery {
    idempotency_key: String,
}

#[derive(Debug, Serialize)]
struct OrderStateHistoryResponse {
    idempotency_key: String,
    intent: OrderIntentResponse,
    state_events: Vec<OrderStateEvent>,
    dispatch_attempts: Vec<DispatchAttempt>,
}

#[derive(Debug, Serialize)]
struct OrderStateEvent {
    state: String,
    reason: String,
    actor: String,
    created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
struct DispatchAttempt {
    attempt_no: i32,
    result_state: String,
    exchange_order_id: Option<String>,
    reason: String,
    actor: String,
    created_at: DateTime<Utc>,
}

#[derive(Debug)]
struct SpreadLedgerEvent {
    pair_id: String,
    action: String,
    spread_direction: Option<String>,
    spread_z: Option<f64>,
    qty: f64,
    created_at: DateTime<Utc>,
}

#[derive(Debug, Default)]
struct FoldedSpreadPosition {
    direction: String,
    total_size: f64,
    avg_entry_z: f64,
    updated_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
struct PortfolioPositionsQuery {
    exchange: String,
    account_id: String,
}

#[derive(Debug, Serialize)]
struct PortfolioPositionRow {
    pair_id: String,
    direction: String,
    total_size: f64,
    avg_entry_z: f64,
    updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
struct PortfolioPositionsResponse {
    exchange: String,
    account_id: String,
    generated_at: DateTime<Utc>,
    positions: Vec<PortfolioPositionRow>,
}

#[derive(Debug, Deserialize)]
struct ExecutionObservabilitySummaryQuery {
    exchange: String,
    account_id: String,
    window_minutes: Option<i64>,
}

#[derive(Debug, Serialize)]
struct ExecutionObservabilitySummaryResponse {
    generated_at: DateTime<Utc>,
    exchange: String,
    account_id: String,
    window_minutes: i64,
    thresholds: ExecutionObservabilityThresholdsResponse,
    metrics: ExecutionObservabilityMetricsResponse,
    alerts: Vec<ExecutionObservabilityAlert>,
}

#[derive(Debug, Serialize)]
struct ExecutionObservabilityThresholdsResponse {
    risk_block_ratio_p2: f64,
    dispatch_reject_ratio_p2: f64,
    stale_ack_count_p1: i64,
    reconcile_block_count_p1: i64,
}

#[derive(Debug, Serialize)]
struct ExecutionObservabilityMetricsResponse {
    intents_total: i64,
    intents_blocked: i64,
    risk_blocked: i64,
    integrity_blocked: i64,
    reconcile_blocked: i64,
    kill_switch_blocked: i64,
    dispatch_total: i64,
    dispatch_rejected: i64,
    dispatch_acknowledged: i64,
    stale_ack_count: i64,
}

#[derive(Debug, Serialize)]
struct ExecutionObservabilityAlert {
    code: String,
    severity: String,
    triggered: bool,
    message: String,
}

#[derive(Debug, Clone, Copy)]
struct ExecutionObservabilityMetricsRaw {
    intents_total: i64,
    intents_blocked: i64,
    risk_blocked: i64,
    integrity_blocked: i64,
    reconcile_blocked: i64,
    kill_switch_blocked: i64,
    dispatch_total: i64,
    dispatch_rejected: i64,
    dispatch_acknowledged: i64,
    stale_ack_count: i64,
}

#[derive(Debug, Deserialize)]
struct DispatchIntentRequest {
    idempotency_key: String,
    actor: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OrderEventIngestRequest {
    idempotency_key: Option<String>,
    exchange_order_id: Option<String>,
    to_state: String,
    reason: Option<String>,
    actor: Option<String>,
}

#[derive(Debug, Serialize)]
struct DispatchIntentResponse {
    idempotency_key: String,
    result: String,
    from_state: Option<String>,
    to_state: Option<String>,
    exchange_order_id: Option<String>,
    reason: Option<String>,
    attempted_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
struct OrderEventIngestResponse {
    idempotency_key: String,
    exchange_order_id: Option<String>,
    result: String,
    from_state: Option<String>,
    to_state: Option<String>,
    reason: Option<String>,
    event_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Debug)]
enum ApiError {
    BadRequest(String),
    Upstream(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        match self {
            Self::BadRequest(message) => (
                StatusCode::BAD_REQUEST,
                Json(ErrorResponse { error: message }),
            )
                .into_response(),
            Self::Upstream(message) => (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(ErrorResponse { error: message }),
            )
                .into_response(),
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let postgres_url = std::env::var("POSTGRES_URL").unwrap_or_else(|_| {
        "postgres://cryptopairs:cryptopairs@127.0.0.1:5432/cryptopairs".to_string()
    });
    let account_service_url = std::env::var("ACCOUNT_SERVICE_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8081".to_string());
    let port = std::env::var("EXECUTION_SERVICE_PORT").unwrap_or_else(|_| "8082".to_string());
    let default_min_coverage_pct = std::env::var("INTEGRITY_MIN_COVERAGE_PCT")
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
        .unwrap_or(99.5);
    let dispatch_mode = DispatchMode::parse(
        &std::env::var("EXECUTION_DISPATCH_MODE").unwrap_or_else(|_| "fail_closed".to_string()),
    );
    let ack_watchdog = AckWatchdogConfig {
        poll_interval_seconds: std::env::var("EXECUTION_ACK_WATCHDOG_POLL_SECONDS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(15),
        expire_after_seconds: std::env::var("EXECUTION_ACK_EXPIRE_AFTER_SECONDS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(90),
        batch_limit: std::env::var("EXECUTION_ACK_WATCHDOG_BATCH_LIMIT")
            .ok()
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(200),
    };
    let open_orders_poller = OpenOrdersPollerConfig {
        enabled: std::env::var("EXECUTION_OPENORDERS_POLLER_ENABLED")
            .ok()
            .and_then(|value| value.parse::<bool>().ok())
            .unwrap_or(true),
        poll_interval_seconds: std::env::var("EXECUTION_OPENORDERS_POLL_SECONDS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(5),
        batch_limit: std::env::var("EXECUTION_OPENORDERS_POLL_BATCH_LIMIT")
            .ok()
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(200),
    };
    let order_status_lookup = OrderStatusLookupConfig {
        enabled: std::env::var("EXECUTION_ORDER_STATUS_LOOKUP_ENABLED")
            .ok()
            .and_then(|value| value.parse::<bool>().ok())
            .unwrap_or(false),
        query_key: std::env::var("KRAKEN_FUTURES_ORDER_STATUS_QUERY_KEY")
            .unwrap_or_else(|_| "orderId".to_string()),
    };
    let trigger_reconcile_on_terminal = std::env::var("EXECUTION_TRIGGER_RECONCILE_ON_TERMINAL")
        .ok()
        .and_then(|value| value.parse::<bool>().ok())
        .unwrap_or(true);
    let risk_caps = RiskCapsConfig {
        per_pair_max_qty: std::env::var("EXECUTION_RISK_PER_PAIR_MAX_QTY")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(12.0),
        gross_max_qty: std::env::var("EXECUTION_RISK_GROSS_MAX_QTY")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(40.0),
        max_leverage: std::env::var("EXECUTION_RISK_MAX_LEVERAGE")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(3.0),
        daily_loss_limit_usd: std::env::var("EXECUTION_RISK_DAILY_LOSS_LIMIT_USD")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(500.0),
        entry_cooldown_seconds: std::env::var("EXECUTION_RISK_ENTRY_COOLDOWN_SECONDS")
            .ok()
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(30),
    };
    let risk_max_snapshot_age_seconds = std::env::var("EXECUTION_RISK_MAX_SNAPSHOT_AGE_SECONDS")
        .ok()
        .and_then(|value| value.parse::<i64>().ok())
        .unwrap_or(120);
    let observability_thresholds = ExecutionObservabilityThresholds {
        risk_block_ratio_p2: std::env::var("EXECUTION_ALERT_RISK_BLOCK_RATIO_P2")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(0.25),
        dispatch_reject_ratio_p2: std::env::var("EXECUTION_ALERT_DISPATCH_REJECT_RATIO_P2")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(0.15),
        stale_ack_count_p1: std::env::var("EXECUTION_ALERT_STALE_ACK_COUNT_P1")
            .ok()
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(1),
        reconcile_block_count_p1: std::env::var("EXECUTION_ALERT_RECONCILE_BLOCK_COUNT_P1")
            .ok()
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(1),
    };
    let http_client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()?;
    let kraken_live = if matches!(dispatch_mode, DispatchMode::LiveKraken) {
        match KrakenLiveClient::from_env() {
            Ok(client) => Some(Arc::new(client)),
            Err(reason) => {
                info!(
                    reason = %reason,
                    "live_kraken dispatch mode configured but client initialization failed; dispatch will fail closed"
                );
                None
            }
        }
    } else {
        None
    };
    let bind_addr = format!("0.0.0.0:{port}");

    let repository = Arc::new(ExecutionRepository::connect(&postgres_url).await?);
    let app_state = AppState {
        repository,
        postgres_url: Arc::new(postgres_url.clone()),
        account_service_url: Arc::new(account_service_url.clone()),
        http_client,
        default_min_coverage_pct,
        dispatch_mode,
        kraken_live,
        ack_watchdog,
        open_orders_poller,
        order_status_lookup: order_status_lookup.clone(),
        trigger_reconcile_on_terminal,
        risk_caps,
        risk_max_snapshot_age_seconds,
        observability_thresholds,
    };
    tokio::spawn(spawn_ack_watchdog(app_state.clone()));
    tokio::spawn(spawn_open_orders_poller(app_state.clone()));
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);
    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/execution/decision", get(decision))
        .route(
            "/v1/execution/kill-switch",
            get(kill_switch).post(update_kill_switch),
        )
        .route("/v1/execution/order-intent", post(order_intent))
        .route(
            "/v1/execution/portfolio/positions",
            get(portfolio_positions),
        )
        .route(
            "/v1/execution/observability/summary",
            get(execution_observability_summary),
        )
        .route(
            "/v1/execution/order-intent/history",
            get(order_intent_history),
        )
        .route(
            "/v1/execution/order-intent/dispatch",
            post(dispatch_order_intent),
        )
        .route("/v1/execution/order-event", post(ingest_order_event))
        .layer(cors)
        .with_state(app_state);

    let listener = TcpListener::bind(&bind_addr).await?;
    info!(
        bind_addr = %bind_addr,
        postgres_url = %postgres_url,
        account_service_url = %account_service_url,
        default_min_coverage_pct,
        dispatch_mode = ?dispatch_mode,
        ack_watchdog_poll_seconds = ack_watchdog.poll_interval_seconds,
        ack_expire_after_seconds = ack_watchdog.expire_after_seconds,
        ack_watchdog_batch_limit = ack_watchdog.batch_limit,
        openorders_poller_enabled = open_orders_poller.enabled,
        openorders_poll_seconds = open_orders_poller.poll_interval_seconds,
        openorders_poll_batch_limit = open_orders_poller.batch_limit,
        order_status_lookup_enabled = order_status_lookup.enabled,
        order_status_query_key = %order_status_lookup.query_key,
        trigger_reconcile_on_terminal,
        risk_per_pair_max_qty = risk_caps.per_pair_max_qty,
        risk_gross_max_qty = risk_caps.gross_max_qty,
        risk_max_leverage = risk_caps.max_leverage,
        risk_daily_loss_limit_usd = risk_caps.daily_loss_limit_usd,
        risk_entry_cooldown_seconds = risk_caps.entry_cooldown_seconds,
        risk_max_snapshot_age_seconds = risk_max_snapshot_age_seconds,
        alert_risk_block_ratio_p2 = observability_thresholds.risk_block_ratio_p2,
        alert_dispatch_reject_ratio_p2 = observability_thresholds.dispatch_reject_ratio_p2,
        alert_stale_ack_count_p1 = observability_thresholds.stale_ack_count_p1,
        alert_reconcile_block_count_p1 = observability_thresholds.reconcile_block_count_p1,
        "execution-service started"
    );
    axum::serve(listener, app).await?;
    Ok(())
}

async fn spawn_ack_watchdog(state: AppState) {
    let poll_every = Duration::from_secs(state.ack_watchdog.poll_interval_seconds.max(1));
    loop {
        if let Err(error) = run_ack_watchdog_once(&state).await {
            info!(error = %error, "execution ack watchdog iteration failed");
        }
        sleep(poll_every).await;
    }
}

async fn spawn_open_orders_poller(state: AppState) {
    if !state.open_orders_poller.enabled {
        info!("execution openorders poller disabled");
        return;
    }
    let poll_every = Duration::from_secs(state.open_orders_poller.poll_interval_seconds.max(1));
    loop {
        if let Err(error) = run_open_orders_poll_once(&state).await {
            info!(error = %error, "execution openorders poller iteration failed");
        }
        sleep(poll_every).await;
    }
}

async fn run_open_orders_poll_once(state: &AppState) -> anyhow::Result<()> {
    let Some(client) = &state.kraken_live else {
        return Ok(());
    };

    let tracked_orders = state
        .repository
        .fetch_live_tracked_orders(state.open_orders_poller.batch_limit)
        .await?;
    if tracked_orders.is_empty() {
        return Ok(());
    }

    let open_orders = client
        .fetch_open_orders()
        .await
        .map_err(anyhow::Error::msg)?;
    for tracked in tracked_orders {
        let transition = if let Some(open_order) = open_orders.get(&tracked.exchange_order_id) {
            derive_open_order_transition(tracked.current_state, open_order)
        } else if state.order_status_lookup.enabled {
            let status_order = client
                .fetch_order_status_by_query(
                    &tracked.exchange_order_id,
                    &state.order_status_lookup.query_key,
                )
                .await
                .map_err(anyhow::Error::msg)?;
            status_order
                .and_then(|order| derive_order_status_transition(tracked.current_state, &order))
        } else {
            None
        };
        let Some((target_state, reason)) = transition else {
            continue;
        };

        let transitioned = transition_order_state_if_current(
            state,
            &tracked.idempotency_key,
            tracked.current_state,
            target_state,
            &reason,
            "openorders-poller",
        )
        .await
        .map_err(|error| anyhow::anyhow!(api_error_to_message(error)))?;
        if !transitioned {
            continue;
        }

        info!(
            idempotency_key = %tracked.idempotency_key,
            exchange_order_id = %tracked.exchange_order_id,
            from_state = %tracked.current_state.as_str(),
            to_state = %target_state.as_str(),
            reason = %reason,
            "execution openorders poller applied lifecycle transition"
        );
        if is_terminal_state(target_state) {
            let intent = state
                .repository
                .fetch_order_intent(&tracked.idempotency_key)
                .await?;
            if let Some(intent) = intent {
                trigger_reconcile_after_terminal(state, &intent, target_state, "openorders-poller")
                    .await;
            }
        }
    }

    Ok(())
}

fn derive_open_order_transition(
    current_state: OrderLifecycleState,
    open_order: &KrakenOpenOrder,
) -> Option<(OrderLifecycleState, String)> {
    if let (Some(filled), Some(unfilled)) = (open_order.filled_size, open_order.unfilled_size) {
        if filled > 0.0 && unfilled > 0.0 && current_state == OrderLifecycleState::Acknowledged {
            return Some((
                OrderLifecycleState::PartiallyFilled,
                format!(
                    "openorders poller: status={} filled_size={filled:.8} unfilled_size={unfilled:.8}",
                    open_order.status.as_deref().unwrap_or("unknown")
                ),
            ));
        }
        if filled > 0.0 && unfilled <= 0.0 {
            return Some((
                OrderLifecycleState::Filled,
                format!(
                    "openorders poller inferred filled: status={} filled_size={filled:.8} unfilled_size={unfilled:.8}",
                    open_order.status.as_deref().unwrap_or("unknown")
                ),
            ));
        }
    }

    let status = open_order
        .status
        .as_deref()
        .unwrap_or("unknown")
        .to_ascii_lowercase();
    if status.contains("partial") && current_state == OrderLifecycleState::Acknowledged {
        return Some((
            OrderLifecycleState::PartiallyFilled,
            format!("openorders poller: status={status}"),
        ));
    }
    if status.contains("cancel") {
        return Some((
            OrderLifecycleState::Canceled,
            format!("openorders poller: status={status}"),
        ));
    }
    if status.contains("reject") {
        return Some((
            OrderLifecycleState::Rejected,
            format!("openorders poller: status={status}"),
        ));
    }
    if status.contains("expire") {
        return Some((
            OrderLifecycleState::Expired,
            format!("openorders poller: status={status}"),
        ));
    }
    if status == "filled" {
        return Some((
            OrderLifecycleState::Filled,
            "openorders poller: status=filled".to_string(),
        ));
    }
    None
}

fn derive_order_status_transition(
    current_state: OrderLifecycleState,
    order: &KrakenStatusOrder,
) -> Option<(OrderLifecycleState, String)> {
    let status = order.status.to_ascii_uppercase();
    match status.as_str() {
        "FULLY_EXECUTED" => Some((
            OrderLifecycleState::Filled,
            format!(
                "order status lookup: status=FULLY_EXECUTED filled={:.8} quantity={:.8}",
                order.filled.unwrap_or(0.0),
                order.quantity.unwrap_or(0.0)
            ),
        )),
        "CANCELLED" => Some((
            OrderLifecycleState::Canceled,
            "order status lookup: status=CANCELLED".to_string(),
        )),
        "REJECTED" | "TRIGGER_ACTIVATION_FAILURE" => Some((
            OrderLifecycleState::Rejected,
            format!("order status lookup: status={status}"),
        )),
        "ENTERED_BOOK" => {
            if let (Some(filled), Some(quantity)) = (order.filled, order.quantity) {
                if filled >= quantity && quantity > 0.0 {
                    return Some((
                        OrderLifecycleState::Filled,
                        format!(
                            "order status lookup: status=ENTERED_BOOK filled={filled:.8} quantity={quantity:.8}"
                        ),
                    ));
                }
                if filled > 0.0
                    && filled < quantity
                    && current_state == OrderLifecycleState::Acknowledged
                {
                    return Some((
                        OrderLifecycleState::PartiallyFilled,
                        format!(
                            "order status lookup: status=ENTERED_BOOK filled={filled:.8} quantity={quantity:.8}"
                        ),
                    ));
                }
            }
            None
        }
        "EXPIRED" => Some((
            OrderLifecycleState::Expired,
            "order status lookup: status=EXPIRED".to_string(),
        )),
        _ => None,
    }
}

async fn run_ack_watchdog_once(state: &AppState) -> anyhow::Result<()> {
    let stale_orders = state
        .repository
        .fetch_stale_acknowledged_orders(
            state.ack_watchdog.expire_after_seconds as i64,
            state.ack_watchdog.batch_limit,
        )
        .await?;
    if stale_orders.is_empty() {
        return Ok(());
    }

    for idempotency_key in stale_orders {
        let transitioned = transition_order_state_if_current(
            state,
            &idempotency_key,
            OrderLifecycleState::Acknowledged,
            OrderLifecycleState::Expired,
            "ack watchdog expired order: no terminal update received within threshold",
            "ack-watchdog",
        )
        .await
        .map_err(|error| anyhow::anyhow!(api_error_to_message(error)))?;
        if transitioned {
            info!(
                idempotency_key = %idempotency_key,
                expire_after_seconds = state.ack_watchdog.expire_after_seconds,
                "execution ack watchdog expired stale acknowledged order"
            );
            let intent = state
                .repository
                .fetch_order_intent(&idempotency_key)
                .await?;
            if let Some(intent) = intent {
                trigger_reconcile_after_terminal(
                    state,
                    &intent,
                    OrderLifecycleState::Expired,
                    "ack-watchdog",
                )
                .await;
            }
        }
    }

    Ok(())
}

fn is_terminal_state(state: OrderLifecycleState) -> bool {
    matches!(
        state,
        OrderLifecycleState::Filled
            | OrderLifecycleState::Canceled
            | OrderLifecycleState::Rejected
            | OrderLifecycleState::Expired
    )
}

async fn trigger_reconcile_after_terminal(
    state: &AppState,
    intent: &OrderIntentRecord,
    terminal_state: OrderLifecycleState,
    source: &str,
) {
    if !state.trigger_reconcile_on_terminal {
        return;
    }
    if !is_terminal_state(terminal_state) {
        return;
    }

    let endpoint = format!(
        "{}/v1/account/reconcile/run",
        state.account_service_url.trim_end_matches('/')
    );
    info!(
        idempotency_key = %intent.idempotency_key,
        exchange = %intent.exchange,
        account_id = %intent.account_id,
        terminal_state = %terminal_state.as_str(),
        source = %source,
        endpoint = %endpoint,
        "execution triggering account reconciliation after terminal state"
    );
    let response = state.http_client.post(&endpoint).send().await;
    match response {
        Ok(resp) if resp.status().is_success() => {
            info!(
                idempotency_key = %intent.idempotency_key,
                terminal_state = %terminal_state.as_str(),
                source = %source,
                status = %resp.status(),
                "execution terminal-state reconcile trigger succeeded"
            );
        }
        Ok(resp) => {
            info!(
                idempotency_key = %intent.idempotency_key,
                terminal_state = %terminal_state.as_str(),
                source = %source,
                status = %resp.status(),
                "execution terminal-state reconcile trigger failed"
            );
        }
        Err(error) => {
            info!(
                idempotency_key = %intent.idempotency_key,
                terminal_state = %terminal_state.as_str(),
                source = %source,
                error = %error,
                "execution terminal-state reconcile trigger errored"
            );
        }
    }
}

fn api_error_to_message(error: ApiError) -> String {
    match error {
        ApiError::BadRequest(message) | ApiError::Upstream(message) => message,
    }
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

fn safe_ratio(numerator: i64, denominator: i64) -> f64 {
    if denominator <= 0 {
        return 0.0;
    }
    numerator as f64 / denominator as f64
}

fn build_execution_alerts(
    metrics: ExecutionObservabilityMetricsRaw,
    thresholds: ExecutionObservabilityThresholds,
) -> Vec<ExecutionObservabilityAlert> {
    let risk_block_ratio = safe_ratio(metrics.risk_blocked, metrics.intents_total);
    let dispatch_reject_ratio = safe_ratio(metrics.dispatch_rejected, metrics.dispatch_total);

    vec![
        ExecutionObservabilityAlert {
            code: "execution_risk_block_ratio".to_string(),
            severity: "P2".to_string(),
            triggered: risk_block_ratio >= thresholds.risk_block_ratio_p2,
            message: format!(
                "risk-block ratio={risk_block_ratio:.4} threshold={:.4}",
                thresholds.risk_block_ratio_p2
            ),
        },
        ExecutionObservabilityAlert {
            code: "execution_dispatch_reject_ratio".to_string(),
            severity: "P2".to_string(),
            triggered: dispatch_reject_ratio >= thresholds.dispatch_reject_ratio_p2,
            message: format!(
                "dispatch-reject ratio={dispatch_reject_ratio:.4} threshold={:.4}",
                thresholds.dispatch_reject_ratio_p2
            ),
        },
        ExecutionObservabilityAlert {
            code: "execution_stale_ack_count".to_string(),
            severity: "P1".to_string(),
            triggered: metrics.stale_ack_count >= thresholds.stale_ack_count_p1,
            message: format!(
                "stale ACK count={} threshold={}",
                metrics.stale_ack_count, thresholds.stale_ack_count_p1
            ),
        },
        ExecutionObservabilityAlert {
            code: "execution_reconcile_block_count".to_string(),
            severity: "P1".to_string(),
            triggered: metrics.reconcile_blocked >= thresholds.reconcile_block_count_p1,
            message: format!(
                "reconcile-block count={} threshold={}",
                metrics.reconcile_blocked, thresholds.reconcile_block_count_p1
            ),
        },
    ]
}

async fn execution_observability_summary(
    State(state): State<AppState>,
    Query(query): Query<ExecutionObservabilitySummaryQuery>,
) -> Result<Json<ExecutionObservabilitySummaryResponse>, ApiError> {
    if query.exchange.trim().is_empty() || query.account_id.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "exchange and account_id are required".to_string(),
        ));
    }
    let window_minutes = query.window_minutes.unwrap_or(60).clamp(1, 24 * 60);
    let metrics = state
        .repository
        .fetch_observability_metrics(
            &query.exchange,
            &query.account_id,
            window_minutes,
            state.ack_watchdog.expire_after_seconds as i64,
        )
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let alerts = build_execution_alerts(metrics, state.observability_thresholds);

    Ok(Json(ExecutionObservabilitySummaryResponse {
        generated_at: Utc::now(),
        exchange: query.exchange,
        account_id: query.account_id,
        window_minutes,
        thresholds: ExecutionObservabilityThresholdsResponse {
            risk_block_ratio_p2: state.observability_thresholds.risk_block_ratio_p2,
            dispatch_reject_ratio_p2: state.observability_thresholds.dispatch_reject_ratio_p2,
            stale_ack_count_p1: state.observability_thresholds.stale_ack_count_p1,
            reconcile_block_count_p1: state.observability_thresholds.reconcile_block_count_p1,
        },
        metrics: ExecutionObservabilityMetricsResponse {
            intents_total: metrics.intents_total,
            intents_blocked: metrics.intents_blocked,
            risk_blocked: metrics.risk_blocked,
            integrity_blocked: metrics.integrity_blocked,
            reconcile_blocked: metrics.reconcile_blocked,
            kill_switch_blocked: metrics.kill_switch_blocked,
            dispatch_total: metrics.dispatch_total,
            dispatch_rejected: metrics.dispatch_rejected,
            dispatch_acknowledged: metrics.dispatch_acknowledged,
            stale_ack_count: metrics.stale_ack_count,
        },
        alerts,
    }))
}

async fn decision(
    State(state): State<AppState>,
    Query(query): Query<DecisionQuery>,
) -> Result<Json<DecisionResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected one of 1m, 15m, 1h".to_string())
    })?;
    let min_coverage_pct = query
        .min_coverage_pct
        .unwrap_or(state.default_min_coverage_pct);
    let gate_decision = evaluate_integrity_gate_from_store(
        &state.postgres_url,
        &query.instrument,
        timeframe,
        min_coverage_pct,
    )
    .await
    .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (decision, reason) = match gate_decision {
        GateDecision::Allowed => ("ALLOWED", None),
        GateDecision::Blocked(reason) => ("BLOCKED", Some(reason)),
    };

    Ok(Json(DecisionResponse {
        instrument: query.instrument,
        timeframe: timeframe.as_str().to_string(),
        decision,
        reason,
        min_coverage_pct,
        evaluated_at: Utc::now(),
    }))
}

fn fold_spread_positions(events: &[SpreadLedgerEvent]) -> Vec<PortfolioPositionRow> {
    let mut by_pair: HashMap<String, FoldedSpreadPosition> = HashMap::new();
    for event in events {
        if !event.qty.is_finite() || event.qty <= 0.0 {
            continue;
        }
        let state = by_pair.entry(event.pair_id.clone()).or_default();
        if event.action == "ENTRY" {
            let direction = event
                .spread_direction
                .as_deref()
                .unwrap_or("NONE")
                .to_string();
            if state.total_size <= 0.0 {
                state.direction = direction;
                state.total_size = event.qty;
                state.avg_entry_z = event.spread_z.unwrap_or(0.0);
            } else {
                let prior_size = state.total_size;
                let next_size = prior_size + event.qty;
                let next_avg = if let Some(z) = event.spread_z {
                    ((state.avg_entry_z * prior_size) + (z * event.qty))
                        / next_size.max(f64::EPSILON)
                } else {
                    state.avg_entry_z
                };
                state.total_size = next_size;
                if state.direction == "NONE" {
                    state.direction = direction;
                }
                state.avg_entry_z = next_avg;
            }
            state.updated_at = event.created_at;
            continue;
        }

        if event.action == "EXIT" || event.action == "EMERGENCY_STOP_CLOSE" {
            if state.total_size <= 0.0 {
                continue;
            }
            let remaining = (state.total_size - event.qty).max(0.0);
            state.total_size = remaining;
            state.updated_at = event.created_at;
            if remaining <= 0.0 {
                state.direction = "NONE".to_string();
                state.avg_entry_z = 0.0;
            }
        }
    }

    let mut rows: Vec<_> = by_pair
        .into_iter()
        .filter_map(|(pair_id, folded)| {
            if folded.total_size <= 0.0 {
                return None;
            }
            Some(PortfolioPositionRow {
                pair_id,
                direction: folded.direction,
                total_size: folded.total_size,
                avg_entry_z: folded.avg_entry_z,
                updated_at: folded.updated_at,
            })
        })
        .collect();
    rows.sort_by(|left, right| right.updated_at.cmp(&left.updated_at));
    rows
}

async fn portfolio_positions(
    State(state): State<AppState>,
    Query(query): Query<PortfolioPositionsQuery>,
) -> Result<Json<PortfolioPositionsResponse>, ApiError> {
    if query.exchange.trim().is_empty() || query.account_id.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "exchange and account_id are required".to_string(),
        ));
    }
    let events = state
        .repository
        .fetch_spread_ledger_events(&query.exchange, &query.account_id)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let positions = fold_spread_positions(&events);
    info!(
        exchange = %query.exchange,
        account_id = %query.account_id,
        positions_count = positions.len(),
        "execution portfolio positions generated"
    );
    Ok(Json(PortfolioPositionsResponse {
        exchange: query.exchange,
        account_id: query.account_id,
        generated_at: Utc::now(),
        positions,
    }))
}

async fn kill_switch(State(state): State<AppState>) -> Result<Json<KillSwitchState>, ApiError> {
    let current = state
        .repository
        .get_kill_switch_state()
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    Ok(Json(current))
}

async fn update_kill_switch(
    State(state): State<AppState>,
    Json(payload): Json<UpdateKillSwitchRequest>,
) -> Result<Json<KillSwitchState>, ApiError> {
    if payload.active && payload.reason.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "reason is required when enabling kill switch".to_string(),
        ));
    }
    let actor = payload.actor.unwrap_or_else(|| "operator".to_string());
    let reason = if payload.reason.trim().is_empty() {
        "manual update".to_string()
    } else {
        payload.reason
    };

    let updated = state
        .repository
        .set_kill_switch_state(payload.active, &reason, &actor)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    info!(
        active = updated.active,
        reason = %updated.reason,
        actor = %actor,
        "execution kill switch updated"
    );

    Ok(Json(updated))
}

async fn fetch_latest_account_snapshot_from_service(
    state: &AppState,
    exchange: &str,
    account_id: &str,
) -> anyhow::Result<Option<AccountSnapshotRow>> {
    let url = format!(
        "{}/v1/account/snapshot",
        state.account_service_url.trim_end_matches('/')
    );
    let response = state
        .http_client
        .get(url)
        .query(&[("exchange", exchange), ("account_id", account_id)])
        .send()
        .await?;
    if !response.status().is_success() {
        return Err(anyhow::anyhow!(
            "account-service snapshot read failed with status {}",
            response.status()
        ));
    }
    let payload: AccountServiceSnapshotResponse = response.json().await?;
    Ok(payload.snapshot.map(|snapshot| AccountSnapshotRow {
        ts: snapshot.ts,
        equity: snapshot.equity,
        margin_used: snapshot.margin_used,
    }))
}

async fn fetch_day_start_equity_from_service(
    state: &AppState,
    exchange: &str,
    account_id: &str,
    day_start_utc: DateTime<Utc>,
) -> anyhow::Result<Option<f64>> {
    let url = format!(
        "{}/v1/account/snapshot/day-start",
        state.account_service_url.trim_end_matches('/')
    );
    let day_start_utc_raw = day_start_utc.to_rfc3339();
    let response = state
        .http_client
        .get(url)
        .query(&[
            ("exchange", exchange),
            ("account_id", account_id),
            ("day_start_utc", day_start_utc_raw.as_str()),
        ])
        .send()
        .await?;
    if !response.status().is_success() {
        return Err(anyhow::anyhow!(
            "account-service day-start snapshot read failed with status {}",
            response.status()
        ));
    }
    let payload: AccountServiceSnapshotResponse = response.json().await?;
    Ok(payload.snapshot.map(|snapshot| snapshot.equity))
}

async fn fetch_latest_reconcile_decision_from_service(
    state: &AppState,
    exchange: &str,
    account_id: &str,
) -> anyhow::Result<ReconcileDecision> {
    let url = format!(
        "{}/v1/account/reconcile",
        state.account_service_url.trim_end_matches('/')
    );
    let response = state
        .http_client
        .get(url)
        .query(&[("exchange", exchange), ("account_id", account_id)])
        .send()
        .await?;
    if !response.status().is_success() {
        return Err(anyhow::anyhow!(
            "account-service reconcile read failed with status {}",
            response.status()
        ));
    }
    let payload: AccountServiceReconcileResponse = response.json().await?;
    let Some(reconcile) = payload.reconcile else {
        return Ok(ReconcileDecision::Blocked(format!(
            "reconcile gate blocked signal: no reconcile history for exchange={exchange} account_id={account_id}"
        )));
    };
    if reconcile.status == "OK" {
        Ok(ReconcileDecision::Allowed)
    } else {
        Ok(ReconcileDecision::Blocked(format!(
            "reconcile gate blocked signal: status={} drift_notional={:.4} notes={}",
            reconcile.status, reconcile.drift_notional, reconcile.notes
        )))
    }
}

fn is_snapshot_stale(
    snapshot_ts: DateTime<Utc>,
    now: DateTime<Utc>,
    max_snapshot_age_seconds: i64,
) -> bool {
    (now - snapshot_ts).num_seconds() > max_snapshot_age_seconds.max(0)
}

async fn evaluate_risk_gate_from_store(
    state: &AppState,
    exchange: &str,
    account_id: &str,
    instrument: &str,
    action: OrderIntentAction,
    request_qty: f64,
) -> anyhow::Result<GateDecision> {
    if !matches!(action, OrderIntentAction::Entry) {
        return Ok(GateDecision::Allowed);
    }

    let latest_snapshot = match fetch_latest_account_snapshot_from_service(
        state, exchange, account_id,
    )
    .await
    {
        Ok(snapshot) => snapshot,
        Err(error) => {
            return Ok(GateDecision::Blocked(format!(
                "risk gate blocked signal: failed to fetch account snapshot from account-service: {error}"
            )));
        }
    };

    let Some(latest_snapshot) = latest_snapshot else {
        return Ok(GateDecision::Blocked(format!(
            "risk gate blocked signal: no account snapshot for exchange={exchange} account_id={account_id}"
        )));
    };

    let now = Utc::now();
    let snapshot_age_seconds = (now - latest_snapshot.ts).num_seconds();
    if is_snapshot_stale(latest_snapshot.ts, now, state.risk_max_snapshot_age_seconds) {
        return Ok(GateDecision::Blocked(format!(
            "risk gate blocked signal: stale account snapshot age_seconds={snapshot_age_seconds} max_age_seconds={}",
            state.risk_max_snapshot_age_seconds.max(0)
        )));
    }

    let day_start = chrono::DateTime::<Utc>::from_naive_utc_and_offset(
        Utc::now()
            .date_naive()
            .and_hms_opt(0, 0, 0)
            .expect("midnight is valid"),
        Utc,
    );
    let day_start_equity = match fetch_day_start_equity_from_service(
        state, exchange, account_id, day_start,
    )
    .await
    {
        Ok(Some(equity)) => equity,
        Ok(None) => {
            return Ok(GateDecision::Blocked(format!(
                "risk gate blocked signal: no day-start account snapshot for exchange={exchange} account_id={account_id} day_start_utc={}",
                day_start.to_rfc3339()
            )));
        }
        Err(error) => {
            return Ok(GateDecision::Blocked(format!(
                "risk gate blocked signal: failed to fetch day-start account snapshot from account-service: {error}"
            )));
        }
    };
    let daily_loss_usd = (day_start_equity - latest_snapshot.equity).max(0.0);
    let leverage = if latest_snapshot.equity > 0.0 {
        latest_snapshot.margin_used / latest_snapshot.equity
    } else {
        f64::INFINITY
    };
    let active_pair_qty = state
        .repository
        .fetch_active_pair_qty(exchange, account_id, instrument)
        .await?;
    let active_gross_qty = state
        .repository
        .fetch_active_gross_qty(exchange, account_id)
        .await?;
    let last_entry_ts = state
        .repository
        .fetch_last_accepted_entry_ts(exchange, account_id, instrument)
        .await?;
    let seconds_since_last_entry = last_entry_ts.map(|ts| (Utc::now() - ts).num_seconds());

    Ok(evaluate_risk_caps(
        action,
        RiskCheckInput {
            active_pair_qty,
            active_gross_qty,
            request_qty,
            leverage,
            daily_loss_usd,
            seconds_since_last_entry,
        },
        state.risk_caps,
    ))
}

async fn order_intent(
    State(state): State<AppState>,
    Json(payload): Json<OrderIntentRequest>,
) -> Result<Json<OrderIntentResponse>, ApiError> {
    if payload.idempotency_key.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "idempotency_key is required".to_string(),
        ));
    }
    if payload.exchange.trim().is_empty() || payload.account_id.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "exchange and account_id are required".to_string(),
        ));
    }
    if payload.qty <= 0.0 {
        return Err(ApiError::BadRequest("qty must be > 0".to_string()));
    }
    let timeframe = Timeframe::parse(&payload.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected one of 1m, 15m, 1h".to_string())
    })?;
    let action = OrderIntentAction::parse(&payload.action).ok_or_else(|| {
        ApiError::BadRequest("action must be one of ENTRY, EXIT, EMERGENCY_STOP_CLOSE".to_string())
    })?;
    let side = normalize_side(&payload.side)
        .ok_or_else(|| ApiError::BadRequest("side must be BUY or SELL".to_string()))?;
    let normalized_operator_id = normalize_optional_string(payload.operator_id.as_deref());
    let normalized_pair_id = normalize_optional_string(payload.pair_id.as_deref());
    let normalized_spread_direction =
        normalize_spread_direction(payload.spread_direction.as_deref())?;
    let normalized_spread_z = payload
        .spread_z
        .filter(|value| value.is_finite() && value.abs() <= 100.0);
    if payload.spread_z.is_some() && normalized_spread_z.is_none() {
        return Err(ApiError::BadRequest(
            "spread_z must be finite and within +/-100 when provided".to_string(),
        ));
    }
    validate_manual_controls(
        action,
        payload.operator_confirmed,
        normalized_operator_id.as_deref(),
    )?;

    let min_coverage_pct = payload
        .min_coverage_pct
        .unwrap_or(state.default_min_coverage_pct);

    if let Some(existing) = state
        .repository
        .fetch_order_intent(&payload.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
    {
        if !is_same_intent(
            &existing,
            &payload.exchange,
            &payload.account_id,
            normalized_pair_id.as_deref(),
            &payload.instrument,
            timeframe,
            action,
            normalized_spread_direction.as_deref(),
            normalized_spread_z,
            side,
            payload.qty,
            payload.operator_confirmed,
            normalized_operator_id.as_deref(),
            min_coverage_pct,
        ) {
            return Err(ApiError::BadRequest(
                "idempotency_key already used with different payload".to_string(),
            ));
        }
        return Ok(Json(map_order_intent(existing)));
    }

    let kill_switch = state
        .repository
        .get_kill_switch_state()
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    let gate_decision = if matches!(action, OrderIntentAction::EmergencyStopClose) {
        GateDecision::Allowed
    } else {
        evaluate_integrity_gate_from_store(
            &state.postgres_url,
            &payload.instrument,
            timeframe,
            min_coverage_pct,
        )
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
    };

    let reconcile_decision = if matches!(action, OrderIntentAction::EmergencyStopClose) {
        ReconcileDecision::Allowed
    } else {
        fetch_latest_reconcile_decision_from_service(&state, &payload.exchange, &payload.account_id)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?
    };

    let risk_decision = if matches!(action, OrderIntentAction::EmergencyStopClose) {
        GateDecision::Allowed
    } else {
        evaluate_risk_gate_from_store(
            &state,
            &payload.exchange,
            &payload.account_id,
            &payload.instrument,
            action,
            payload.qty,
        )
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
    };

    let intent_decision = evaluate_order_intent(
        action,
        kill_switch.active,
        gate_decision,
        reconcile_decision,
        risk_decision,
    );
    let (decision, reason) = match intent_decision {
        OrderIntentDecision::Accepted => ("ACCEPTED".to_string(), String::new()),
        OrderIntentDecision::Blocked(reason) => ("BLOCKED".to_string(), reason),
    };

    let record = OrderIntentRecord {
        idempotency_key: payload.idempotency_key,
        exchange: payload.exchange,
        account_id: payload.account_id,
        pair_id: normalized_pair_id,
        instrument: payload.instrument,
        timeframe: timeframe.as_str().to_string(),
        action: action.as_str().to_string(),
        spread_direction: normalized_spread_direction,
        spread_z: normalized_spread_z,
        side: side.to_string(),
        qty: payload.qty,
        operator_confirmed: payload.operator_confirmed,
        operator_id: normalized_operator_id,
        min_coverage_pct,
        decision,
        reason,
        created_at: Utc::now(),
    };

    state
        .repository
        .insert_order_intent(&record)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    let stored = state
        .repository
        .fetch_order_intent(&record.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
        .ok_or_else(|| ApiError::Upstream("order intent persistence failed".to_string()))?;

    info!(
        idempotency_key = %stored.idempotency_key,
        action = %stored.action,
        operator_confirmed = stored.operator_confirmed,
        decision = %stored.decision,
        reason = %stored.reason,
        "execution order intent evaluated"
    );

    Ok(Json(map_order_intent(stored)))
}

async fn order_intent_history(
    State(state): State<AppState>,
    Query(query): Query<OrderStateHistoryQuery>,
) -> Result<Json<OrderStateHistoryResponse>, ApiError> {
    if query.idempotency_key.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "idempotency_key is required".to_string(),
        ));
    }

    let intent = state
        .repository
        .fetch_order_intent(&query.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
        .ok_or_else(|| ApiError::BadRequest("idempotency_key not found".to_string()))?;

    let state_events = state
        .repository
        .fetch_order_state_history(&query.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    let dispatch_attempts = state
        .repository
        .fetch_dispatch_attempts(&query.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    Ok(Json(OrderStateHistoryResponse {
        idempotency_key: query.idempotency_key,
        intent: map_order_intent(intent),
        state_events,
        dispatch_attempts,
    }))
}

async fn dispatch_order_intent(
    State(state): State<AppState>,
    Json(payload): Json<DispatchIntentRequest>,
) -> Result<Json<DispatchIntentResponse>, ApiError> {
    if payload.idempotency_key.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "idempotency_key is required".to_string(),
        ));
    }

    let actor = payload.actor.unwrap_or_else(|| "operator".to_string());
    let intent = state
        .repository
        .fetch_order_intent(&payload.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
        .ok_or_else(|| ApiError::BadRequest("idempotency_key not found".to_string()))?;

    if intent.decision != "ACCEPTED" {
        return Ok(Json(DispatchIntentResponse {
            idempotency_key: payload.idempotency_key,
            result: "NOOP".to_string(),
            from_state: state
                .repository
                .fetch_latest_order_state(&intent.idempotency_key)
                .await
                .map_err(|error| ApiError::Upstream(error.to_string()))?
                .map(|state| state.as_str().to_string()),
            to_state: None,
            exchange_order_id: None,
            reason: Some(format!(
                "dispatch skipped: decision={} reason={}",
                intent.decision, intent.reason
            )),
            attempted_at: Utc::now(),
        }));
    }

    let current_state = state
        .repository
        .fetch_latest_order_state(&intent.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
        .ok_or_else(|| {
            ApiError::Upstream("order lifecycle missing current state for dispatch".to_string())
        })?;

    if current_state != OrderLifecycleState::Approved {
        return Ok(Json(DispatchIntentResponse {
            idempotency_key: payload.idempotency_key,
            result: "NOOP".to_string(),
            from_state: Some(current_state.as_str().to_string()),
            to_state: None,
            exchange_order_id: None,
            reason: Some(format!(
                "dispatch skipped: expected state=APPROVED current_state={}",
                current_state.as_str()
            )),
            attempted_at: Utc::now(),
        }));
    }

    let transitioned = transition_order_state_if_current(
        &state,
        &intent.idempotency_key,
        OrderLifecycleState::Approved,
        OrderLifecycleState::PendingSubmit,
        "dispatch accepted; pending exchange submit",
        &actor,
    )
    .await?;
    if !transitioned {
        return Ok(Json(DispatchIntentResponse {
            idempotency_key: payload.idempotency_key,
            result: "NOOP".to_string(),
            from_state: Some(OrderLifecycleState::Approved.as_str().to_string()),
            to_state: None,
            exchange_order_id: None,
            reason: Some("dispatch skipped: state changed concurrently".to_string()),
            attempted_at: Utc::now(),
        }));
    }

    let (result_state, result_reason, exchange_order_id) = match state.dispatch_mode {
        DispatchMode::FailClosed => (
            OrderLifecycleState::Rejected,
            "dispatch failed closed: live submit adapter not configured".to_string(),
            None,
        ),
        DispatchMode::SimulateAck => {
            let synthetic_id = format!(
                "SIM-{}-{}",
                intent.idempotency_key,
                Utc::now().timestamp_millis()
            );
            (
                OrderLifecycleState::Acknowledged,
                "dispatch acknowledged in simulate_ack mode".to_string(),
                Some(synthetic_id),
            )
        }
        DispatchMode::LiveKraken => {
            if let Some(client) = &state.kraken_live {
                match client.submit_order(&intent).await {
                    Ok(success) => (
                        OrderLifecycleState::Acknowledged,
                        success.reason,
                        Some(success.exchange_order_id),
                    ),
                    Err(reason) => (
                        OrderLifecycleState::Rejected,
                        format!("kraken live submit failed closed: {reason}"),
                        None,
                    ),
                }
            } else {
                (
                    OrderLifecycleState::Rejected,
                    "kraken live submit failed closed: missing or invalid live credentials/config"
                        .to_string(),
                    None,
                )
            }
        }
    };

    let transitioned = transition_order_state_if_current(
        &state,
        &intent.idempotency_key,
        OrderLifecycleState::PendingSubmit,
        result_state,
        &result_reason,
        "execution-dispatch",
    )
    .await?;
    if !transitioned {
        return Ok(Json(DispatchIntentResponse {
            idempotency_key: payload.idempotency_key,
            result: "NOOP".to_string(),
            from_state: Some(OrderLifecycleState::PendingSubmit.as_str().to_string()),
            to_state: None,
            exchange_order_id: None,
            reason: Some("dispatch skipped: pending state changed concurrently".to_string()),
            attempted_at: Utc::now(),
        }));
    }

    state
        .repository
        .insert_dispatch_attempt(
            &intent.idempotency_key,
            result_state,
            exchange_order_id.as_deref(),
            &result_reason,
            &actor,
        )
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    if is_terminal_state(result_state) {
        trigger_reconcile_after_terminal(&state, &intent, result_state, "dispatch").await;
    }

    info!(
        idempotency_key = %intent.idempotency_key,
        dispatch_mode = ?state.dispatch_mode,
        result_state = %result_state.as_str(),
        reason = %result_reason,
        "execution dispatch attempt completed"
    );

    Ok(Json(DispatchIntentResponse {
        idempotency_key: payload.idempotency_key,
        result: if result_state == OrderLifecycleState::Acknowledged {
            "ACKNOWLEDGED".to_string()
        } else {
            "REJECTED".to_string()
        },
        from_state: Some(OrderLifecycleState::Approved.as_str().to_string()),
        to_state: Some(result_state.as_str().to_string()),
        exchange_order_id,
        reason: Some(result_reason),
        attempted_at: Utc::now(),
    }))
}

async fn ingest_order_event(
    State(state): State<AppState>,
    Json(payload): Json<OrderEventIngestRequest>,
) -> Result<Json<OrderEventIngestResponse>, ApiError> {
    let normalized_idempotency_key = payload
        .idempotency_key
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string);
    let normalized_exchange_order_id = payload
        .exchange_order_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string);
    if normalized_idempotency_key.is_none() && normalized_exchange_order_id.is_none() {
        return Err(ApiError::BadRequest(
            "idempotency_key or exchange_order_id is required".to_string(),
        ));
    }

    let target_state = parse_ingest_target_state(&payload.to_state).ok_or_else(|| {
        ApiError::BadRequest(
            "to_state must be one of ACKNOWLEDGED, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED"
                .to_string(),
        )
    })?;
    let actor = payload
        .actor
        .unwrap_or_else(|| "execution-event-ingest".to_string());
    let reason = payload
        .reason
        .unwrap_or_else(|| "exchange lifecycle update".to_string());

    let resolved_intent = if let Some(idempotency_key) = &normalized_idempotency_key {
        state
            .repository
            .fetch_order_intent(idempotency_key)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?
            .ok_or_else(|| ApiError::BadRequest("idempotency_key not found".to_string()))?
    } else if let Some(exchange_order_id) = &normalized_exchange_order_id {
        state
            .repository
            .fetch_order_intent_by_exchange_order_id(exchange_order_id)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?
            .ok_or_else(|| ApiError::BadRequest("exchange_order_id not found".to_string()))?
    } else {
        return Err(ApiError::BadRequest("missing order identity".to_string()));
    };
    let resolved_idempotency_key = resolved_intent.idempotency_key.clone();

    if let Some(exchange_order_id) = &normalized_exchange_order_id {
        let from_exchange_lookup = state
            .repository
            .fetch_order_intent_by_exchange_order_id(exchange_order_id)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?;
        if let Some(intent_by_exchange) = from_exchange_lookup {
            if intent_by_exchange.idempotency_key != resolved_intent.idempotency_key {
                return Err(ApiError::BadRequest(
                    "idempotency_key and exchange_order_id do not reference the same order"
                        .to_string(),
                ));
            }
        }
    }

    let current_state = state
        .repository
        .fetch_latest_order_state(&resolved_idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
        .ok_or_else(|| ApiError::Upstream("order lifecycle missing current state".to_string()))?;

    if current_state == target_state {
        let exchange_order_id = normalized_exchange_order_id.or(state
            .repository
            .fetch_latest_exchange_order_id(&resolved_idempotency_key)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?);
        return Ok(Json(OrderEventIngestResponse {
            idempotency_key: resolved_idempotency_key.clone(),
            exchange_order_id,
            result: "NOOP".to_string(),
            from_state: Some(current_state.as_str().to_string()),
            to_state: None,
            reason: Some("order event ignored: already in requested state".to_string()),
            event_at: Utc::now(),
        }));
    }

    if !can_transition_state(current_state, target_state) {
        let exchange_order_id = normalized_exchange_order_id.or(state
            .repository
            .fetch_latest_exchange_order_id(&resolved_idempotency_key)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?);
        return Ok(Json(OrderEventIngestResponse {
            idempotency_key: resolved_idempotency_key.clone(),
            exchange_order_id,
            result: "NOOP".to_string(),
            from_state: Some(current_state.as_str().to_string()),
            to_state: None,
            reason: Some(format!(
                "order event ignored: invalid transition {} -> {}",
                current_state.as_str(),
                target_state.as_str()
            )),
            event_at: Utc::now(),
        }));
    }

    let transitioned = transition_order_state_if_current(
        &state,
        &resolved_idempotency_key,
        current_state,
        target_state,
        &reason,
        &actor,
    )
    .await?;
    if !transitioned {
        let exchange_order_id = normalized_exchange_order_id.or(state
            .repository
            .fetch_latest_exchange_order_id(&resolved_idempotency_key)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?);
        return Ok(Json(OrderEventIngestResponse {
            idempotency_key: resolved_idempotency_key.clone(),
            exchange_order_id,
            result: "NOOP".to_string(),
            from_state: Some(current_state.as_str().to_string()),
            to_state: None,
            reason: Some("order event ignored: state changed concurrently".to_string()),
            event_at: Utc::now(),
        }));
    }

    let exchange_order_id = normalized_exchange_order_id.or(state
        .repository
        .fetch_latest_exchange_order_id(&resolved_idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?);

    info!(
        idempotency_key = %resolved_idempotency_key,
        exchange_order_id = ?exchange_order_id,
        from_state = %current_state.as_str(),
        to_state = %target_state.as_str(),
        actor = %actor,
        reason = %reason,
        "execution order event ingested"
    );

    if is_terminal_state(target_state) {
        trigger_reconcile_after_terminal(&state, &resolved_intent, target_state, "order-event")
            .await;
    }

    Ok(Json(OrderEventIngestResponse {
        idempotency_key: resolved_idempotency_key,
        exchange_order_id,
        result: "APPLIED".to_string(),
        from_state: Some(current_state.as_str().to_string()),
        to_state: Some(target_state.as_str().to_string()),
        reason: Some(reason),
        event_at: Utc::now(),
    }))
}

async fn transition_order_state_if_current(
    state: &AppState,
    idempotency_key: &str,
    from_state: OrderLifecycleState,
    to_state: OrderLifecycleState,
    reason: &str,
    actor: &str,
) -> Result<bool, ApiError> {
    if !can_transition_state(from_state, to_state) {
        return Err(ApiError::BadRequest(format!(
            "invalid lifecycle transition: {} -> {}",
            from_state.as_str(),
            to_state.as_str()
        )));
    }

    let latest = state
        .repository
        .fetch_latest_order_state(idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    if latest != Some(from_state) {
        return Ok(false);
    }

    state
        .repository
        .record_state_event(idempotency_key, to_state, reason, actor)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    Ok(true)
}

fn validate_manual_controls(
    action: OrderIntentAction,
    operator_confirmed: bool,
    operator_id: Option<&str>,
) -> Result<(), ApiError> {
    if matches!(action, OrderIntentAction::Entry | OrderIntentAction::Exit) {
        if !operator_confirmed {
            return Err(ApiError::BadRequest(
                "manual ENTRY/EXIT requires operator_confirmed=true".to_string(),
            ));
        }
        if operator_id.is_none() {
            return Err(ApiError::BadRequest(
                "manual ENTRY/EXIT requires operator_id".to_string(),
            ));
        }
    }
    Ok(())
}

fn normalize_optional_string(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn normalize_spread_direction(value: Option<&str>) -> Result<Option<String>, ApiError> {
    let Some(raw) = value.map(str::trim).filter(|raw| !raw.is_empty()) else {
        return Ok(None);
    };
    if raw == "LONG_SPREAD" || raw == "SHORT_SPREAD" {
        return Ok(Some(raw.to_string()));
    }
    Err(ApiError::BadRequest(
        "spread_direction must be LONG_SPREAD or SHORT_SPREAD when provided".to_string(),
    ))
}

fn parse_ingest_target_state(value: &str) -> Option<OrderLifecycleState> {
    match value {
        "ACKNOWLEDGED" => Some(OrderLifecycleState::Acknowledged),
        "PARTIALLY_FILLED" => Some(OrderLifecycleState::PartiallyFilled),
        "FILLED" => Some(OrderLifecycleState::Filled),
        "CANCELED" => Some(OrderLifecycleState::Canceled),
        "REJECTED" => Some(OrderLifecycleState::Rejected),
        "EXPIRED" => Some(OrderLifecycleState::Expired),
        _ => None,
    }
}

#[allow(clippy::too_many_arguments)]
fn is_same_intent(
    existing: &OrderIntentRecord,
    exchange: &str,
    account_id: &str,
    pair_id: Option<&str>,
    instrument: &str,
    timeframe: Timeframe,
    action: OrderIntentAction,
    spread_direction: Option<&str>,
    spread_z: Option<f64>,
    side: &str,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<&str>,
    min_coverage_pct: f64,
) -> bool {
    existing.exchange == exchange
        && existing.account_id == account_id
        && existing.pair_id.as_deref() == pair_id
        && existing.instrument == instrument
        && existing.timeframe == timeframe.as_str()
        && existing.action == action.as_str()
        && existing.spread_direction.as_deref() == spread_direction
        && match (existing.spread_z, spread_z) {
            (Some(left), Some(right)) => (left - right).abs() < f64::EPSILON,
            (None, None) => true,
            _ => false,
        }
        && existing.side == side
        && (existing.qty - qty).abs() < f64::EPSILON
        && existing.operator_confirmed == operator_confirmed
        && existing.operator_id.as_deref() == operator_id
        && (existing.min_coverage_pct - min_coverage_pct).abs() < f64::EPSILON
}

fn map_order_intent(record: OrderIntentRecord) -> OrderIntentResponse {
    OrderIntentResponse {
        idempotency_key: record.idempotency_key,
        exchange: record.exchange,
        account_id: record.account_id,
        pair_id: record.pair_id,
        instrument: record.instrument,
        timeframe: record.timeframe,
        action: record.action,
        spread_direction: record.spread_direction,
        spread_z: record.spread_z,
        side: record.side,
        qty: record.qty,
        operator_confirmed: record.operator_confirmed,
        operator_id: record.operator_id,
        min_coverage_pct: record.min_coverage_pct,
        decision: record.decision,
        reason: if record.reason.is_empty() {
            None
        } else {
            Some(record.reason)
        },
        evaluated_at: record.created_at,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        build_execution_alerts, build_uri_component, derive_open_order_transition,
        derive_order_status_transition, fold_spread_positions, is_snapshot_stale,
        is_terminal_state, parse_ingest_target_state, parse_kraken_open_orders_response,
        parse_kraken_order_status_response, parse_kraken_submit_response, resolve_secret_value,
        safe_ratio, sign_kraken_futures_payload, validate_manual_controls, ApiError, DispatchMode,
        ExecutionObservabilityMetricsRaw, ExecutionObservabilityThresholds, KrakenOpenOrder,
        KrakenStatusOrder, SpreadLedgerEvent,
    };
    use chrono::{DateTime, Duration, Utc};
    use execution_service::{OrderIntentAction, OrderLifecycleState};
    use serde::Deserialize;

    #[derive(Debug, Deserialize)]
    struct NormalizationMatrixFixture {
        open_orders: Vec<OpenOrderCase>,
        order_status: Vec<OrderStatusCase>,
    }

    #[derive(Debug, Deserialize)]
    struct OpenOrderCase {
        current_state: String,
        order: KrakenOpenOrder,
        expected_to_state: Option<String>,
    }

    #[derive(Debug, Deserialize)]
    struct OrderStatusCase {
        current_state: String,
        order: KrakenStatusOrder,
        expected_to_state: Option<String>,
    }

    #[test]
    fn manual_entry_requires_operator_confirmation() {
        let result = validate_manual_controls(OrderIntentAction::Entry, false, Some("ops-1"));
        assert!(matches!(result, Err(ApiError::BadRequest(_))));
    }

    #[test]
    fn manual_exit_requires_operator_id() {
        let result = validate_manual_controls(OrderIntentAction::Exit, true, None);
        assert!(matches!(result, Err(ApiError::BadRequest(_))));
    }

    #[test]
    fn emergency_stop_can_run_without_operator_confirmation() {
        let result = validate_manual_controls(OrderIntentAction::EmergencyStopClose, false, None);
        assert!(result.is_ok());
    }

    #[test]
    fn dispatch_mode_defaults_fail_closed() {
        assert!(matches!(
            DispatchMode::parse("unknown"),
            DispatchMode::FailClosed
        ));
        assert!(matches!(
            DispatchMode::parse("simulate_ack"),
            DispatchMode::SimulateAck
        ));
        assert!(matches!(
            DispatchMode::parse("live_kraken"),
            DispatchMode::LiveKraken
        ));
    }

    #[test]
    fn kraken_signing_produces_non_empty_signature() {
        let signature = sign_kraken_futures_payload(
            "orderType=mkt&symbol=PI_XBTUSD&side=buy&size=1&cliOrdId=abc123",
            "1739938400000",
            "/derivatives/api/v3/sendorder",
            "dGVzdF9zZWNyZXQ=",
        )
        .expect("signature should be generated");
        assert!(!signature.is_empty());
    }

    #[test]
    fn build_uri_component_encodes_query_pairs() {
        let uri_component = build_uri_component(
            "/derivatives/api/v3/orders/status",
            &[("orderId", "abc 123"), ("batch", "x/y")],
        );
        assert_eq!(
            uri_component,
            "/derivatives/api/v3/orders/status?orderId=abc%20123&batch=x%2Fy"
        );
    }

    #[test]
    fn kraken_signing_changes_with_uri_component() {
        let without_query = sign_kraken_futures_payload(
            "",
            "1739938400000",
            "/derivatives/api/v3/orders/status",
            "dGVzdF9zZWNyZXQ=",
        )
        .expect("signature should be generated");
        let with_query = sign_kraken_futures_payload(
            "",
            "1739938400000",
            "/derivatives/api/v3/orders/status?orderId=abc%20123",
            "dGVzdF9zZWNyZXQ=",
        )
        .expect("signature should be generated");
        assert_ne!(without_query, with_query);
    }

    #[test]
    fn parse_kraken_submit_response_extracts_order_id() {
        let body = r#"{
          "result":"success",
          "sendStatus":{
            "status":"placed",
            "orderEvents":[{"type":"PLACE","order":{"orderId":"abc-order-1"}}]
          }
        }"#;
        let parsed = parse_kraken_submit_response(body).expect("expected success payload");
        assert_eq!(parsed.exchange_order_id, "abc-order-1");
    }

    #[test]
    fn parse_kraken_submit_response_rejects_non_success() {
        let body = r#"{
          "result":"success",
          "sendStatus":{"status":"insufficientAvailableFunds"}
        }"#;
        let parsed = parse_kraken_submit_response(body);
        assert!(parsed.is_err());
    }

    #[test]
    fn parse_ingest_target_state_accepts_expected_states() {
        assert_eq!(
            parse_ingest_target_state("PARTIALLY_FILLED"),
            Some(OrderLifecycleState::PartiallyFilled)
        );
        assert_eq!(
            parse_ingest_target_state("FILLED"),
            Some(OrderLifecycleState::Filled)
        );
        assert_eq!(
            parse_ingest_target_state("CANCELED"),
            Some(OrderLifecycleState::Canceled)
        );
    }

    #[test]
    fn parse_ingest_target_state_rejects_non_event_state() {
        assert_eq!(parse_ingest_target_state("APPROVED"), None);
        assert_eq!(parse_ingest_target_state("NEW"), None);
    }

    #[test]
    fn terminal_state_predicate_matches_policy() {
        assert!(is_terminal_state(OrderLifecycleState::Filled));
        assert!(is_terminal_state(OrderLifecycleState::Canceled));
        assert!(is_terminal_state(OrderLifecycleState::Rejected));
        assert!(is_terminal_state(OrderLifecycleState::Expired));
        assert!(!is_terminal_state(OrderLifecycleState::Acknowledged));
        assert!(!is_terminal_state(OrderLifecycleState::PartiallyFilled));
    }

    #[test]
    fn parse_kraken_open_orders_response_reads_order_ids() {
        let body = r#"{
          "result":"success",
          "openOrders":[
            {"order_id":"o1","status":"untouched","filledSize":0,"unfilledSize":10},
            {"order_id":"o2","status":"partially_filled","filledSize":2,"unfilledSize":8}
          ]
        }"#;
        let parsed = parse_kraken_open_orders_response(body).expect("valid open orders response");
        assert!(parsed.contains_key("o1"));
        assert!(parsed.contains_key("o2"));
    }

    #[test]
    fn derive_open_order_transition_promotes_partial_fill() {
        let open = KrakenOpenOrder {
            order_id: "o1".to_string(),
            status: Some("untouched".to_string()),
            filled_size: Some(1.0),
            unfilled_size: Some(9.0),
        };
        let transition = derive_open_order_transition(OrderLifecycleState::Acknowledged, &open);
        assert!(matches!(
            transition,
            Some((OrderLifecycleState::PartiallyFilled, _))
        ));
    }

    #[test]
    fn derive_open_order_transition_noop_for_untouched_zero_fill() {
        let open = KrakenOpenOrder {
            order_id: "o1".to_string(),
            status: Some("untouched".to_string()),
            filled_size: Some(0.0),
            unfilled_size: Some(10.0),
        };
        let transition = derive_open_order_transition(OrderLifecycleState::Acknowledged, &open);
        assert!(transition.is_none());
    }

    #[test]
    fn parse_kraken_order_status_response_reads_orders() {
        let body = r#"{
          "result":"success",
          "orders":[
            {"type":"ORDER","orderId":"o1","status":"ENTERED_BOOK","filled":1.0,"quantity":10.0},
            {"type":"ORDER","orderId":"o2","status":"FULLY_EXECUTED","filled":10.0,"quantity":10.0}
          ],
          "serverTime":"2020-08-27T17:03:33.196Z"
        }"#;
        let parsed = parse_kraken_order_status_response(body).expect("valid order status response");
        assert_eq!(parsed.len(), 2);
        assert_eq!(parsed[0].order_id, "o1");
        assert_eq!(parsed[1].order_id, "o2");
    }

    #[test]
    fn derive_order_status_transition_maps_terminal_states() {
        let fully = KrakenStatusOrder {
            order_id: "o1".to_string(),
            status: "FULLY_EXECUTED".to_string(),
            filled: Some(10.0),
            quantity: Some(10.0),
        };
        let cancelled = KrakenStatusOrder {
            order_id: "o2".to_string(),
            status: "CANCELLED".to_string(),
            filled: Some(0.0),
            quantity: Some(10.0),
        };
        let rejected = KrakenStatusOrder {
            order_id: "o3".to_string(),
            status: "REJECTED".to_string(),
            filled: Some(0.0),
            quantity: Some(10.0),
        };

        assert!(matches!(
            derive_order_status_transition(OrderLifecycleState::Acknowledged, &fully),
            Some((OrderLifecycleState::Filled, _))
        ));
        assert!(matches!(
            derive_order_status_transition(OrderLifecycleState::Acknowledged, &cancelled),
            Some((OrderLifecycleState::Canceled, _))
        ));
        assert!(matches!(
            derive_order_status_transition(OrderLifecycleState::Acknowledged, &rejected),
            Some((OrderLifecycleState::Rejected, _))
        ));
    }

    #[test]
    fn derive_order_status_transition_maps_entered_book_partial() {
        let partial = KrakenStatusOrder {
            order_id: "o1".to_string(),
            status: "ENTERED_BOOK".to_string(),
            filled: Some(2.0),
            quantity: Some(10.0),
        };
        assert!(matches!(
            derive_order_status_transition(OrderLifecycleState::Acknowledged, &partial),
            Some((OrderLifecycleState::PartiallyFilled, _))
        ));
    }

    fn read_fixture(name: &str) -> String {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join("kraken")
            .join(name);
        std::fs::read_to_string(&path)
            .unwrap_or_else(|error| panic!("failed to read fixture {}: {error}", path.display()))
    }

    #[test]
    fn replay_openorders_fixture_maps_partial_fill_transition() {
        let fixture = read_fixture("openorders.success.json");
        let open_orders =
            parse_kraken_open_orders_response(&fixture).expect("fixture should parse");
        let tracked = open_orders
            .get("022774bc-2c4a-4f26-9317-436c8d85746d")
            .expect("expected order from fixture");
        let transition = derive_open_order_transition(OrderLifecycleState::Acknowledged, tracked);
        assert!(matches!(
            transition,
            Some((OrderLifecycleState::PartiallyFilled, _))
        ));
    }

    #[test]
    fn replay_order_status_fixture_maps_terminal_transitions() {
        let fixture = read_fixture("order_status.success.json");
        let orders = parse_kraken_order_status_response(&fixture).expect("fixture should parse");
        let by_id: std::collections::HashMap<_, _> = orders
            .into_iter()
            .map(|order| (order.order_id.clone(), order))
            .collect();

        let fully = by_id.get("f1111111-1111-1111-1111-111111111111").unwrap();
        let cancelled = by_id.get("c2222222-2222-2222-2222-222222222222").unwrap();
        let rejected = by_id.get("r3333333-3333-3333-3333-333333333333").unwrap();

        assert!(matches!(
            derive_order_status_transition(OrderLifecycleState::Acknowledged, fully),
            Some((OrderLifecycleState::Filled, _))
        ));
        assert!(matches!(
            derive_order_status_transition(OrderLifecycleState::Acknowledged, cancelled),
            Some((OrderLifecycleState::Canceled, _))
        ));
        assert!(matches!(
            derive_order_status_transition(OrderLifecycleState::Acknowledged, rejected),
            Some((OrderLifecycleState::Rejected, _))
        ));
    }

    #[test]
    fn replay_normalization_matrix_fixture() {
        let fixture = read_fixture("normalization_matrix.json");
        let matrix: NormalizationMatrixFixture =
            serde_json::from_str(&fixture).expect("normalization matrix fixture should parse");

        for case in matrix.open_orders {
            let current = OrderLifecycleState::parse(&case.current_state)
                .expect("current_state should be valid lifecycle state");
            let got = derive_open_order_transition(current, &case.order)
                .map(|(state, _)| state.as_str().to_string());
            assert_eq!(got, case.expected_to_state, "open-order case failed");
        }

        for case in matrix.order_status {
            let current = OrderLifecycleState::parse(&case.current_state)
                .expect("current_state should be valid lifecycle state");
            let got = derive_order_status_transition(current, &case.order)
                .map(|(state, _)| state.as_str().to_string());
            assert_eq!(got, case.expected_to_state, "order-status case failed");
        }
    }

    #[test]
    fn snapshot_freshness_blocks_when_older_than_threshold() {
        let now = Utc::now();
        assert!(is_snapshot_stale(now - Duration::seconds(121), now, 120));
        assert!(!is_snapshot_stale(now - Duration::seconds(120), now, 120));
    }

    #[test]
    fn fold_spread_positions_applies_entry_add_and_exit() {
        let t0 = DateTime::parse_from_rfc3339("2026-02-20T03:00:00Z")
            .expect("valid time")
            .with_timezone(&Utc);
        let t1 = DateTime::parse_from_rfc3339("2026-02-20T03:01:00Z")
            .expect("valid time")
            .with_timezone(&Utc);
        let t2 = DateTime::parse_from_rfc3339("2026-02-20T03:02:00Z")
            .expect("valid time")
            .with_timezone(&Utc);
        let rows = fold_spread_positions(&[
            SpreadLedgerEvent {
                pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
                action: "ENTRY".to_string(),
                spread_direction: Some("LONG_SPREAD".to_string()),
                spread_z: Some(-2.0),
                qty: 1.0,
                created_at: t0,
            },
            SpreadLedgerEvent {
                pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
                action: "ENTRY".to_string(),
                spread_direction: Some("LONG_SPREAD".to_string()),
                spread_z: Some(-1.0),
                qty: 1.0,
                created_at: t1,
            },
            SpreadLedgerEvent {
                pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
                action: "EXIT".to_string(),
                spread_direction: Some("LONG_SPREAD".to_string()),
                spread_z: None,
                qty: 0.5,
                created_at: t2,
            },
        ]);
        assert_eq!(rows.len(), 1);
        let row = &rows[0];
        assert_eq!(row.pair_id, "PI_XBTUSD__PI_ETHUSD");
        assert_eq!(row.direction, "LONG_SPREAD");
        assert!((row.total_size - 1.5).abs() < f64::EPSILON);
        assert!((row.avg_entry_z - (-1.5)).abs() < f64::EPSILON);
    }

    #[test]
    fn fold_spread_positions_drops_closed_positions() {
        let t0 = DateTime::parse_from_rfc3339("2026-02-20T03:00:00Z")
            .expect("valid time")
            .with_timezone(&Utc);
        let t1 = DateTime::parse_from_rfc3339("2026-02-20T03:01:00Z")
            .expect("valid time")
            .with_timezone(&Utc);
        let rows = fold_spread_positions(&[
            SpreadLedgerEvent {
                pair_id: "PI_SOLUSD__PI_XRPUSD".to_string(),
                action: "ENTRY".to_string(),
                spread_direction: Some("SHORT_SPREAD".to_string()),
                spread_z: Some(2.1),
                qty: 1.25,
                created_at: t0,
            },
            SpreadLedgerEvent {
                pair_id: "PI_SOLUSD__PI_XRPUSD".to_string(),
                action: "EMERGENCY_STOP_CLOSE".to_string(),
                spread_direction: Some("SHORT_SPREAD".to_string()),
                spread_z: None,
                qty: 1.25,
                created_at: t1,
            },
        ]);
        assert!(rows.is_empty());
    }

    #[test]
    fn safe_ratio_returns_zero_for_empty_denominator() {
        assert!((safe_ratio(5, 0) - 0.0).abs() < f64::EPSILON);
        assert!((safe_ratio(2, 4) - 0.5).abs() < f64::EPSILON);
    }

    #[test]
    fn execution_observability_alerts_trigger_on_thresholds() {
        let metrics = ExecutionObservabilityMetricsRaw {
            intents_total: 10,
            intents_blocked: 4,
            risk_blocked: 3,
            integrity_blocked: 0,
            reconcile_blocked: 2,
            kill_switch_blocked: 0,
            dispatch_total: 8,
            dispatch_rejected: 2,
            dispatch_acknowledged: 6,
            stale_ack_count: 1,
        };
        let thresholds = ExecutionObservabilityThresholds {
            risk_block_ratio_p2: 0.25,
            dispatch_reject_ratio_p2: 0.2,
            stale_ack_count_p1: 1,
            reconcile_block_count_p1: 2,
        };
        let alerts = build_execution_alerts(metrics, thresholds);
        assert_eq!(alerts.len(), 4);
        assert!(alerts.iter().all(|alert| alert.triggered));
    }

    #[test]
    fn resolve_secret_value_prefers_direct_value() {
        let value = resolve_secret_value(
            "KRAKEN_FUTURES_API_KEY",
            Some(" direct-value ".to_string()),
            None,
        )
        .expect("direct value should resolve");
        assert_eq!(value, "direct-value");
    }

    #[test]
    fn resolve_secret_value_reads_file_when_direct_missing() {
        let path = std::env::temp_dir().join(format!(
            "cryptopairs-secret-{}.txt",
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        std::fs::write(&path, " file-secret ").expect("secret file should be writable");
        let value = resolve_secret_value(
            "KRAKEN_FUTURES_API_KEY",
            None,
            Some(path.to_string_lossy().to_string()),
        )
        .expect("file value should resolve");
        assert_eq!(value, "file-secret");
        let _ = std::fs::remove_file(path);
    }
}
