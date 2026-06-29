package adapters.dukascopy;

import com.dukascopy.api.*;
import com.dukascopy.api.IEngine.OrderCommand;

import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * JForex strategy that bridges Dukascopy's trading platform with the Python
 * FastAPI backend running at http://localhost:8000.
 *
 * Lifecycle:
 *   onStart  -> register with backend, load settings
 *   onTick   -> forward tick, poll signals, execute/close orders
 *   onBar    -> forward 5-min bars
 *   onStop   -> close all positions, deregister
 *
 * Safety:
 *   - If backend becomes unreachable, all positions are closed and trading halts.
 *   - Kill switch support via backend setting.
 *   - Maximum one position per currency pair.
 *   - Time-based forced close after max_hold_minutes.
 */
public class DukascopyBridgeStrategy implements IStrategy {

    // ── Configurable parameters (exposed in JForex UI) ──────────────────────

    @Configurable("Backend URL")
    public String backendUrl = "http://localhost:8001";

    @Configurable("Trade amount (lots)")
    public double tradeAmountLots = 0.01;

    @Configurable("Tick forwarding interval (ms)")
    public long tickForwardIntervalMs = 1000;

    @Configurable("Signal poll interval (ms)")
    public long signalPollIntervalMs = 2000;

    @Configurable("Max consecutive backend failures before safety shutdown")
    public int maxBackendFailures = 5;

    // ── JForex API handles ──────────────────────────────────────────────────

    private IEngine engine;
    private IConsole console;
    private IHistory history;
    private IContext context;
    private IAccount account;

    // ── Internal state ──────────────────────────────────────────────────────

    private HttpClient http;
    private volatile boolean tradingEnabled = true;
    private volatile boolean backendConnected = false;
    private int consecutiveBackendFailures = 0;

    /** Open position labels keyed by instrument name, e.g. "EUR/USD" */
    private final ConcurrentHashMap<String, IOrder> openPositions = new ConcurrentHashMap<>();

    /** Timestamps when positions were opened, for time-based stop */
    private final ConcurrentHashMap<String, Long> positionOpenTimes = new ConcurrentHashMap<>();

    /** Instruments we are subscribed to, derived from backend /api/health */
    private final Set<Instrument> subscribedInstruments = new LinkedHashSet<>();

    /** Throttle: last tick forward time per instrument */
    private final ConcurrentHashMap<String, Long> lastTickForwardTime = new ConcurrentHashMap<>();

    /** Throttle: last signal poll time */
    private volatile long lastSignalPollTime = 0;

    /** Cached backend settings */
    private volatile double stopLossPips = 25.0;
    private volatile double takeProfitPips = 40.0;
    private volatile double spreadThresholdPips = 3.0;
    private volatile int maxHoldMinutes = 120;
    private volatile String overrideMode = "NORMAL";

    /** Counter for generating unique order labels */
    private int orderCounter = 0;

    private static final SimpleDateFormat ISO_FORMAT = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'");
    static {
        ISO_FORMAT.setTimeZone(TimeZone.getTimeZone("UTC"));
    }

    // =====================================================================
    //  IStrategy lifecycle
    // =====================================================================

    @Override
    public void onStart(IContext context) throws JFException {
        this.context = context;
        this.engine = context.getEngine();
        this.console = context.getConsole();
        this.history = context.getHistory();
        this.account = context.getAccount();

        log("DukascopyBridgeStrategy starting. Backend: " + backendUrl);

        // Initialise HTTP client
        http = new HttpClient(backendUrl, 5000, 10000);

        // Connect to backend
        if (!connectToBackend()) {
            log("WARNING: Backend not reachable at startup. Will retry on each tick.");
        }

        // Subscribe to instruments reported by backend
        if (subscribedInstruments.isEmpty()) {
            // Default to AUD/USD and NZD/USD if backend was unreachable
            subscribedInstruments.add(Instrument.AUDUSD);
            subscribedInstruments.add(Instrument.NZDUSD);
        }
        Set<Instrument> instrumentSet = new HashSet<>(subscribedInstruments);
        context.setSubscribedInstruments(instrumentSet, true);
        log("Subscribed to instruments: " + subscribedInstruments);

        // Register adapter with backend
        registerWithBackend();

        // Load settings from backend
        refreshSettings();

        // Sync existing open orders from engine
        syncExistingOrders();

        log("DukascopyBridgeStrategy started successfully.");
    }

    @Override
    public void onTick(Instrument instrument, ITick tick) throws JFException {
        if (!subscribedInstruments.contains(instrument)) return;

        String pair = instrumentToPair(instrument);
        long now = System.currentTimeMillis();

        // ── Forward tick data (throttled) ───────────────────────────────────
        Long lastForward = lastTickForwardTime.get(pair);
        if (lastForward == null || (now - lastForward) >= tickForwardIntervalMs) {
            lastTickForwardTime.put(pair, now);
            forwardTick(pair, tick);
        }

        // ── Poll signals and act (throttled) ────────────────────────────────
        if ((now - lastSignalPollTime) >= signalPollIntervalMs) {
            lastSignalPollTime = now;

            // Check backend health
            if (!checkBackendHealth()) return;

            // Refresh settings periodically (every 30 signal polls ~ 60s at 2s interval)
            if (orderCounter % 30 == 0) {
                refreshSettings();
            }

            // Check kill switch
            if (!tradingEnabled) {
                return;
            }

            // Check override mode
            if ("FLATTEN_ALL".equals(overrideMode)) {
                closeAllPositions();
                return;
            }

            // Time-based stop: close positions held longer than max_hold_minutes
            enforceTimeLimits(now);

            // Report position state to backend
            reportPositions();

            // Poll for signals and execute
            pollAndExecuteSignals(instrument, tick);
        }
    }

    @Override
    public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) throws JFException {
        // Only forward 5-minute bars
        if (period != Period.FIVE_MINS) return;
        if (!subscribedInstruments.contains(instrument)) return;

        String pair = instrumentToPair(instrument);
        forwardBar(pair, bidBar, askBar);
    }

    @Override
    public void onMessage(IMessage message) throws JFException {
        IOrder order = message.getOrder();
        if (order == null) return;

        String pair = instrumentToPair(order.getInstrument());

        switch (message.getType()) {
            case ORDER_FILL_OK:
                log("Order FILLED: " + order.getLabel() + " " + order.getOrderCommand()
                    + " " + pair + " @ " + order.getOpenPrice());
                openPositions.put(pair, order);
                positionOpenTimes.put(pair, System.currentTimeMillis());
                reportPositionEvent(pair, "FILLED", order);
                break;

            case ORDER_CLOSE_OK:
                log("Order CLOSED: " + order.getLabel() + " " + pair
                    + " PnL=" + String.format("%.2f", order.getProfitLossInPips()) + " pips");
                openPositions.remove(pair);
                positionOpenTimes.remove(pair);
                reportPositionEvent(pair, "CLOSED", order);
                break;

            case ORDER_CHANGED_OK:
                log("Order MODIFIED: " + order.getLabel() + " " + pair);
                break;

            case ORDER_CHANGED_REJECTED:
                log("Order MODIFY REJECTED: " + order.getLabel() + " " + pair
                    + " reason=" + message.getContent());
                break;

            case ORDER_CLOSE_REJECTED:
                log("Order CLOSE REJECTED: " + order.getLabel() + " " + pair
                    + " reason=" + message.getContent());
                break;

            case ORDER_FILL_REJECTED:
                log("Order FILL REJECTED: " + order.getLabel() + " " + pair
                    + " reason=" + message.getContent());
                openPositions.remove(pair);
                positionOpenTimes.remove(pair);
                reportPositionEvent(pair, "REJECTED", order);
                break;

            case ORDER_SUBMIT_REJECTED:
                log("Order SUBMIT REJECTED: " + order.getLabel() + " "
                    + " reason=" + message.getContent());
                break;

            default:
                break;
        }
    }

    @Override
    public void onAccount(IAccount account) throws JFException {
        this.account = account;
    }

    @Override
    public void onStop() throws JFException {
        log("DukascopyBridgeStrategy stopping. Closing all positions...");
        closeAllPositions();
        deregisterFromBackend();
        log("DukascopyBridgeStrategy stopped.");
    }

    // =====================================================================
    //  Backend communication
    // =====================================================================

    /**
     * Connect to the Python backend and parse its configuration.
     */
    private boolean connectToBackend() {
        HttpClient.Response resp = http.get("/api/health");
        if (resp == null || !resp.isOk()) {
            backendConnected = false;
            return false;
        }

        backendConnected = true;
        consecutiveBackendFailures = 0;

        // Parse pairs from health response
        String pairsJson = resp.jsonValue("pairs");
        if (pairsJson != null) {
            subscribedInstruments.clear();
            // Parse ["AUD/USD", "NZD/USD"] style array
            String cleaned = pairsJson.replace("[", "").replace("]", "").replace("\"", "").trim();
            if (!cleaned.isEmpty()) {
                for (String p : cleaned.split(",")) {
                    Instrument inst = pairToInstrument(p.trim());
                    if (inst != null) {
                        subscribedInstruments.add(inst);
                    }
                }
            }
        }

        log("Backend connected. Status: " + resp.jsonValue("status")
            + ", Event state: " + resp.jsonValue("event_state"));
        return true;
    }

    /**
     * Register this adapter with the backend.
     */
    private void registerWithBackend() {
        String json = HttpClient.jsonObject(
            "broker", "dukascopy",
            "adapter_version", "1.0.0",
            "account_id", account != null ? account.getAccountId() : "unknown",
            "equity", account != null ? account.getEquity() : 0.0,
            "timestamp", utcNow()
        );
        HttpClient.Response resp = http.post("/api/broker/status", json);
        if (resp != null && resp.isOk()) {
            log("Registered with backend.");
        } else {
            log("WARNING: Failed to register with backend.");
        }
    }

    /**
     * Deregister from the backend on shutdown.
     */
    private void deregisterFromBackend() {
        String json = HttpClient.jsonObject(
            "broker", "dukascopy",
            "status", "disconnected",
            "timestamp", utcNow()
        );
        http.post("/api/broker/status", json);
    }

    /**
     * Check backend health. Returns true if backend is reachable and kill switch is off.
     */
    private boolean checkBackendHealth() {
        HttpClient.Response resp = http.get("/api/health");
        if (resp == null || !resp.isOk()) {
            consecutiveBackendFailures++;
            log("Backend unreachable. Failure count: " + consecutiveBackendFailures);

            if (consecutiveBackendFailures >= maxBackendFailures) {
                log("SAFETY: Backend unreachable for " + consecutiveBackendFailures
                    + " consecutive checks. Closing all positions and disabling trading.");
                tradingEnabled = false;
                try {
                    closeAllPositions();
                } catch (JFException e) {
                    log("ERROR closing positions during safety shutdown: " + e.getMessage());
                }
            }
            backendConnected = false;
            return false;
        }

        // Backend recovered
        if (!backendConnected) {
            log("Backend connection restored.");
            consecutiveBackendFailures = 0;
            backendConnected = true;
            tradingEnabled = true;
            refreshSettings();
        }
        consecutiveBackendFailures = 0;
        return true;
    }

    /**
     * Load/refresh settings from the backend.
     */
    private void refreshSettings() {
        HttpClient.Response resp = http.get("/api/settings");
        if (resp == null || !resp.isOk()) return;

        String body = resp.getBody();

        // Parse individual settings from the response
        // The backend returns a dict of settings like {"kill_switch": "false", ...}
        stopLossPips = parseSettingDouble(body, "stop_loss_pips", stopLossPips);
        takeProfitPips = parseSettingDouble(body, "take_profit_pips", takeProfitPips);
        spreadThresholdPips = parseSettingDouble(body, "spread_threshold_pips", spreadThresholdPips);
        maxHoldMinutes = (int) parseSettingDouble(body, "max_hold_minutes", maxHoldMinutes);

        String mode = parseSettingString(body, "override_mode");
        if (mode != null) overrideMode = mode;

        // Kill switch check
        String killSwitch = parseSettingString(body, "kill_switch");
        if ("true".equalsIgnoreCase(killSwitch)) {
            log("KILL SWITCH ACTIVE. Disabling trading and closing all positions.");
            tradingEnabled = false;
            try {
                closeAllPositions();
            } catch (JFException e) {
                log("ERROR closing positions for kill switch: " + e.getMessage());
            }
        } else if (!tradingEnabled && "false".equalsIgnoreCase(killSwitch) && backendConnected) {
            log("Kill switch deactivated. Re-enabling trading.");
            tradingEnabled = true;
        }
    }

    // =====================================================================
    //  Tick and bar forwarding
    // =====================================================================

    /**
     * Forward a tick to the Python backend.
     */
    private void forwardTick(String pair, ITick tick) {
        String json = HttpClient.jsonObject(
            "pair", pair,
            "bid", tick.getBid(),
            "ask", tick.getAsk(),
            "spread", (tick.getAsk() - tick.getBid()),
            "bid_volume", tick.getBidVolume(),
            "ask_volume", tick.getAskVolume(),
            "timestamp", utcNow()
        );
        HttpClient.Response resp = http.post("/api/broker/tick", json);
        // Tick forwarding failure is not critical -- silently ignored
    }

    /**
     * Forward a 5-minute bar to the Python backend.
     */
    private void forwardBar(String pair, IBar bidBar, IBar askBar) {
        double midOpen = (bidBar.getOpen() + askBar.getOpen()) / 2.0;
        double midHigh = (bidBar.getHigh() + askBar.getHigh()) / 2.0;
        double midLow = (bidBar.getLow() + askBar.getLow()) / 2.0;
        double midClose = (bidBar.getClose() + askBar.getClose()) / 2.0;
        double volume = bidBar.getVolume() + askBar.getVolume();

        String json = HttpClient.jsonObject(
            "pair", pair,
            "period", "5min",
            "open", midOpen,
            "high", midHigh,
            "low", midLow,
            "close", midClose,
            "volume", volume,
            "timestamp", utcNow()
        );
        http.post("/api/broker/bar", json);
    }

    // =====================================================================
    //  Signal polling and order execution
    // =====================================================================

    /**
     * Poll the backend for current signals and execute trades accordingly.
     */
    private void pollAndExecuteSignals(Instrument instrument, ITick tick) {
        HttpClient.Response resp = http.get("/api/signals/current");
        if (resp == null || !resp.isOk()) return;

        String body = resp.getBody();

        // Parse the signals object -- it contains per-pair signal data
        // Response format: {"signals": {"AUD/USD": {"direction": "BUY", ...}, ...}, "event_state": {...}}
        String signalsBlock = resp.jsonValue("signals");
        if (signalsBlock == null || signalsBlock.equals("{}")) return;

        // Check if the override mode from the signal response suggests OBSERVE_ONLY
        String eventStateBlock = resp.jsonValue("event_state");
        if (eventStateBlock != null) {
            HttpClient.Response stateResp = new HttpClient.Response(200, eventStateBlock);
            String state = stateResp.jsonValue("state");
            if ("PRE_EVENT".equals(state) || "COOLDOWN".equals(state)) {
                // During event windows, do not open new positions
                return;
            }
        }

        // Iterate through subscribed instruments and check their signals
        for (Instrument inst : subscribedInstruments) {
            String pair = instrumentToPair(inst);
            String pairSignal = extractPairSignal(signalsBlock, pair);
            if (pairSignal == null) continue;

            HttpClient.Response sigResp = new HttpClient.Response(200, pairSignal);
            String direction = sigResp.jsonValue("direction");
            if (direction == null) continue;

            double confidence = sigResp.jsonDouble("confidence", 0.0);

            try {
                if ("FLATTEN".equals(direction) || "FLATTEN_ALL".equals(overrideMode)) {
                    if (openPositions.containsKey(pair)) {
                        log("Signal FLATTEN for " + pair + ". Closing position.");
                        closePosition(pair);
                    }
                } else if (("BUY".equals(direction) || "SELL".equals(direction)) && confidence >= 50.0) {
                    if ("OBSERVE_ONLY".equals(overrideMode)) {
                        // Log but do not trade
                        continue;
                    }
                    if ("REDUCE_ONLY".equals(overrideMode)) {
                        // Only allow closing trades, not opening
                        continue;
                    }
                    if (!openPositions.containsKey(pair)) {
                        // Spread check
                        ITick latestTick = history.getLastTick(inst);
                        if (latestTick != null) {
                            double spreadPips = (latestTick.getAsk() - latestTick.getBid())
                                                / inst.getPipValue();
                            if (spreadPips > spreadThresholdPips) {
                                log("Spread too wide for " + pair + ": " + String.format("%.1f", spreadPips)
                                    + " pips > threshold " + spreadThresholdPips);
                                continue;
                            }
                        }
                        submitMarketOrder(inst, direction, tradeAmountLots);
                    }
                }
                // "WAIT" direction -- do nothing
            } catch (JFException e) {
                log("ERROR executing signal for " + pair + ": " + e.getMessage());
            }
        }
    }

    /**
     * Submit a market order with stop loss and take profit.
     */
    private void submitMarketOrder(Instrument instrument, String direction, double lots)
            throws JFException {

        String pair = instrumentToPair(instrument);

        // Prevent duplicate positions
        if (openPositions.containsKey(pair)) {
            log("Already have a position for " + pair + ". Skipping order.");
            return;
        }

        OrderCommand command = "BUY".equals(direction) ? OrderCommand.BUY : OrderCommand.SELL;
        String label = generateOrderLabel(pair, direction);

        // Convert lots to JForex amount (millions)
        double amount = lots;  // JForex uses lots directly in submitOrder

        // Calculate SL and TP prices
        double pipValue = instrument.getPipValue();
        ITick lastTick = history.getLastTick(instrument);
        double entryPrice;
        double slPrice;
        double tpPrice;

        if (command == OrderCommand.BUY) {
            entryPrice = lastTick.getAsk();
            slPrice = entryPrice - (stopLossPips * pipValue);
            tpPrice = entryPrice + (takeProfitPips * pipValue);
        } else {
            entryPrice = lastTick.getBid();
            slPrice = entryPrice + (stopLossPips * pipValue);
            tpPrice = entryPrice - (takeProfitPips * pipValue);
        }

        log("Submitting " + direction + " order for " + pair
            + " | amount=" + lots + " lots"
            + " | SL=" + String.format("%.5f", slPrice)
            + " | TP=" + String.format("%.5f", tpPrice));

        IOrder order = engine.submitOrder(
            label,
            instrument,
            command,
            amount,
            0,         // price=0 for market order
            20,        // slippage in pips
            slPrice,
            tpPrice
        );

        // Track the order immediately (will be confirmed in onMessage)
        openPositions.put(pair, order);
        positionOpenTimes.put(pair, System.currentTimeMillis());

        // Report to backend
        String json = HttpClient.jsonObject(
            "pair", pair,
            "direction", direction,
            "amount", lots,
            "entry_price", entryPrice,
            "stop_loss", slPrice,
            "take_profit", tpPrice,
            "label", label,
            "status", "SUBMITTED",
            "timestamp", utcNow()
        );
        http.post("/api/broker/position", json);
    }

    /**
     * Close the position for a specific pair.
     */
    private void closePosition(String pair) throws JFException {
        IOrder order = openPositions.get(pair);
        if (order != null && order.getState() == IOrder.State.FILLED) {
            log("Closing position for " + pair + " | label=" + order.getLabel());
            order.close();
            // Removal from maps happens in onMessage when ORDER_CLOSE_OK arrives
        } else if (order != null && order.getState() == IOrder.State.OPENED) {
            order.close();
        } else {
            openPositions.remove(pair);
            positionOpenTimes.remove(pair);
        }
    }

    /**
     * Close all open positions across all pairs.
     */
    private void closeAllPositions() throws JFException {
        for (Map.Entry<String, IOrder> entry : openPositions.entrySet()) {
            String pair = entry.getKey();
            IOrder order = entry.getValue();
            try {
                if (order.getState() == IOrder.State.FILLED
                        || order.getState() == IOrder.State.OPENED) {
                    log("Safety close: " + pair + " | label=" + order.getLabel());
                    order.close();
                }
            } catch (JFException e) {
                log("ERROR closing position " + pair + ": " + e.getMessage());
            }
        }

        // Also scan the engine for any orders we may have missed
        for (IOrder order : engine.getOrders()) {
            if (order.getState() == IOrder.State.FILLED
                    || order.getState() == IOrder.State.OPENED) {
                if (order.getLabel().startsWith("FXB_")) {
                    try {
                        order.close();
                    } catch (JFException e) {
                        log("ERROR closing orphaned order " + order.getLabel() + ": " + e.getMessage());
                    }
                }
            }
        }
    }

    // =====================================================================
    //  Position reporting
    // =====================================================================

    /**
     * Report all current position states to the backend.
     */
    private void reportPositions() {
        for (Map.Entry<String, IOrder> entry : openPositions.entrySet()) {
            String pair = entry.getKey();
            IOrder order = entry.getValue();
            if (order.getState() != IOrder.State.FILLED) continue;

            String json = HttpClient.jsonObject(
                "pair", pair,
                "direction", order.isLong() ? "BUY" : "SELL",
                "amount", order.getAmount(),
                "entry_price", order.getOpenPrice(),
                "current_pnl_pips", order.getProfitLossInPips(),
                "current_pnl_usd", order.getProfitLossInUSD(),
                "stop_loss", order.getStopLossPrice(),
                "take_profit", order.getTakeProfitPrice(),
                "label", order.getLabel(),
                "status", "OPEN",
                "timestamp", utcNow()
            );
            http.post("/api/broker/position", json);
        }
    }

    /**
     * Report a position lifecycle event (fill, close, reject) to the backend.
     */
    private void reportPositionEvent(String pair, String event, IOrder order) {
        String json = HttpClient.jsonObject(
            "pair", pair,
            "event", event,
            "direction", order.isLong() ? "BUY" : "SELL",
            "amount", order.getAmount(),
            "entry_price", order.getOpenPrice(),
            "close_price", order.getClosePrice(),
            "pnl_pips", order.getProfitLossInPips(),
            "pnl_usd", order.getProfitLossInUSD(),
            "label", order.getLabel(),
            "status", event,
            "timestamp", utcNow()
        );
        http.post("/api/broker/position", json);
    }

    // =====================================================================
    //  Time-based stop
    // =====================================================================

    /**
     * Force-close any position that has been held longer than max_hold_minutes.
     */
    private void enforceTimeLimits(long nowMs) {
        long maxHoldMs = maxHoldMinutes * 60L * 1000L;

        for (Map.Entry<String, Long> entry : positionOpenTimes.entrySet()) {
            String pair = entry.getKey();
            long openTime = entry.getValue();

            if ((nowMs - openTime) >= maxHoldMs) {
                log("TIME STOP: Position " + pair + " held for "
                    + ((nowMs - openTime) / 60000) + " minutes. Max=" + maxHoldMinutes + ". Closing.");
                try {
                    closePosition(pair);
                } catch (JFException e) {
                    log("ERROR in time-based close for " + pair + ": " + e.getMessage());
                }
            }
        }
    }

    // =====================================================================
    //  Utility methods
    // =====================================================================

    /**
     * Sync any existing open orders belonging to this strategy (after restart).
     */
    private void syncExistingOrders() {
        try {
            for (IOrder order : engine.getOrders()) {
                if (order.getLabel().startsWith("FXB_")
                        && (order.getState() == IOrder.State.FILLED
                            || order.getState() == IOrder.State.OPENED)) {
                    String pair = instrumentToPair(order.getInstrument());
                    openPositions.put(pair, order);
                    // Estimate open time -- we do not know the exact time, use now
                    positionOpenTimes.put(pair, System.currentTimeMillis());
                    log("Synced existing order: " + order.getLabel() + " " + pair);
                }
            }
        } catch (JFException e) {
            log("ERROR syncing existing orders: " + e.getMessage());
        }
    }

    /**
     * Generate a unique order label.
     * Format: FXB_AUDUSD_BUY_001
     */
    private String generateOrderLabel(String pair, String direction) {
        orderCounter++;
        String pairClean = pair.replace("/", "");
        return "FXB_" + pairClean + "_" + direction + "_" + String.format("%03d", orderCounter);
    }

    /**
     * Convert JForex Instrument to pair string, e.g. Instrument.AUDUSD -> "AUD/USD".
     */
    private static String instrumentToPair(Instrument instrument) {
        String name = instrument.name();
        // Instrument names are like "AUDUSD" -- insert the slash
        if (name.length() == 6) {
            return name.substring(0, 3) + "/" + name.substring(3);
        }
        // Fallback for unusual names
        return instrument.toString().replace("_", "/");
    }

    /**
     * Convert pair string to JForex Instrument, e.g. "AUD/USD" -> Instrument.AUDUSD.
     */
    private static Instrument pairToInstrument(String pair) {
        if (pair == null) return null;
        String normalized = pair.replace("/", "").replace("_", "").toUpperCase();
        try {
            return Instrument.valueOf(normalized);
        } catch (IllegalArgumentException e) {
            // Try the Instrument.fromString method as fallback
            for (Instrument inst : Instrument.values()) {
                if (inst.name().equalsIgnoreCase(normalized)) {
                    return inst;
                }
            }
            return null;
        }
    }

    /**
     * Extract the signal JSON block for a specific pair from the signals object.
     * Searches for "AUD/USD": {...} within the signals block.
     */
    private static String extractPairSignal(String signalsBlock, String pair) {
        String key = "\"" + pair + "\"";
        int idx = signalsBlock.indexOf(key);
        if (idx == -1) return null;

        int colonIdx = signalsBlock.indexOf(':', idx + key.length());
        if (colonIdx == -1) return null;

        int braceStart = signalsBlock.indexOf('{', colonIdx);
        if (braceStart == -1) return null;

        // Find matching close brace
        int depth = 1;
        int pos = braceStart + 1;
        boolean inString = false;
        while (pos < signalsBlock.length() && depth > 0) {
            char c = signalsBlock.charAt(pos);
            if (inString) {
                if (c == '\\') { pos++; }
                else if (c == '"') { inString = false; }
            } else {
                if (c == '"') { inString = true; }
                else if (c == '{') { depth++; }
                else if (c == '}') { depth--; }
            }
            pos++;
        }

        if (depth != 0) return null;
        return signalsBlock.substring(braceStart, pos);
    }

    /**
     * Parse a double setting value from the backend settings JSON response.
     * Settings response format: {"key1": "value1", "key2": "value2", ...}
     */
    private static double parseSettingDouble(String body, String key, double defaultValue) {
        String val = parseSettingString(body, key);
        if (val == null) return defaultValue;
        try {
            return Double.parseDouble(val);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    /**
     * Parse a string setting value from the backend settings JSON response.
     */
    private static String parseSettingString(String body, String key) {
        if (body == null) return null;
        String search = "\"" + key + "\"";
        int idx = body.indexOf(search);
        if (idx == -1) return null;
        int colonIdx = body.indexOf(':', idx + search.length());
        if (colonIdx == -1) return null;
        int start = colonIdx + 1;
        while (start < body.length() && body.charAt(start) == ' ') start++;
        if (start >= body.length()) return null;

        if (body.charAt(start) == '"') {
            int end = body.indexOf('"', start + 1);
            if (end == -1) return null;
            return body.substring(start + 1, end);
        } else {
            int end = start;
            while (end < body.length() && body.charAt(end) != ','
                    && body.charAt(end) != '}' && body.charAt(end) != ']') {
                end++;
            }
            return body.substring(start, end).trim();
        }
    }

    /**
     * Get current UTC timestamp as ISO 8601 string.
     */
    private static String utcNow() {
        synchronized (ISO_FORMAT) {
            return ISO_FORMAT.format(new Date());
        }
    }

    /**
     * Log a message to the JForex console.
     */
    private void log(String message) {
        if (console != null) {
            console.getOut().println("[FXBridge] " + message);
        }
    }
}
