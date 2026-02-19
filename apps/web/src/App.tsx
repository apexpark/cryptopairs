import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useEffect, useMemo, useState } from "react";
import LineChart from "./components/LineChart";
import {
  alignCandles,
  computeSpreadSeries,
  deriveMarkers,
  simulateHypotheticalEquity,
  timeframeMinutes,
} from "./lib/analytics";
import {
  fetchExecutionDecision,
  fetchIntegrityHistory,
  fetchKillSwitchState,
  fetchReconcile,
  fetchStrategyCostGates,
  fetchStrategyCues,
  fetchStrategyPortfolioPlan,
  queryCandles,
  submitOrderIntent,
} from "./lib/api";
import {
  applyEntryLike,
  applyReduce,
  emptyPosition,
  isAddAllowed,
  isCloseAllowed,
  isEntryAllowed,
  isGateSafe,
  isReduceAllowed,
  isStopConfigured,
} from "./lib/tradeGuards";
import type {
  ChartMarker,
  DirectionHint,
  ExecutionAction,
  IntegrityHistoryResponse,
  KillSwitchState,
  OrderIntentResponse,
  ReconcileResponse,
  SpreadPosition,
  StrategyPairsCostGateResponse,
  StrategyPairsCuesResponse,
  StrategyPairsPortfolioPlanResponse,
  Timeframe,
  TimelineEvent,
  TradeSide,
} from "./types";
import logoDark from "./assets/logo-dark.png";
import logoLight from "./assets/logo-light.png";

type PageId = "trade" | "markets" | "analytics" | "portfolio" | "data-quality" | "settings";

type ThemeMode = "dark" | "light";

type TradeCommand =
  | "long-entry"
  | "short-entry"
  | "add-exposure"
  | "reduce-exposure"
  | "close-spread";

interface SpreadLeg {
  instrument: string;
  side: TradeSide;
}

const NAV_ITEMS: Array<{ id: PageId; label: string }> = [
  { id: "trade", label: "Trade" },
  { id: "markets", label: "Markets" },
  { id: "analytics", label: "Analytics" },
  { id: "portfolio", label: "Portfolio" },
  { id: "data-quality", label: "Data Quality" },
  { id: "settings", label: "Settings" },
];

const TIMEFRAMES: Timeframe[] = ["1m", "15m", "1h"];

function analyticsRefreshMs(timeframe: Timeframe): number {
  if (timeframe === "1m") {
    return 15_000;
  }
  if (timeframe === "15m") {
    return 45_000;
  }
  return 90_000;
}

function usePersistentState<T>(key: string, fallback: T): [T, (updater: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) {
        return fallback;
      }
      return JSON.parse(raw) as T;
    } catch {
      return fallback;
    }
  });

  const update = (updater: T | ((prev: T) => T)) => {
    setState((prev) => {
      const next = typeof updater === "function" ? (updater as (prev: T) => T)(prev) : updater;
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // best effort persistence
      }
      return next;
    });
  };

  return [state, update];
}

function preferredTheme(): ThemeMode {
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

function formatSigned(value: number, digits = 2): string {
  const abs = Math.abs(value).toFixed(digits);
  return `${value >= 0 ? "+" : "-"}${abs}`;
}

function toneFromStatus(status?: string): "ok" | "warn" | "bad" {
  if (status === "COMPLETE" || status === "OK") {
    return "ok";
  }
  if (status === "PARTIAL_BACKFILLED" || status === "STALE") {
    return "warn";
  }
  return "bad";
}

function buildSpreadLegs(
  leftInstrument: string,
  rightInstrument: string,
  direction: Exclude<DirectionHint, "NONE">,
  action: ExecutionAction
): SpreadLeg[] {
  const isEntry = action === "ENTRY";
  if (direction === "LONG_SPREAD") {
    return [
      { instrument: leftInstrument, side: isEntry ? "BUY" : "SELL" },
      { instrument: rightInstrument, side: isEntry ? "SELL" : "BUY" },
    ];
  }
  return [
    { instrument: leftInstrument, side: isEntry ? "SELL" : "BUY" },
    { instrument: rightInstrument, side: isEntry ? "BUY" : "SELL" },
  ];
}

function nowIso(): string {
  return new Date().toISOString();
}

function App(): JSX.Element {
  const [theme, setTheme] = usePersistentState<ThemeMode>("cp.theme", preferredTheme());
  const [page, setPage] = useState<PageId>("trade");
  const [timeframe, setTimeframe] = usePersistentState<Timeframe>("cp.timeframe", "1m");

  const [exchange, setExchange] = usePersistentState<string>("cp.exchange", "kraken_futures");
  const [accountId, setAccountId] = usePersistentState<string>("cp.account_id", "primary");
  const [operatorId, setOperatorId] = usePersistentState<string>("cp.operator", "operator-kevin");
  const [apiKey, setApiKey] = useState<string>("");
  const [apiSecret, setApiSecret] = useState<string>("");
  const [apiPassphrase, setApiPassphrase] = useState<string>("");
  const [showApiSecrets, setShowApiSecrets] = useState<boolean>(false);

  const [cuesResponse, setCuesResponse] = useState<StrategyPairsCuesResponse | null>(null);
  const [costResponse, setCostResponse] = useState<StrategyPairsCostGateResponse | null>(null);
  const [planResponse, setPlanResponse] = useState<StrategyPairsPortfolioPlanResponse | null>(null);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [coreLoading, setCoreLoading] = useState(false);

  const [selectedPairId, setSelectedPairId] = usePersistentState<string>("cp.pair", "");

  const [killSwitch, setKillSwitch] = useState<KillSwitchState | null>(null);
  const [leftDecisionAllowed, setLeftDecisionAllowed] = useState<boolean>(false);
  const [rightDecisionAllowed, setRightDecisionAllowed] = useState<boolean>(false);
  const [reconcileResponse, setReconcileResponse] = useState<ReconcileResponse | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);

  const [leftIntegrity, setLeftIntegrity] = useState<IntegrityHistoryResponse | null>(null);
  const [rightIntegrity, setRightIntegrity] = useState<IntegrityHistoryResponse | null>(null);

  const [zSeries, setZSeries] = useState<number[]>([]);
  const [equitySeries, setEquitySeries] = useState<number[]>([]);
  const [zMarkers, setZMarkers] = useState<ChartMarker[]>([]);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  const [stopMethod, setStopMethod] = useState<"Z-Score" | "Dollar" | "Percent">("Z-Score");
  const [stopValue, setStopValue] = useState<string>("3.2");
  const [altStop, setAltStop] = useState<string>("150");
  const [spreadSize, setSpreadSize] = useState<string>("1.25");
  const [operatorConfirmed, setOperatorConfirmed] = useState<boolean>(false);
  const [tradeMessage, setTradeMessage] = useState<string>("No trade submitted yet.");
  const [submitting, setSubmitting] = useState(false);

  const [positions, setPositions] = usePersistentState<Record<string, SpreadPosition>>(
    "cp.positions",
    {}
  );
  const [timelineByPair, setTimelineByPair] = usePersistentState<Record<string, TimelineEvent[]>>(
    "cp.timeline",
    {}
  );

  const selectedCueRow = useMemo(() => {
    if (!cuesResponse?.cues.length) {
      return null;
    }
    return (
      cuesResponse.cues.find((entry) => entry.cue.pair_id === selectedPairId) ?? cuesResponse.cues[0]
    );
  }, [cuesResponse, selectedPairId]);

  useEffect(() => {
    if (selectedCueRow && selectedPairId !== selectedCueRow.cue.pair_id) {
      setSelectedPairId(selectedCueRow.cue.pair_id);
    }
  }, [selectedCueRow, selectedPairId, setSelectedPairId]);

  const currentPairId = selectedCueRow?.cue.pair_id ?? "";
  const currentPosition =
    (currentPairId ? positions[currentPairId] : undefined) ?? emptyPosition(nowIso());
  const currentTimeline = timelineByPair[currentPairId] ?? [];

  const stopValueNumber = Number.parseFloat(stopValue);
  const spreadSizeNumber = Number.parseFloat(spreadSize);

  const stopConfigured = isStopConfigured(stopMethod, stopValueNumber);
  const gateState = useMemo(
    () => ({
      killSwitchActive: killSwitch?.active ?? true,
      leftAllowed: leftDecisionAllowed,
      rightAllowed: rightDecisionAllowed,
      reconcileOk: reconcileResponse?.reconcile?.status === "OK",
    }),
    [killSwitch?.active, leftDecisionAllowed, rightDecisionAllowed, reconcileResponse]
  );

  const baseEntryGuard = {
    stopConfigured,
    operatorConfirmed,
    operatorId,
    spreadSize: spreadSizeNumber,
    gateState,
  };

  const canLongEntry = isEntryAllowed(baseEntryGuard);
  const canShortEntry = isEntryAllowed(baseEntryGuard);
  const canAddExposure = isAddAllowed(currentPosition, baseEntryGuard);
  const canReduceExposure = isReduceAllowed(
    currentPosition,
    operatorConfirmed,
    operatorId,
    spreadSizeNumber
  );
  const canCloseSpread = isCloseAllowed(currentPosition);

  const gateSafe = isGateSafe(gateState);

  useEffect(() => {
    let cancelled = false;
    setCoreLoading(true);
    setCoreError(null);

    Promise.all([
      fetchStrategyCues(timeframe, 20),
      fetchStrategyCostGates(timeframe),
      fetchStrategyPortfolioPlan(timeframe),
    ])
      .then(([cues, costs, plan]) => {
        if (cancelled) {
          return;
        }
        setCuesResponse(cues);
        setCostResponse(costs);
        setPlanResponse(plan);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setCoreError(
          `Unable to load strategy data from live services: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
        setCuesResponse(null);
        setCostResponse(null);
        setPlanResponse(null);
      })
      .finally(() => {
        if (!cancelled) {
          setCoreLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [timeframe]);

  useEffect(() => {
    if (!selectedCueRow) {
      return;
    }

    let cancelled = false;
    setGateError(null);

    Promise.all([
      fetchKillSwitchState(),
      fetchExecutionDecision(selectedCueRow.cue.left_instrument, timeframe),
      fetchExecutionDecision(selectedCueRow.cue.right_instrument, timeframe),
      fetchReconcile(exchange, accountId),
    ])
      .then(([kill, left, right, reconcile]) => {
        if (cancelled) {
          return;
        }
        setKillSwitch(kill);
        setLeftDecisionAllowed(left.decision === "ALLOWED");
        setRightDecisionAllowed(right.decision === "ALLOWED");
        setReconcileResponse(reconcile);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setGateError(
          `Gate state unavailable. UI is fail-closed: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
        setKillSwitch({ active: true, reason: "unknown", updated_at: nowIso() });
        setLeftDecisionAllowed(false);
        setRightDecisionAllowed(false);
        setReconcileResponse({ reconcile: null });
      });

    return () => {
      cancelled = true;
    };
  }, [selectedCueRow, timeframe, exchange, accountId]);

  useEffect(() => {
    if (!selectedCueRow) {
      return;
    }

    let cancelled = false;
    Promise.all([
      fetchIntegrityHistory(selectedCueRow.cue.left_instrument, timeframe, 50),
      fetchIntegrityHistory(selectedCueRow.cue.right_instrument, timeframe, 50),
    ])
      .then(([left, right]) => {
        if (cancelled) {
          return;
        }
        setLeftIntegrity(left);
        setRightIntegrity(right);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setLeftIntegrity(null);
        setRightIntegrity(null);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedCueRow, timeframe]);

  useEffect(() => {
    if (!selectedCueRow) {
      setZSeries([]);
      setEquitySeries([]);
      setZMarkers([]);
      setAnalyticsError("No pair selected.");
      setAnalyticsLoading(false);
      return;
    }

    let cancelled = false;
    let inFlight = false;
    setAnalyticsLoading(true);

    const runAnalyticsRefresh = async (firstLoad = false): Promise<void> => {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      if (firstLoad) {
        setAnalyticsLoading(true);
      }

      const minutes = timeframeMinutes(timeframe);
      const bars = timeframe === "1m" ? 300 : timeframe === "15m" ? 280 : 220;
      const end = new Date();
      const start = new Date(end.getTime() - bars * minutes * 60_000);

      try {
        const [left, right] = await Promise.all([
          queryCandles(
            selectedCueRow.cue.left_instrument,
            timeframe,
            start.toISOString(),
            end.toISOString()
          ),
          queryCandles(
            selectedCueRow.cue.right_instrument,
            timeframe,
            start.toISOString(),
            end.toISOString()
          ),
        ]);

        if (cancelled) {
          return;
        }

        const aligned = alignCandles(left.candles, right.candles);
        const spreadSeries = computeSpreadSeries(aligned, selectedCueRow.hedge_ratio);

        if (spreadSeries.length < 20) {
          setAnalyticsError("Insufficient live candle overlap for analytics charts.");
          setZSeries([]);
          setEquitySeries([]);
          setZMarkers([]);
          return;
        }

        const zValues = spreadSeries.map((point) => point.z);
        const markers = deriveMarkers(
          spreadSeries,
          selectedCueRow.cue.entry_band,
          selectedCueRow.cue.exit_band,
          selectedCueRow.cue.stop_band
        );
        const equity = simulateHypotheticalEquity(
          spreadSeries,
          selectedCueRow.cue.entry_band,
          selectedCueRow.cue.exit_band,
          selectedCueRow.cue.stop_band,
          selectedCueRow.cue.cost_estimate_bps
        );

        setZSeries(zValues);
        setZMarkers(markers);
        setEquitySeries(equity);
        setAnalyticsError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setAnalyticsError(
          `Analytics unavailable from live data query: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
      } finally {
        if (!cancelled && firstLoad) {
          setAnalyticsLoading(false);
        }
        inFlight = false;
      }
    };

    void runAnalyticsRefresh(true);
    const refreshIntervalId = window.setInterval(() => {
      void runAnalyticsRefresh(false);
    }, analyticsRefreshMs(timeframe));

    return () => {
      cancelled = true;
      window.clearInterval(refreshIntervalId);
    };
  }, [selectedCueRow, timeframe]);

  const addTimelineEvent = (pairId: string, event: TimelineEvent): void => {
    setTimelineByPair((prev) => {
      const current = prev[pairId] ?? [];
      return {
        ...prev,
        [pairId]: [event, ...current].slice(0, 40),
      };
    });
  };

  const updatePosition = (
    pairId: string,
    updater: (position: SpreadPosition) => SpreadPosition
  ): void => {
    setPositions((prev) => {
      const current = prev[pairId] ?? emptyPosition(nowIso());
      return {
        ...prev,
        [pairId]: updater(current),
      };
    });
  };

  const executeTradeCommand = async (command: TradeCommand): Promise<void> => {
    if (!selectedCueRow) {
      setTradeMessage("No selected pair.");
      return;
    }

    const now = nowIso();
    const pairId = selectedCueRow.cue.pair_id;
    const current = positions[pairId] ?? emptyPosition(now);
    const currentZ = selectedCueRow.cue.spread_z;

    let direction: Exclude<DirectionHint, "NONE">;
    let action: ExecutionAction;
    let qty = spreadSizeNumber;

    if (!Number.isFinite(spreadSizeNumber) || spreadSizeNumber <= 0) {
      setTradeMessage("Spread size must be > 0.");
      return;
    }

    if (command === "long-entry") {
      direction = "LONG_SPREAD";
      action = "ENTRY";
    } else if (command === "short-entry") {
      direction = "SHORT_SPREAD";
      action = "ENTRY";
    } else if (command === "add-exposure") {
      if (current.direction === "NONE") {
        setTradeMessage("No open spread to add exposure to.");
        return;
      }
      direction = current.direction;
      action = "ENTRY";
    } else if (command === "reduce-exposure") {
      if (current.direction === "NONE" || current.totalSize <= 0) {
        setTradeMessage("No open spread to reduce.");
        return;
      }
      direction = current.direction;
      action = "EXIT";
      qty = Math.min(spreadSizeNumber, current.totalSize);
    } else {
      if (current.direction === "NONE" || current.totalSize <= 0) {
        setTradeMessage("No open spread to close.");
        return;
      }
      direction = current.direction;
      action = "EMERGENCY_STOP_CLOSE";
      qty = current.totalSize;
    }

    const legs = buildSpreadLegs(
      selectedCueRow.cue.left_instrument,
      selectedCueRow.cue.right_instrument,
      direction,
      action
    );

    setSubmitting(true);
    try {
      const responses = await Promise.all(
        legs.map((leg, index) =>
          submitOrderIntent({
            idempotency_key: `${Date.now()}-${pairId}-${command}-${leg.instrument}-${index}`,
            exchange,
            account_id: accountId,
            instrument: leg.instrument,
            timeframe,
            action,
            side: leg.side,
            qty,
            operator_confirmed: action === "EMERGENCY_STOP_CLOSE" ? false : operatorConfirmed,
            operator_id: action === "EMERGENCY_STOP_CLOSE" ? null : operatorId,
            min_coverage_pct: 99.5,
          })
        )
      );

      const accepted = responses.every((response) => response.decision === "ACCEPTED");
      const reason = responses
        .map((response) => response.reason)
        .filter((value): value is string => !!value)
        .join(" | ");

      const summaryTone: TimelineEvent["tone"] = accepted ? "ok" : "bad";
      addTimelineEvent(pairId, {
        ts: now,
        text: `${command.toUpperCase()} ${accepted ? "approved" : "blocked"}${
          reason ? ` (${reason})` : ""
        }`,
        tone: summaryTone,
      });

      if (accepted) {
        updatePosition(pairId, (position) => {
          if (command === "long-entry") {
            return applyEntryLike(position, "LONG_SPREAD", qty, currentZ, now);
          }
          if (command === "short-entry") {
            return applyEntryLike(position, "SHORT_SPREAD", qty, currentZ, now);
          }
          if (command === "add-exposure") {
            return applyEntryLike(position, direction, qty, currentZ, now);
          }
          if (command === "reduce-exposure") {
            return applyReduce(position, qty, now);
          }
          return emptyPosition(now);
        });
      }

      const legsText = responses
        .map((response) => `${response.instrument}: ${response.decision}`)
        .join(" | ");
      setTradeMessage(
        `${accepted ? "Spread action accepted" : "Spread action blocked"}. ${legsText}${
          reason ? ` | ${reason}` : ""
        }`
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addTimelineEvent(pairId, {
        ts: now,
        text: `SUBMIT ERROR (${message})`,
        tone: "bad",
      });
      setTradeMessage(`Submission error: ${message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const logoSrc = theme === "dark" ? logoDark : logoLight;
  const pageLabel = NAV_ITEMS.find((item) => item.id === page)?.label ?? "Trade";

  const content = (() => {
    if (page === "trade") {
      return (
        <TradePage
          cues={cuesResponse}
          selectedPairId={currentPairId}
          onSelectPair={setSelectedPairId}
          zSeries={zSeries}
          zMarkers={zMarkers}
          analyticsError={analyticsError}
          currentPosition={currentPosition}
          timeline={currentTimeline}
          stopMethod={stopMethod}
          stopValue={stopValue}
          altStop={altStop}
          spreadSize={spreadSize}
          operatorConfirmed={operatorConfirmed}
          operatorId={operatorId}
          setStopMethod={setStopMethod}
          setStopValue={setStopValue}
          setAltStop={setAltStop}
          setSpreadSize={setSpreadSize}
          setOperatorConfirmed={setOperatorConfirmed}
          setOperatorId={setOperatorId}
          stopConfigured={stopConfigured}
          canLongEntry={canLongEntry}
          canShortEntry={canShortEntry}
          canAddExposure={canAddExposure}
          canReduceExposure={canReduceExposure}
          canCloseSpread={canCloseSpread}
          gateState={gateState}
          killSwitch={killSwitch}
          reconcile={reconcileResponse?.reconcile ?? null}
          gateError={gateError}
          tradeMessage={tradeMessage}
          submitting={submitting}
          onCommand={executeTradeCommand}
        />
      );
    }

    if (page === "markets") {
      return (
        <MarketsPage
          cues={cuesResponse}
          costs={costResponse}
          loading={coreLoading}
          error={coreError}
        />
      );
    }

    if (page === "analytics") {
      return (
        <AnalyticsPage
          cues={cuesResponse}
          selectedPairId={currentPairId}
          onSelectPair={setSelectedPairId}
          zSeries={zSeries}
          zMarkers={zMarkers}
          equitySeries={equitySeries}
          loading={analyticsLoading}
          error={analyticsError}
        />
      );
    }

    if (page === "portfolio") {
      return (
        <PortfolioPage
          plan={planResponse}
          positions={positions}
          selectedPairId={currentPairId}
          onSelectPair={setSelectedPairId}
        />
      );
    }

    if (page === "data-quality") {
      return (
        <DataQualityPage
          selected={selectedCueRow}
          left={leftIntegrity}
          right={rightIntegrity}
          gateState={gateState}
        />
      );
    }

    return (
      <SettingsPage
        theme={theme}
        setTheme={setTheme}
        exchange={exchange}
        accountId={accountId}
        operatorId={operatorId}
        apiKey={apiKey}
        apiSecret={apiSecret}
        apiPassphrase={apiPassphrase}
        showApiSecrets={showApiSecrets}
        setExchange={setExchange}
        setAccountId={setAccountId}
        setOperatorId={setOperatorId}
        setApiKey={setApiKey}
        setApiSecret={setApiSecret}
        setApiPassphrase={setApiPassphrase}
        setShowApiSecrets={setShowApiSecrets}
        timeframe={timeframe}
      />
    );
  })();

  return (
    <div className={`app ${theme}`}>
      <header className="topbar">
        <div className="topbar-left">
          <img src={logoSrc} alt="Pairs logo" className="brand-logo" />
          <h1>{pageLabel}</h1>
        </div>

        <div className="metrics-row">
          <Metric label="Mark" value="28.50" />
          <Metric label="Index" value="28.53" />
          <Metric label="24h" value="-2.81%" tone="bad" />
          <Metric label="Funding" value="-0.0040% / hr" />
          <Metric label="OI" value="69.6k" />
        </div>

        <div className="topbar-right">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button type="button" className="timeframe-button">
                Timeframe: {timeframe}
                <span className="caret">▾</span>
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content sideOffset={8} className="dropdown-content">
              {TIMEFRAMES.map((value) => (
                <DropdownMenu.Item
                  key={value}
                  className={`dropdown-item ${timeframe === value ? "selected" : ""}`}
                  onSelect={() => setTimeframe(value)}
                >
                  {value}
                  {timeframe === value ? <span className="check">✓</span> : null}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>
      </header>

      <div className="app-body">
        <aside className="side-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`side-nav-item ${page === item.id ? "active" : ""}`}
              onClick={() => setPage(item.id)}
            >
              {item.label}
            </button>
          ))}
        </aside>

        <section className="content-shell">{content}</section>
      </div>

      <footer className="footer-note">
        <span>Global timeframe selector applies to all pages and strategy panels.</span>
        <span className={gateSafe ? "tone-ok" : "tone-bad"}>
          {gateSafe
            ? "Trade gates healthy"
            : "Fail-closed mode: entry actions blocked until all gates are safe"}
        </span>
      </footer>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}): JSX.Element {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className={`metric-value tone-${tone}`}>{value}</div>
    </div>
  );
}

function SectionCard({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={`panel-card ${className ?? ""}`.trim()}>
      <h2>{title}</h2>
      {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
      {children}
    </section>
  );
}

function TradePage(props: {
  cues: StrategyPairsCuesResponse | null;
  selectedPairId: string;
  onSelectPair: (pairId: string) => void;
  zSeries: number[];
  zMarkers: ChartMarker[];
  analyticsError: string | null;
  currentPosition: SpreadPosition;
  timeline: TimelineEvent[];
  stopMethod: "Z-Score" | "Dollar" | "Percent";
  stopValue: string;
  altStop: string;
  spreadSize: string;
  operatorConfirmed: boolean;
  operatorId: string;
  setStopMethod: (value: "Z-Score" | "Dollar" | "Percent") => void;
  setStopValue: (value: string) => void;
  setAltStop: (value: string) => void;
  setSpreadSize: (value: string) => void;
  setOperatorConfirmed: (value: boolean) => void;
  setOperatorId: (value: string) => void;
  stopConfigured: boolean;
  canLongEntry: boolean;
  canShortEntry: boolean;
  canAddExposure: boolean;
  canReduceExposure: boolean;
  canCloseSpread: boolean;
  gateState: { killSwitchActive: boolean; leftAllowed: boolean; rightAllowed: boolean; reconcileOk: boolean };
  killSwitch: KillSwitchState | null;
  reconcile: ReconcileResponse["reconcile"];
  gateError: string | null;
  tradeMessage: string;
  submitting: boolean;
  onCommand: (command: TradeCommand) => Promise<void>;
}): JSX.Element {
  const selectedCue =
    props.cues?.cues.find((entry) => entry.cue.pair_id === props.selectedPairId) ??
    props.cues?.cues[0] ??
    null;

  const execute = (command: TradeCommand) => {
    void props.onCommand(command);
  };

  return (
    <div className="trade-grid">
      <SectionCard
        title="Opportunities"
        subtitle="Pairs scanner: z-score | edge | gate"
        className="opportunities-panel"
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Z</th>
                <th>Edge</th>
                <th>Gate</th>
              </tr>
            </thead>
            <tbody>
              {props.cues?.cues.map((entry) => (
                <tr
                  key={entry.cue.pair_id}
                  className={entry.cue.pair_id === props.selectedPairId ? "selected-row" : ""}
                  onClick={() => props.onSelectPair(entry.cue.pair_id)}
                >
                  <td>{entry.cue.pair_id.replace("PI_", "").replaceAll("__", "/")}</td>
                  <td>{entry.cue.spread_z.toFixed(2)}</td>
                  <td>{formatSigned(entry.cue.cost_gate.net_edge_bps)}bp</td>
                  <td className={entry.cue.cost_gate.pass ? "tone-ok" : "tone-bad"}>
                    {entry.cue.cost_gate.pass ? "PASS" : "BLOCK"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mini-card">
          <h3>Open spread summary</h3>
          <p>
            Direction: <span className="tone-info">{props.currentPosition.direction}</span>
          </p>
          <p>Total size: {props.currentPosition.totalSize.toFixed(2)} spread units</p>
          <p>Avg entry z-score: {props.currentPosition.avgEntryZ.toFixed(2)}</p>
          <p>Updated: {new Date(props.currentPosition.updatedAt).toLocaleTimeString()}</p>
        </div>
      </SectionCard>

      <SectionCard
        title="Analysis"
        subtitle="Spread z-score chart and rationale"
        className="analysis-panel"
      >
        <LineChart
          values={props.zSeries}
          markers={props.zMarkers}
          thresholds={
            selectedCue
              ? [
                  { value: 0, tone: "info" },
                  { value: selectedCue.cue.entry_band, tone: "warn" },
                  { value: -selectedCue.cue.entry_band, tone: "warn" },
                  { value: selectedCue.cue.stop_band, tone: "bad" },
                  { value: -selectedCue.cue.stop_band, tone: "bad" },
                ]
              : []
          }
          title="Live spread z-score (entry / mean / stop)"
          unavailableText={props.analyticsError ?? "No live z-score data"}
          height={246}
        />

        <div className="chip-row">
          {selectedCue?.cue.rationale_codes.length ? (
            selectedCue.cue.rationale_codes.map((code) => (
              <span key={code} className="chip">
                {code}
              </span>
            ))
          ) : (
            <>
              <span className="chip tone-ok">COINT PASS</span>
              <span className="chip tone-info">HALF-LIFE OK</span>
              <span className="chip tone-ok">COST PASS</span>
              <span className="chip tone-warn">REGIME {selectedCue?.cue.regime ?? "N/A"}</span>
            </>
          )}
        </div>

        <div className="timeline-card">
          <h3>Intent timeline</h3>
          {props.timeline.length ? (
            props.timeline.map((event, index) => (
              <p key={`${event.ts}-${index}`} className={`tone-${event.tone}`}>
                {new Date(event.ts).toLocaleTimeString()} {event.text}
              </p>
            ))
          ) : (
            <p className="empty-text">No live intent events yet.</p>
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Spread Execution"
        subtitle="Stop is prerequisite for entry actions"
        className="execution-panel"
      >
        <div className="execution-grid">
          <div className="execution-block stop-block">
            <h3>1) Stop Configuration (Required)</h3>
            <label>
              Method
              <select
                value={props.stopMethod}
                onChange={(event) =>
                  props.setStopMethod(event.target.value as "Z-Score" | "Dollar" | "Percent")
                }
              >
                <option value="Z-Score">Z-Score</option>
                <option value="Dollar">Dollar</option>
                <option value="Percent">Percent</option>
              </select>
            </label>
            <label>
              Value
              <input
                type="number"
                step="0.01"
                min="0"
                value={props.stopValue}
                onChange={(event) => props.setStopValue(event.target.value)}
              />
            </label>
            <label>
              Alt stop
              <input
                type="number"
                step="0.01"
                min="0"
                value={props.altStop}
                onChange={(event) => props.setAltStop(event.target.value)}
              />
            </label>
            <div className={`status-pill ${props.stopConfigured ? "ok" : "bad"}`}>
              Stop ready: {props.stopConfigured ? "yes" : "no"}
            </div>
          </div>

          <div className="execution-block entry-block">
            <h3>2) Entry / Add Exposure</h3>
            <label>
              Spread size (units)
              <input
                type="number"
                step="0.01"
                min="0"
                value={props.spreadSize}
                onChange={(event) => props.setSpreadSize(event.target.value)}
              />
            </label>
            <label>
              Operator ID
              <input
                type="text"
                value={props.operatorId}
                onChange={(event) => props.setOperatorId(event.target.value)}
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={props.operatorConfirmed}
                onChange={(event) => props.setOperatorConfirmed(event.target.checked)}
              />
              Live Trading Armed
            </label>

            <button disabled={!props.canLongEntry || props.submitting} onClick={() => execute("long-entry")}>
              Long Spread Entry
            </button>
            <button
              className="danger"
              disabled={!props.canShortEntry || props.submitting}
              onClick={() => execute("short-entry")}
            >
              Short Spread Entry
            </button>
            <button disabled={!props.canAddExposure || props.submitting} onClick={() => execute("add-exposure")}>
              Add Exposure to Open Spread
            </button>
          </div>

          <div className="execution-block reduce-block">
            <h3>3) Reduce / Close</h3>
            <button disabled={!props.canReduceExposure || props.submitting} onClick={() => execute("reduce-exposure")}>
              Reduce Exposure (partial)
            </button>
            <button
              className="danger"
              disabled={!props.canCloseSpread || props.submitting}
              onClick={() => execute("close-spread")}
            >
              Close Spread (all open in pair)
            </button>
          </div>

          <div className="execution-status-block">
            <div className="gate-grid">
              <div className={`status-pill ${props.gateState.killSwitchActive ? "bad" : "ok"}`}>
                Kill switch: {props.gateState.killSwitchActive ? "ACTIVE" : "OFF"}
              </div>
              <div className={`status-pill ${props.gateState.leftAllowed ? "ok" : "bad"}`}>
                Left integrity gate: {props.gateState.leftAllowed ? "ALLOWED" : "BLOCKED"}
              </div>
              <div className={`status-pill ${props.gateState.rightAllowed ? "ok" : "bad"}`}>
                Right integrity gate: {props.gateState.rightAllowed ? "ALLOWED" : "BLOCKED"}
              </div>
              <div className={`status-pill ${props.gateState.reconcileOk ? "ok" : "bad"}`}>
                Reconcile gate: {props.gateState.reconcileOk ? "OK" : "NOT_OK"}
              </div>
            </div>

            <div className="message-box">
              <strong>Result:</strong> {props.tradeMessage}
              {props.killSwitch ? (
                <div className="small-text">Kill switch reason: {props.killSwitch.reason}</div>
              ) : null}
              {props.reconcile ? (
                <div className="small-text">
                  Reconcile status: {props.reconcile.status} (drift {props.reconcile.drift_notional.toFixed(2)})
                </div>
              ) : null}
              {props.gateError ? <div className="tone-bad small-text">{props.gateError}</div> : null}
            </div>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}

function MarketsPage({
  cues,
  costs,
  loading,
  error,
}: {
  cues: StrategyPairsCuesResponse | null;
  costs: StrategyPairsCostGateResponse | null;
  loading: boolean;
  error: string | null;
}): JSX.Element {
  return (
    <div className="split-grid">
      <SectionCard title="Markets" subtitle="Live strategy candidate overview">
        {loading ? <p>Loading live data...</p> : null}
        {error ? <p className="tone-bad">{error}</p> : null}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Regime</th>
                <th>Score</th>
                <th>Actionable</th>
              </tr>
            </thead>
            <tbody>
              {cues?.cues.map((entry) => (
                <tr key={entry.cue.pair_id}>
                  <td>{entry.cue.pair_id.replaceAll("PI_", "")}</td>
                  <td>{entry.cue.regime}</td>
                  <td>{entry.cue.opportunity_score.toFixed(2)}</td>
                  <td className={entry.cue.actionable ? "tone-ok" : "tone-warn"}>
                    {entry.cue.actionable ? "YES" : "NO"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard title="Cost Gates" subtitle="Live edge versus cost diagnostics">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Net Edge</th>
                <th>Pass</th>
              </tr>
            </thead>
            <tbody>
              {costs?.gates.map((gate) => (
                <tr key={gate.pair_id}>
                  <td>{gate.pair_id.replaceAll("PI_", "")}</td>
                  <td>{formatSigned(gate.net_edge_bps)}bp</td>
                  <td className={gate.pass ? "tone-ok" : "tone-bad"}>{gate.pass ? "PASS" : "BLOCK"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

function AnalyticsPage({
  cues,
  selectedPairId,
  onSelectPair,
  zSeries,
  zMarkers,
  equitySeries,
  loading,
  error,
}: {
  cues: StrategyPairsCuesResponse | null;
  selectedPairId: string;
  onSelectPair: (value: string) => void;
  zSeries: number[];
  zMarkers: ChartMarker[];
  equitySeries: number[];
  loading: boolean;
  error: string | null;
}): JSX.Element {
  const selected = cues?.cues.find((entry) => entry.cue.pair_id === selectedPairId) ?? cues?.cues[0];

  return (
    <div className="analytics-layout">
      <div className="analytics-left-stack">
        <SectionCard title="Strategy Metrics" subtitle="Optimal strategy summary">
          {selected ? (
            <>
              <StatRow label="Opportunity Score" value={selected.cue.opportunity_score.toFixed(2)} />
              <StatRow label="Expected Hold Bars" value={selected.cue.expected_hold_bars.toString()} />
              <StatRow label="Cost Estimate" value={`${selected.cue.cost_estimate_bps.toFixed(2)} bp`} />
              <StatRow label="Confidence" value={selected.cue.confidence_band} />
              <StatRow
                label="Shadow ML Precision"
                value={selected.cue.shadow_ml.precision.toFixed(2)}
                tone="ok"
              />
            </>
          ) : (
            <p className="empty-text">No live cues available.</p>
          )}

          <label>
            Pair
            <select
              value={selected?.cue.pair_id ?? ""}
              onChange={(event) => onSelectPair(event.target.value)}
            >
              {cues?.cues.map((entry) => (
                <option key={entry.cue.pair_id} value={entry.cue.pair_id}>
                  {entry.cue.pair_id.replaceAll("PI_", "")}
                </option>
              ))}
            </select>
          </label>
        </SectionCard>

        <SectionCard title="Diagnostics" subtitle="Reoptimize and shadow model status">
          {selected ? (
            <>
              <StatRow label="Champion Variant" value={selected.cue.selected_variant} />
              <StatRow
                label="Shadow Agreement"
                value={selected.cue.shadow_ml.agrees_with_selected ? "YES" : "NO"}
                tone={selected.cue.shadow_ml.agrees_with_selected ? "ok" : "warn"}
              />
              <StatRow
                label="Cost Gate"
                value={selected.cue.cost_gate.pass ? "PASS" : "BLOCK"}
                tone={selected.cue.cost_gate.pass ? "ok" : "bad"}
              />
            </>
          ) : (
            <p className="empty-text">No diagnostics available.</p>
          )}
        </SectionCard>
      </div>

      <div className="analytics-chart-split">
        <SectionCard
          title="Hypothetical Equity Curve"
          subtitle="Derived from live candles and current strategy bands"
        >
          <LineChart
            values={equitySeries}
            height={360}
            title="Hypothetical equity (net of estimated costs)"
            unavailableText={loading ? "Loading live candles..." : error ?? "No data"}
          />
        </SectionCard>

        <SectionCard
          title="Historical Z-Score (Entries / Exits / Stops)"
          subtitle="Derived from live spread history"
        >
          <LineChart
            values={zSeries}
            markers={zMarkers}
            thresholds={
              selected
                ? [
                    { value: 0, tone: "info" },
                    { value: selected.cue.entry_band, tone: "warn" },
                    { value: -selected.cue.entry_band, tone: "warn" },
                    { value: selected.cue.stop_band, tone: "bad" },
                    { value: -selected.cue.stop_band, tone: "bad" },
                  ]
                : []
            }
            height={360}
            title="Entry=green, Exit=amber, Stop=red"
            unavailableText={loading ? "Loading live candles..." : error ?? "No data"}
          />
        </SectionCard>
      </div>
    </div>
  );
}

function PortfolioPage({
  plan,
  positions,
  selectedPairId,
  onSelectPair,
}: {
  plan: StrategyPairsPortfolioPlanResponse | null;
  positions: Record<string, SpreadPosition>;
  selectedPairId: string;
  onSelectPair: (pairId: string) => void;
}): JSX.Element {
  const entries = Object.entries(positions);

  return (
    <div className="split-grid">
      <SectionCard title="Portfolio" subtitle="Live open spread positions (client ledger from accepted intents)">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Direction</th>
                <th>Size</th>
                <th>Avg Z</th>
              </tr>
            </thead>
            <tbody>
              {entries.length ? (
                entries.map(([pairId, position]) => (
                  <tr
                    key={pairId}
                    className={pairId === selectedPairId ? "selected-row" : ""}
                    onClick={() => onSelectPair(pairId)}
                  >
                    <td>{pairId.replaceAll("PI_", "")}</td>
                    <td>{position.direction}</td>
                    <td>{position.totalSize.toFixed(2)}</td>
                    <td>{position.avgEntryZ.toFixed(2)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="empty-text">
                    No accepted spread positions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard title="Portfolio Plan" subtitle="Live strategy advisory weights">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Target Weight</th>
                <th>Risk Contribution</th>
              </tr>
            </thead>
            <tbody>
              {plan?.plan.weights.map((weight) => (
                <tr key={weight.pair_id}>
                  <td>{weight.pair_id.replaceAll("PI_", "")}</td>
                  <td>{weight.target_weight.toFixed(2)}</td>
                  <td>{(weight.risk_contribution * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

function DataQualityPage({
  selected,
  left,
  right,
  gateState,
}: {
  selected: StrategyPairsCuesResponse["cues"][number] | null;
  left: IntegrityHistoryResponse | null;
  right: IntegrityHistoryResponse | null;
  gateState: { killSwitchActive: boolean; leftAllowed: boolean; rightAllowed: boolean; reconcileOk: boolean };
}): JSX.Element {
  return (
    <div className="split-grid">
      <SectionCard title="Data Quality" subtitle="Integrity history from data-service">
        <StatRow
          label="Execution impact"
          value={gateState.leftAllowed && gateState.rightAllowed ? "ENTRY ALLOWED" : "ENTRY BLOCKED"}
          tone={gateState.leftAllowed && gateState.rightAllowed ? "ok" : "bad"}
        />

        <h3>{selected?.cue.left_instrument ?? "Left Instrument"}</h3>
        <IntegrityTable rows={left?.rows ?? []} />

        <h3>{selected?.cue.right_instrument ?? "Right Instrument"}</h3>
        <IntegrityTable rows={right?.rows ?? []} />
      </SectionCard>

      <SectionCard title="Details" subtitle="Backfill and gating context">
        <p>
          Kill switch: <span className={gateState.killSwitchActive ? "tone-bad" : "tone-ok"}>{gateState.killSwitchActive ? "ACTIVE" : "OFF"}</span>
        </p>
        <p>
          Left gate: <span className={gateState.leftAllowed ? "tone-ok" : "tone-bad"}>{gateState.leftAllowed ? "ALLOWED" : "BLOCKED"}</span>
        </p>
        <p>
          Right gate: <span className={gateState.rightAllowed ? "tone-ok" : "tone-bad"}>{gateState.rightAllowed ? "ALLOWED" : "BLOCKED"}</span>
        </p>
        <p>
          Reconcile gate: <span className={gateState.reconcileOk ? "tone-ok" : "tone-bad"}>{gateState.reconcileOk ? "OK" : "NOT_OK"}</span>
        </p>
      </SectionCard>
    </div>
  );
}

function IntegrityTable({
  rows,
}: {
  rows: Array<{
    start_ts: string;
    end_ts: string;
    status: "COMPLETE" | "PARTIAL_BACKFILLED" | "INCOMPLETE" | "STALE" | "FAILED";
    coverage_pct: number;
    reason: string;
    checked_at: string;
  }>;
}): JSX.Element {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Checked</th>
            <th>Status</th>
            <th>Coverage</th>
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.slice(0, 8).map((row) => (
              <tr key={`${row.checked_at}-${row.start_ts}`}>
                <td>{new Date(row.checked_at).toLocaleTimeString()}</td>
                <td className={`tone-${toneFromStatus(row.status)}`}>{row.status}</td>
                <td>{row.coverage_pct.toFixed(2)}%</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={3} className="empty-text">
                No live integrity rows available.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function SettingsPage({
  theme,
  setTheme,
  exchange,
  accountId,
  operatorId,
  apiKey,
  apiSecret,
  apiPassphrase,
  showApiSecrets,
  setExchange,
  setAccountId,
  setOperatorId,
  setApiKey,
  setApiSecret,
  setApiPassphrase,
  setShowApiSecrets,
  timeframe,
}: {
  theme: ThemeMode;
  setTheme: (value: ThemeMode | ((prev: ThemeMode) => ThemeMode)) => void;
  exchange: string;
  accountId: string;
  operatorId: string;
  apiKey: string;
  apiSecret: string;
  apiPassphrase: string;
  showApiSecrets: boolean;
  setExchange: (value: string) => void;
  setAccountId: (value: string) => void;
  setOperatorId: (value: string) => void;
  setApiKey: (value: string) => void;
  setApiSecret: (value: string) => void;
  setApiPassphrase: (value: string) => void;
  setShowApiSecrets: (value: boolean) => void;
  timeframe: Timeframe;
}): JSX.Element {
  return (
    <div className="split-grid">
      <SectionCard title="Settings" subtitle="Manual trading defaults and UI preferences">
        <label>
          Theme
          <select value={theme} onChange={(event) => setTheme(event.target.value as ThemeMode)}>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>

        <label>
          Exchange
          <input value={exchange} onChange={(event) => setExchange(event.target.value)} />
        </label>

        <label>
          Account ID
          <input value={accountId} onChange={(event) => setAccountId(event.target.value)} />
        </label>

        <label>
          Default Operator ID
          <input value={operatorId} onChange={(event) => setOperatorId(event.target.value)} />
        </label>

        <div className="mini-card">
          <h3>Current global timeframe</h3>
          <p>{timeframe}</p>
        </div>
      </SectionCard>

      <SectionCard title="API Credentials" subtitle="Session-only fields for local operator testing">
        <label>
          Kraken API Key
          <input
            type={showApiSecrets ? "text" : "password"}
            autoComplete="off"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="API key"
          />
        </label>

        <label>
          Kraken API Secret
          <input
            type={showApiSecrets ? "text" : "password"}
            autoComplete="off"
            value={apiSecret}
            onChange={(event) => setApiSecret(event.target.value)}
            placeholder="API secret"
          />
        </label>

        <label>
          Kraken API Passphrase
          <input
            type={showApiSecrets ? "text" : "password"}
            autoComplete="off"
            value={apiPassphrase}
            onChange={(event) => setApiPassphrase(event.target.value)}
            placeholder="Optional passphrase"
          />
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={showApiSecrets}
            onChange={(event) => setShowApiSecrets(event.target.checked)}
          />
          Show values in clear text
        </label>

        <button
          type="button"
          className="danger"
          onClick={() => {
            setApiKey("");
            setApiSecret("");
            setApiPassphrase("");
          }}
        >
          Clear Session Keys
        </button>

        <p className="small-text">
          Session only: keys stay in browser memory and are not written to repo files.
        </p>
      </SectionCard>

      <SectionCard title="Safety Defaults" subtitle="Fail-closed behavior">
        <p className="tone-ok">Entry/exit require operator confirmation.</p>
        <p className="tone-ok">Emergency close is available for open spread flattening.</p>
        <p className="tone-ok">If gate state is unavailable, entry buttons remain disabled.</p>
        <p className="small-text">
          Live credentials should remain backend-managed and encrypted at rest.
        </p>
      </SectionCard>
    </div>
  );
}

function StatRow({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}): JSX.Element {
  return (
    <div className="stat-row">
      <div className="stat-label">{label}</div>
      <div className={`stat-value tone-${tone}`}>{value}</div>
    </div>
  );
}

export default App;
