package adapters.dukascopy;

import com.dukascopy.api.Configurable;
import com.dukascopy.api.IAccount;
import com.dukascopy.api.IBar;
import com.dukascopy.api.IConsole;
import com.dukascopy.api.IContext;
import com.dukascopy.api.IMessage;
import com.dukascopy.api.IStrategy;
import com.dukascopy.api.ITick;
import com.dukascopy.api.Instrument;
import com.dukascopy.api.JFException;
import com.dukascopy.api.Period;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TimeZone;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Minimal Dukascopy probe strategy.
 *
 * Purpose:
 *   - verify JForex4 can run a local strategy
 *   - verify it can reach the local Python backend
 *   - forward live FX ticks only
 *
 * It never submits, modifies, or closes any order.
 */
public class DukascopyTickProbeStrategy implements IStrategy {

    @Configurable("Backend URL")
    public String backendUrl = "http://127.0.0.1:8001";

    @Configurable("Pairs CSV")
    public String pairsCsv = "AUD/USD,NZD/USD,EUR/USD,USD/JPY,GBP/USD,AUD/JPY,NZD/JPY";

    @Configurable("Tick forwarding interval (ms)")
    public long tickForwardIntervalMs = 1000;

    @Configurable("Status heartbeat interval (ms)")
    public long statusHeartbeatIntervalMs = 10000;

    private IConsole console;
    private IAccount account;
    private SimpleHttpClient http;

    private final Set<Instrument> subscribedInstruments = new LinkedHashSet<>();
    private final Map<Instrument, String> subscribedLabels = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Long> lastTickForwardTime = new ConcurrentHashMap<>();
    private long lastStatusHeartbeatTime = 0L;

    private static final SimpleDateFormat ISO_FORMAT = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'");
    static {
        ISO_FORMAT.setTimeZone(TimeZone.getTimeZone("UTC"));
    }

    @Override
    public void onStart(IContext context) throws JFException {
        this.console = context.getConsole();
        this.account = context.getAccount();
        this.http = new SimpleHttpClient(backendUrl, 5000, 10000);

        parseInstruments();
        if (subscribedInstruments.isEmpty()) {
            subscribedInstruments.add(Instrument.AUDUSD);
            subscribedInstruments.add(Instrument.NZDUSD);
        }
        context.setSubscribedInstruments(subscribedInstruments, true);

        log("DukascopyTickProbeStrategy started.");
        log("Backend URL: " + backendUrl);
        log("Subscribed instruments: " + subscribedInstruments);

        sendStatus("probe_starting");
    }

    @Override
    public void onTick(Instrument instrument, ITick tick) throws JFException {
        if (!subscribedInstruments.contains(instrument)) {
            return;
        }

        String pair = instrumentToPair(instrument);
        long now = System.currentTimeMillis();
        Long lastForward = lastTickForwardTime.get(pair);
        if (lastForward == null || (now - lastForward) >= tickForwardIntervalMs) {
            lastTickForwardTime.put(pair, now);
            forwardTick(pair, tick);
        }

        if ((now - lastStatusHeartbeatTime) >= statusHeartbeatIntervalMs) {
            lastStatusHeartbeatTime = now;
            sendStatus("probe_live");
        }
    }

    @Override
    public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) throws JFException {
        // Intentionally no-op: tick probe only.
    }

    @Override
    public void onMessage(IMessage message) throws JFException {
        // Intentionally no-op: this strategy does not trade.
    }

    @Override
    public void onAccount(IAccount account) throws JFException {
        this.account = account;
        sendStatus("probe_live");
    }

    @Override
    public void onStop() throws JFException {
        sendStatus("disconnected");
        log("DukascopyTickProbeStrategy stopped.");
    }

    private void parseInstruments() {
        subscribedInstruments.clear();
        subscribedLabels.clear();
        if (pairsCsv == null || pairsCsv.trim().isEmpty()) {
            return;
        }
        String[] parts = pairsCsv.split(",");
        for (String part : parts) {
            ResolvedInstrument resolved = parseInstrument(part);
            if (resolved != null) {
                subscribedInstruments.add(resolved.instrument);
                subscribedLabels.put(resolved.instrument, resolved.logicalLabel);
                if (!resolved.actualName.equalsIgnoreCase(resolved.logicalLabel)) {
                    log("Mapped " + resolved.logicalLabel + " -> " + resolved.actualName);
                }
            } else {
                log("Skipping unsupported instrument entry: " + part);
            }
        }
    }

    private ResolvedInstrument parseInstrument(String value) {
        String normalized = value == null ? "" : value.trim().toUpperCase(Locale.ROOT)
            .replace("-", "/")
            .replace("_", "/");
        if (normalized.isEmpty()) {
            return null;
        }

        String logicalLabel = normalized;
        List<String> candidates = new ArrayList<>();

        if (normalized.equals("AUDUSD") || normalized.equals("AUD/USD")) {
            logicalLabel = "AUD/USD";
            candidates.add("AUD/USD");
        } else if (normalized.equals("NZDUSD") || normalized.equals("NZD/USD")) {
            logicalLabel = "NZD/USD";
            candidates.add("NZD/USD");
        } else if (normalized.equals("EURUSD") || normalized.equals("EUR/USD")) {
            logicalLabel = "EUR/USD";
            candidates.add("EUR/USD");
        } else if (normalized.equals("USDJPY") || normalized.equals("USD/JPY")) {
            logicalLabel = "USD/JPY";
            candidates.add("USD/JPY");
        } else if (normalized.equals("GBPUSD") || normalized.equals("GBP/USD")) {
            logicalLabel = "GBP/USD";
            candidates.add("GBP/USD");
        } else if (normalized.equals("AUDJPY") || normalized.equals("AUD/JPY")) {
            logicalLabel = "AUD/JPY";
            candidates.add("AUD/JPY");
        } else if (normalized.equals("NZDJPY") || normalized.equals("NZD/JPY")) {
            logicalLabel = "NZD/JPY";
            candidates.add("NZD/JPY");
        } else if (normalized.equals("USDCHF") || normalized.equals("USD/CHF")) {
            logicalLabel = "USD/CHF";
            candidates.add("USD/CHF");
        } else if (normalized.equals("USDCAD") || normalized.equals("USD/CAD")) {
            logicalLabel = "USD/CAD";
            candidates.add("USD/CAD");
        } else if (normalized.equals("BTC") || normalized.equals("BTCUSD") || normalized.equals("BTC/USD")) {
            logicalLabel = "BTC";
            candidates.add("BTC/USD");
        } else if (normalized.equals("MES") || normalized.equals("USA500") ||
                   normalized.equals("USA500.IDX") || normalized.equals("USA500.IDX/USD")) {
            logicalLabel = "MES";
            candidates.add("USA500.IDX/USD");
        } else if (normalized.equals("MNQ") || normalized.equals("USATECH") ||
                   normalized.equals("USATECH.IDX") || normalized.equals("USATECH.IDX/USD")) {
            logicalLabel = "MNQ";
            candidates.add("USATECH.IDX/USD");
        } else if (normalized.equals("ZT") || normalized.equals("ZN") || normalized.equals("SR3")) {
            log("No clean Dukascopy instrument mapping defined for " + normalized);
            return null;
        } else {
            candidates.add(normalized);
        }

        for (String candidate : candidates) {
            Instrument instrument = resolveInstrument(candidate);
            if (instrument != null) {
                return new ResolvedInstrument(instrument, logicalLabel, candidate);
            }
        }
        return null;
    }

    private Instrument resolveInstrument(String candidate) {
        if (candidate == null || candidate.isEmpty()) {
            return null;
        }
        Instrument direct = Instrument.fromString(candidate);
        if (direct != null) {
            return direct;
        }
        Instrument inverted = Instrument.fromInvertedString(candidate);
        if (inverted != null) {
            return inverted;
        }
        try {
            String enumLike = candidate.replace("/", "").replace(".", "");
            return Instrument.valueOf(enumLike);
        } catch (IllegalArgumentException ignored) {
            return null;
        }
    }

    private String instrumentToPair(Instrument instrument) {
        String label = subscribedLabels.get(instrument);
        return label != null ? label : instrument.toString();
    }

    private void sendStatus(String status) {
        if (http == null) return;
        String payload = "{"
            + "\"broker\":\"dukascopy\","
            + "\"status\":\"" + escape(status) + "\","
            + "\"adapter_version\":\"tick-probe-1.0\","
            + "\"account_id\":" + jsonString(account != null ? account.getAccountId() : null) + ","
            + "\"equity\":" + (account != null ? Double.toString(account.getEquity()) : "null") + ","
            + "\"timestamp\":\"" + isoNow() + "\""
            + "}";
        SimpleHttpClient.Response response = http.post("/api/broker/status", payload);
        if (response == null) {
            log("Status post failed: backend unreachable");
        }
    }

    private void forwardTick(String pair, ITick tick) {
        if (http == null) return;
        String payload = "{"
            + "\"pair\":\"" + escape(pair) + "\","
            + "\"bid\":" + formatPrice(tick.getBid()) + ","
            + "\"ask\":" + formatPrice(tick.getAsk()) + ","
            + "\"bid_volume\":" + formatVolume(tick.getBidVolume()) + ","
            + "\"ask_volume\":" + formatVolume(tick.getAskVolume()) + ","
            + "\"timestamp\":\"" + isoFromMillis(tick.getTime()) + "\""
            + "}";
        SimpleHttpClient.Response response = http.post("/api/broker/tick", payload);
        if (response == null) {
            log("Tick forward failed for " + pair + ": backend unreachable");
        }
    }

    private String formatPrice(double value) {
        return String.format(Locale.US, "%.6f", value);
    }

    private String formatVolume(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) return "null";
        return String.format(Locale.US, "%.4f", value);
    }

    private String isoNow() {
        return isoFromMillis(System.currentTimeMillis());
    }

    private String isoFromMillis(long millis) {
        synchronized (ISO_FORMAT) {
            return ISO_FORMAT.format(millis);
        }
    }

    private String jsonString(String value) {
        if (value == null || value.isEmpty()) return "null";
        return "\"" + escape(value) + "\"";
    }

    private String escape(String value) {
        return value == null ? "" : value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private void log(String message) {
        if (console != null) {
            console.getOut().println("[TickProbe] " + message);
        }
    }

    /**
     * Small self-contained HTTP helper so JForex can compile this file alone.
     */
    static class SimpleHttpClient {
        private final String baseUrl;
        private final int connectTimeoutMs;
        private final int readTimeoutMs;

        SimpleHttpClient(String baseUrl, int connectTimeoutMs, int readTimeoutMs) {
            this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
            this.connectTimeoutMs = connectTimeoutMs;
            this.readTimeoutMs = readTimeoutMs;
        }

        static class Response {
            final int statusCode;
            final String body;

            Response(int statusCode, String body) {
                this.statusCode = statusCode;
                this.body = body;
            }
        }

        Response post(String path, String jsonBody) {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(baseUrl + path);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Accept", "application/json");
                conn.setConnectTimeout(connectTimeoutMs);
                conn.setReadTimeout(readTimeoutMs);
                conn.setDoOutput(true);

                byte[] payload = jsonBody.getBytes(StandardCharsets.UTF_8);
                conn.setFixedLengthStreamingMode(payload.length);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(payload);
                    os.flush();
                }

                int status = conn.getResponseCode();
                String body = readStream(conn, status);
                return new Response(status, body);
            } catch (IOException e) {
                return null;
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }

        private String readStream(HttpURLConnection conn, int status) throws IOException {
            BufferedReader reader;
            if (status >= 200 && status < 400) {
                reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
            } else {
                if (conn.getErrorStream() == null) {
                    return "";
                }
                reader = new BufferedReader(new InputStreamReader(conn.getErrorStream(), StandardCharsets.UTF_8));
            }
            StringBuilder body = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
            reader.close();
            return body.toString();
        }
    }

    static class ResolvedInstrument {
        final Instrument instrument;
        final String logicalLabel;
        final String actualName;

        ResolvedInstrument(Instrument instrument, String logicalLabel, String actualName) {
            this.instrument = instrument;
            this.logicalLabel = logicalLabel;
            this.actualName = actualName;
        }
    }
}
