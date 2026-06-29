# Dukascopy Demo Integration Notes

This project now contains a local Dukascopy demo-account integration scaffold intended to complement the existing IBKR paper-trading workflow.

## What is already added

- local private environment file support:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/.env.dukascopy_demo.local`
- safe example template:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/.env.dukascopy_demo.local.example`
- local setup / readiness checker:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_dukascopy_demo_setup.py`
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_dukascopy_demo_setup.sh`
- runtime prep:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/prepare_dukascopy_demo_runtime.py`
- Java installer helper:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/install_dukascopy_java_runtime.sh`
- Java SDK login check:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_dukascopy_demo_connect_check.sh`
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/dukascopy_runtime/src/DukascopyDemoConnectCheck.java`

## Why this was added

The five-model runtime already uses IBKR paper trading as the execution backbone.
However, IBKR market-data diagnostics showed that some symbols can still suffer from:

- subscription gaps
- delayed-only data
- competing-session conflicts

Dukascopy demo can therefore serve as a secondary broker / market-data path, especially for:

- FX pairs
- some crypto coverage
- some oil / CFD-style instruments

It is much less likely to cleanly replace:

- CME micro index futures
- Treasury futures
- short-rate futures

## Current blocker

This Mac currently does not have a Java Runtime available, and Dukascopy's JForex / SDK path depends on Java.

That means:

- credentials can already be stored locally
- the readiness checker already works
- the actual SDK login bridge cannot run until Java and the Dukascopy SDK jars are installed

Official Dukascopy wiki references:

- Dukascopy says Desktop JForex4 is written in Java and needs JRE, and that version 4.14+ bundles Java 21 in the desktop package.
- Dukascopy SDK documentation shows `ClientFactory.getDefaultInstance()` and a demo connection example using:
  - `https://platform.dukascopy.com/demo_4/jforex_4.jnlp`

## Quick check

```bash
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_dukascopy_demo_setup.sh
```

## Install Java first

```bash
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/install_dukascopy_java_runtime.sh
```

## Prepare folders and scan for SDK artifacts

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/prepare_dukascopy_demo_runtime.py
```

## What to install later

1. a local Java Runtime
2. the Dukascopy / JForex SDK jar(s)
3. then fill these paths in the local private env file:

```bash
DUKASCOPY_JAVA_BIN=/path/to/java
DUKASCOPY_JFOREX_SDK_JAR=/path/to/sdk.jar
DUKASCOPY_JNLP_JAR=/path/to/jnlp.jar
```

The easiest local drop location is:

```bash
/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/dukascopy_runtime/sdk
```

## Current conclusion

The standalone SDK login test reaches Dukascopy successfully, but the modern JForex4 desktop login flow and the old standalone `client.connect(...)` flow do not behave identically on this Mac. The more reliable production path is now:

- keep JForex4 logged in manually
- run the Dukascopy bridge strategy *inside* JForex4
- let that in-client strategy talk to the local FX backend over HTTP

## First real SDK login test

After Java and the SDK jar are present:

```bash
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_dukascopy_demo_connect_check.sh
```

## Design principle

This integration is intentionally parallel to IBKR, not a replacement.
The safer production path is:

- keep IBKR as the execution source of truth
- use Dukascopy as a secondary data / validation / fallback path where it is strong

## Recommended local commands now

```bash
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/start_dukascopy_fx_bridge_backend.sh
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/build_dukascopy_fx_strategy.sh
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_dukascopy_fx_bridge_status.py
```
