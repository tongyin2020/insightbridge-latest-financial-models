#!/bin/bash
# 编译 + 运行 Dukascopy 无头桥（验证连接 + 启动策略 + 拿行情）
set -uo pipefail
cd /Users/tongyin/InsightBridge_Financial_Models_Latest

set -a; source .env.dukascopy_demo.local; set +a

JAVA="$DUKASCOPY_JAVA_BIN"
SDK="/Users/tongyin/JForex4/libs/DEMO_NEW_VERSIONS/4.8.18"
ECJ="$SDK/ecj-3.20.0.1d.jar"
CP="$(find "$SDK" -name '*.jar' 2>/dev/null | tr '\n' ':')"
ADAPTER="03_FX_AUD_NZD_EUR_GBP/fx_trading_system/adapters/dukascopy"
OUT=/tmp/dc_bridge

mkdir -p "$OUT"
echo "=== 编译（ECJ，3 个源文件）==="
"$JAVA" -jar "$ECJ" -1.8 -cp "$CP" -d "$OUT" \
  "$ADAPTER/DukascopyBridgeStrategy.java" \
  "$ADAPTER/HttpClient.java" \
  "$ADAPTER/DukascopyHeadlessBridge.java" 2>&1 | head -20
if [ -f "$OUT/adapters/dukascopy/DukascopyHeadlessBridge.class" ]; then
  echo "编译成功"
else
  echo "编译失败"
  exit 1
fi

echo "=== 运行无头桥（75s，观察连接+策略+行情）==="
( "$JAVA" -cp "$OUT:$CP" adapters.dukascopy.DukascopyHeadlessBridge > /tmp/dc_bridge.log 2>&1 & echo $! > /tmp/dc_bridge.pid )
PID=$(cat /tmp/dc_bridge.pid)
sleep 75
kill "$PID" 2>/dev/null
sleep 2
kill -9 "$PID" 2>/dev/null
echo "--- 关键输出 ---"
grep -iE "bridge|connected|strategy|started|tick|bar|registered|subscribed|backend|error|exception|disconnect" /tmp/dc_bridge.log | grep -viE "SRP|srp|AuthorizationClient|headerFields|responseString|ApiServerManager|SystemSettingsManager" | head -40
