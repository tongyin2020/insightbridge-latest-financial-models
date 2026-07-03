"""EventAlpha intraday event-study package.

Measures, from real intraday data, the four timing parameters the event-driven
strategy needs per asset:

1. reaction latency   - seconds from event T0 until price genuinely starts moving
2. washout duration   - seconds the fake-impulse / whipsaw lasts before real flow
3. trend lifetime     - seconds the real post-washout trend persists
4. retracement timing - seconds from max-favourable-excursion until giveback

These measured distributions are meant to replace the hard-coded guesses in
``eventalpha_core/advanced/waiting_policy_engine.py`` (wait windows) and to
calibrate ``eventalpha_core/advanced/escape_engine.py`` (exit thresholds).

The package is read-only research: it downloads public historical data and
writes reports. It never touches a broker or live trading logic.
"""
