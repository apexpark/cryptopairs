use crate::{repository::MarketDataRepository, AppState};
use chrono::{TimeZone, Utc};
use common_types::TradeTick;
use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use std::sync::Arc;
use tokio::time::{sleep, Duration};
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

const KRAKEN_WS_URL: &str = "wss://futures.kraken.com/ws/v1";

pub fn spawn_trade_ingest_worker(
    state: AppState,
    symbols: Vec<String>,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        loop {
            if let Err(error) = run_session(state.repository.clone(), symbols.clone()).await {
                warn!(error = %error, "kraken ws ingest session failed; reconnecting");
            }
            sleep(Duration::from_secs(3)).await;
        }
    })
}

async fn run_session(
    repository: Arc<dyn MarketDataRepository>,
    symbols: Vec<String>,
) -> anyhow::Result<()> {
    let (mut socket, _) = connect_async(KRAKEN_WS_URL).await?;
    let subscribe = serde_json::json!({
        "event": "subscribe",
        "feed": "trade",
        "product_ids": symbols
    });
    socket
        .send(Message::Text(subscribe.to_string()))
        .await
        .map_err(|error| anyhow::anyhow!(error.to_string()))?;

    info!("kraken ws trade subscription established");

    while let Some(frame) = socket.next().await {
        match frame {
            Ok(Message::Text(payload)) => {
                if let Err(error) = handle_message(&repository, &payload).await {
                    warn!(error = %error, "failed handling ws payload");
                }
            }
            Ok(Message::Ping(payload)) => {
                socket
                    .send(Message::Pong(payload))
                    .await
                    .map_err(|error| anyhow::anyhow!(error.to_string()))?;
            }
            Ok(Message::Close(_)) => {
                warn!("kraken ws closed connection");
                break;
            }
            Ok(_) => {}
            Err(error) => {
                return Err(anyhow::anyhow!(error.to_string()));
            }
        }
    }

    Ok(())
}

async fn handle_message(
    repository: &Arc<dyn MarketDataRepository>,
    payload: &str,
) -> anyhow::Result<()> {
    let value: Value = serde_json::from_str(payload)?;
    let Some(feed) = value.get("feed").and_then(|v| v.as_str()) else {
        return Ok(());
    };

    let trades = match feed {
        "trade_snapshot" => value
            .get("trades")
            .and_then(|v| v.as_array())
            .map(|rows| rows.iter().filter_map(parse_trade).collect::<Vec<_>>())
            .unwrap_or_default(),
        "trade" => parse_trade(&value).into_iter().collect(),
        _ => Vec::new(),
    };

    if trades.is_empty() {
        return Ok(());
    }

    match repository.insert_trades(&trades).await {
        Ok(inserted) => {
            info!(received = trades.len(), inserted, "ws trades persisted");
        }
        Err(error) => {
            error!(error = %error, "failed persisting ws trades");
        }
    }
    Ok(())
}

fn parse_trade(value: &Value) -> Option<TradeTick> {
    let instrument = value.get("product_id")?.as_str()?.to_string();
    let seq = value.get("seq")?.as_i64()?;
    let ts_ms = value.get("time")?.as_i64()?;
    let ts = Utc.timestamp_millis_opt(ts_ms).single()?;
    let side = value.get("side")?.as_str()?.to_string();
    let uid = value.get("uid")?.as_str()?.to_string();
    let qty = parse_numeric(value.get("qty")?)?;
    let price = parse_numeric(value.get("price")?)?;

    Some(TradeTick {
        instrument,
        seq,
        ts,
        side,
        price,
        qty,
        uid,
    })
}

fn parse_numeric(value: &Value) -> Option<f64> {
    if let Some(v) = value.as_f64() {
        return Some(v);
    }
    value.as_str()?.parse::<f64>().ok()
}

#[cfg(test)]
mod tests {
    use super::{parse_numeric, parse_trade};
    use serde_json::json;

    #[test]
    fn parse_trade_from_snapshot_entry() {
        let raw = json!({
            "product_id":"PI_XBTUSD",
            "seq": 123,
            "time": 1771377651769i64,
            "side":"buy",
            "uid":"abc",
            "qty":"9.0",
            "price":"67153.0"
        });
        let trade = parse_trade(&raw).expect("trade must parse");
        assert_eq!(trade.instrument, "PI_XBTUSD");
        assert_eq!(trade.seq, 123);
        assert_eq!(trade.qty, 9.0);
    }

    #[test]
    fn parse_numeric_handles_strings_and_numbers() {
        assert_eq!(parse_numeric(&json!("1.23")), Some(1.23));
        assert_eq!(parse_numeric(&json!(1.23)), Some(1.23));
    }
}
