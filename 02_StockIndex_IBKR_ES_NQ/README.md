# IBKR Paper Trading Connector

## 启动步骤（每次交易前）

### Step 1 — 打开 TWS 并登录 Paper Trading
1. 打开 TWS 软件
2. 用 DU 开头账号登录
3. 模式选 "Paper Trading"

### Step 2 — 开启 API
TWS 菜单：Edit → Global Configuration → API → Settings
- ✅ Enable ActiveX and Socket Clients
- Port: 7497
- 点 Apply → OK

### Step 3 — 运行连接测试
```bash
cd "/Users/tongyin/Desktop/New Financial Models/Financial_Models_Security_Enhanced_Full"
python3 ibkr_paper_trading/ibkr_connector.py
```

## 端口说明
| 模式 | 端口 |
|------|------|
| Paper Trading | 7497 ✅ |
| Live Trading | 7496 ⚠️ |
