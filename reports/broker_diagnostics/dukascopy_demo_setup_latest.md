# Dukascopy Demo Setup Report

- generated_at: 2026-08-24T23:28:59.055026+00:00
- project: `/Users/tongyin/InsightBridge_Financial_Models_Latest`
- env_file: `/Users/tongyin/InsightBridge_Financial_Models_Latest/.env.dukascopy_demo.local`
- overall: **READY - local Dukascopy demo bridge prerequisites are present.**

## Setup Checks

### credentials

- status: OK
- detail: demo credentials present locally
- extra: `{"url": "https://dukascopy.com", "jnlp_url": "https://platform.dukascopy.com/demo_4/jforex_4.jnlp", "user_present": true, "password_present": true}`

### java_runtime

- status: OK
- detail: java runtime available
- extra: `{"java_bin": "/Users/tongyin/JForex4/.install4j/jre.bundle/Contents/Home/bin/java", "output": ["openjdk version \"25.0.3\" 2026-04-21 LTS", "OpenJDK Runtime Environment Zulu25.34+17-CA (build 25.0.3+9-LTS)"], "source": "env_or_detected_bundle"}`

### sdk_jars

- status: OK
- detail: dukascopy sdk jar path configured
- extra: `{"sdk_jar": "/Users/tongyin/JForex4/libs/demo/4.8.16/jforex-api-4.8.13.jar", "jnlp_jar": "/Users/tongyin/JForex4/libs/demo/4.8.16/jforex-demo.jnlp", "source": "env_or_detected_jforex_install"}`

## Broker Supplement Matrix

| Symbol | Group | IBKR Cause | Dukascopy Strength | Recommendation |
|---|---|---|---|---|
| EURUSD | FX | no_recent_ibkr_diagnostic | strong | verify_manually |
| USDJPY | FX | no_recent_ibkr_diagnostic | strong | verify_manually |
| BTC | CRYPTO | subscription_missing | partial | conditional_supplement |
| ETH | CRYPTO | subscription_missing | partial | conditional_supplement |
| SOL | CRYPTO | subscription_missing | partial | conditional_supplement |
| CL | OIL | subscription_missing | partial | conditional_supplement |
| MES | INDEX | subscription_missing | weak | low_probability_supplement |
| MNQ | INDEX | no_recent_ibkr_diagnostic | weak | verify_manually |
| ZT | TREASURY | no_recent_ibkr_diagnostic | weak | verify_manually |
| ZN | TREASURY | subscription_missing | weak | low_probability_supplement |
| SR3 | TREASURY | no_recent_ibkr_diagnostic | weak | verify_manually |

