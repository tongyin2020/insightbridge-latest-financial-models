#!/bin/bash
# Dukascopy 无头连接重建 + 测试（4.8.18 SDK + 新账户）
set -uo pipefail
cd /Users/tongyin/InsightBridge_Financial_Models_Latest

# 1. 加载 .env（新账户凭据 + SDK 路径）
set -a
source .env.dukascopy_demo.local
set +a

JAVA="$DUKASCOPY_JAVA_BIN"
SDK="/Users/tongyin/JForex4/libs/DEMO_NEW_VERSIONS/4.8.18"
CP="$(find "$SDK" -name '*.jar' 2>/dev/null | tr '\n' ':')"

echo "Java: $($JAVA -version 2>&1 | head -1)"
echo "SDK jars: $(find "$SDK" -name '*.jar' 2>/dev/null | wc -l | tr -d ' ')"
echo "User: $DUKASCOPY_DEMO_USER  JNLP: $DUKASCOPY_DEMO_JNLP_URL"

# 2. 编译连接检查程序（用 ECJ，因为 JForex 自带 javac 依赖 JAVA_HOME 不稳定）
ECJ="/Users/tongyin/JForex4/libs/DEMO_NEW_VERSIONS/4.8.18/ecj-3.20.0.1d.jar"
mkdir -p /tmp/dc_test
echo "--- 编译 DukascopyDemoConnectCheck（ECJ）---"
"$JAVA" -jar "$ECJ" -1.8 -cp "$CP" -d /tmp/dc_test dukascopy_runtime/src/DukascopyDemoConnectCheck.java 2>&1 | head -30
if [ -f /tmp/dc_test/DukascopyDemoConnectCheck.class ]; then
  echo "编译成功"
else
  echo "编译失败"
  exit 1
fi

# 3. 运行连接检查（45s 超时）
echo "--- 运行连接检查 ---"
"$JAVA" -cp "/tmp/dc_test:$CP" DukascopyDemoConnectCheck 2>&1 | grep -iE "connect|success|error|exception|OK|fail|missing" | head -30
