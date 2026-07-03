# JForex tick export (FX/oil precision refresh)

The public Dukascopy datafeed host currently returns `503 Service Unavailable`
("no server is available") and is unusable for historical `.bi5` downloads. The
**authenticated** JForex channel (the one your live client already uses) works
fine, so we pull the historical ticks through a local strategy instead.

This exports only the ticks inside each macro-event window (~40 min each around
~79 NFP/CPI/FOMC events, 2024-2026) — not two years of raw ticks — which is all
the event study needs.

## Steps (on the Mac, in JForex4)

1. Generate the event-window list (writes `~/eventalpha_data/event_windows.csv`):

   ```bash
   python3 -m eventalpha_intraday_study.export_event_windows --start 2024 --end 2026
   ```

2. In JForex4 (already logged in): **Strategies → Open** →
   `EventTickExportStrategy.java` → **Compile** → **Run local**.
   - `Event windows CSV` default: `~/eventalpha_data/event_windows.csv`
   - `Output directory` default: `~/eventalpha_data/jforex_ticks`
   - `Instruments`: `EUR/USD,USD/JPY,LIGHT.CMD/USD`  (LIGHT.CMD/USD = WTI)

   The console prints `[TickExport] ... -> ticks_XXX.csv (N ticks)` per instrument
   and `ALL DONE` when finished. The strategy never trades.

3. Run the tick-precision study (per instrument):

   ```bash
   python3 -m eventalpha_intraday_study.run_jforex_study --instrument EUR/USD --years 2024,2025
   python3 -m eventalpha_intraday_study.run_jforex_study --instrument USD/JPY --years 2024,2025
   python3 -m eventalpha_intraday_study.run_jforex_study --instrument LIGHT.CMD/USD --years 2024,2025
   ```

   This reuses the same measurement engine at `bar_seconds=1` (full tick
   resolution) instead of the 60s HistData bars, then produces updated summaries
   to fold into `measured_timing.py`.

Notes:
- `LIGHT.CMD/USD` is Dukascopy's WTI CFD (the exact WTI the live oil model
  trades); if the enum name differs in your JForex build, the strategy also tries
  `Instrument.fromString` / `fromInvertedString`.
- BTC already uses real Binance tick data, so it is not re-exported here.
