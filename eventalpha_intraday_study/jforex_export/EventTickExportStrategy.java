package eventalpha.export;

import com.dukascopy.api.Configurable;
import com.dukascopy.api.IBar;
import com.dukascopy.api.IConsole;
import com.dukascopy.api.IContext;
import com.dukascopy.api.IHistory;
import com.dukascopy.api.IMessage;
import com.dukascopy.api.IStrategy;
import com.dukascopy.api.ITick;
import com.dukascopy.api.Instrument;
import com.dukascopy.api.JFException;
import com.dukascopy.api.Period;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Historical tick exporter for the EventAlpha intraday event study.
 *
 * Runs INSIDE JForex4 over the authenticated (logged-in) channel, so it does NOT
 * hit the public datafeed host (which currently returns 503 backend-unavailable).
 *
 * It reads the event-window CSV produced by
 *   python -m eventalpha_intraday_study.export_event_windows
 * and, for each instrument, pulls only the ticks inside each macro-event window
 * (a few tens of minutes each -- NOT two years of raw ticks), writing one CSV per
 * instrument:  timestamp_ms,bid,ask,bidVol,askVol
 *
 * This strategy never submits, modifies, or closes any order.
 */
public class EventTickExportStrategy implements IStrategy {

    @Configurable("Event windows CSV (from export_event_windows.py)")
    public String eventWindowsCsv = System.getProperty("user.home") + "/eventalpha_data/event_windows.csv";

    @Configurable("Output directory")
    public String outputDir = System.getProperty("user.home") + "/eventalpha_data/jforex_ticks";

    @Configurable("Instruments CSV (logical)")
    public String instrumentsCsv = "EUR/USD,USD/JPY,LIGHT.CMD/USD";

    private IConsole console;
    private IHistory history;

    @Override
    public void onStart(IContext context) throws JFException {
        this.console = context.getConsole();
        this.history = context.getHistory();
        // getTicks must not run on the strategy thread; do it in a worker.
        Thread worker = new Thread(this::exportAll, "eventalpha-tick-export");
        worker.setDaemon(true);
        worker.start();
        log("EventTickExportStrategy started; export running in background thread.");
    }

    private void exportAll() {
        try {
            List<long[]> windows = readWindows(eventWindowsCsv);   // {win_start_ms, win_end_ms}
            if (windows.isEmpty()) {
                log("No event windows found in " + eventWindowsCsv);
                return;
            }
            new File(outputDir).mkdirs();
            for (String raw : instrumentsCsv.split(",")) {
                String logical = raw.trim();
                if (logical.isEmpty()) continue;
                Instrument inst = resolveInstrument(logical);
                if (inst == null) {
                    log("Skip unresolved instrument: " + logical);
                    continue;
                }
                exportInstrument(logical, inst, windows);
            }
            log("EventTickExportStrategy: ALL DONE.");
        } catch (Exception e) {
            log("export error: " + e.getMessage());
        }
    }

    private void exportInstrument(String logical, Instrument inst, List<long[]> windows) {
        String safe = logical.replace("/", "").replace(".", "");
        File out = new File(outputDir, "ticks_" + safe + ".csv");
        long total = 0;
        try (BufferedWriter w = new BufferedWriter(new FileWriter(out))) {
            w.write("timestamp_ms,bid,ask,bidVol,askVol");
            w.newLine();
            for (long[] win : windows) {
                long from = win[0], to = win[1];
                try {
                    List<ITick> ticks = history.getTicks(inst, from, to);
                    if (ticks == null) continue;
                    for (ITick t : ticks) {
                        w.write(t.getTime() + ","
                                + fmt(t.getBid()) + ","
                                + fmt(t.getAsk()) + ","
                                + fmt(t.getBidVolume()) + ","
                                + fmt(t.getAskVolume()));
                        w.newLine();
                        total++;
                    }
                } catch (JFException je) {
                    log(logical + " window [" + from + "," + to + "] failed: " + je.getMessage());
                }
            }
            log(logical + " -> " + out.getAbsolutePath() + "  (" + total + " ticks)");
        } catch (Exception e) {
            log(logical + " write error: " + e.getMessage());
        }
    }

    private List<long[]> readWindows(String path) {
        List<long[]> out = new ArrayList<>();
        try (BufferedReader r = new BufferedReader(new FileReader(path))) {
            String line = r.readLine(); // header
            while ((line = r.readLine()) != null) {
                String[] c = line.split(",");
                if (c.length < 5) continue;
                try {
                    out.add(new long[]{Long.parseLong(c[3].trim()), Long.parseLong(c[4].trim())});
                } catch (NumberFormatException ignore) {
                }
            }
        } catch (Exception e) {
            log("cannot read windows csv: " + e.getMessage());
        }
        return out;
    }

    private Instrument resolveInstrument(String candidate) {
        Instrument direct = Instrument.fromString(candidate);
        if (direct != null) return direct;
        Instrument inv = Instrument.fromInvertedString(candidate);
        if (inv != null) return inv;
        try {
            return Instrument.valueOf(candidate.replace("/", "").replace(".", ""));
        } catch (IllegalArgumentException ignored) {
            return null;
        }
    }

    private String fmt(double v) {
        if (Double.isNaN(v) || Double.isInfinite(v)) return "";
        return String.format(Locale.US, "%.6f", v);
    }

    private void log(String m) {
        if (console != null) console.getOut().println("[TickExport] " + m);
    }

    @Override public void onTick(Instrument instrument, ITick tick) throws JFException { }
    @Override public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) throws JFException { }
    @Override public void onMessage(IMessage message) throws JFException { }
    @Override public void onAccount(com.dukascopy.api.IAccount account) throws JFException { }
    @Override public void onStop() throws JFException { log("EventTickExportStrategy stopped."); }
}
