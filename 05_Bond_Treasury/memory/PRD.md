# AI Bond & Rate Trading System - PRD

## Original Problem Statement
Build an AI-driven auto-trading bot model for government bonds and interest rate futures. Full-stack platform with React, FastAPI, MongoDB, real-time market data, AI decision queuing, social/leaderboard features, risk analytics, portfolio optimization, and email notifications.

## Core Architecture (V10)
- **Frontend**: React + TailwindCSS + Shadcn UI + Recharts
- **Backend**: FastAPI (modular) + Motor (MongoDB async)
- **Database**: MongoDB
- **AI**: GPT-5.2 via Emergent LLM Key
- **Market Data**: yfinance (Yahoo Finance)
- **Notifications**: Telegram + Browser Push + Risk Alert Push + Resend Email
- **Auth**: JWT (httpOnly cookies) + PyOTP (2FA/TOTP)

### Backend Module Structure
```
/app/backend/services/
├── telegram.py, market_data.py, ai_engine.py, multi_asset.py
├── backtest.py, portfolio.py, paper_trading.py, marketplace.py
├── social.py, yield_curve.py, risk_analytics.py, ai_brief.py
├── risk_alerts.py, risk_trends.py, email_digest.py, portfolio_optimizer.py
```

## All Implemented Features

### Phase 1-4: MVP
- [x] JWT Auth + brute-force protection + 2FA/TOTP
- [x] Dashboard with real-time WebSocket market data + Bond Analytics
- [x] AI Decision Queue (GPT-5.2), System lifecycle, kill switch, risk guard
- [x] Paper trading, Portfolio management, Strategy Marketplace
- [x] Social page with Leaderboard, Activity Feed, Network

### Phase 5-6: Security & Refactoring
- [x] 2FA full UI flow, Bond analytics, Strategy auto-execution
- [x] Backend modular architecture refactoring

### Phase 7: Yield Curve & Backtesting
- [x] Real Historical Backtesting with yfinance
- [x] Yield Curve Analytics + Bond Auction Service

### Phase 8: Risk Analytics & AI Brief
- [x] Risk Analytics Page (VaR, stress tests, radar, histogram)
- [x] AI Market Brief on Dashboard (GPT-5.2)
- [x] Mobile responsiveness optimizations

### Phase 9: Risk Alert Push
- [x] 5-type risk monitoring (VaR/Vol/Drawdown/Sharpe/Stress)
- [x] Configurable thresholds UI + Telegram push
- [x] WebSocket real-time alert broadcast + 30-min cooldown

### Phase 10: Email Digest + Risk Trends + Portfolio Optimizer (April 2, 2026)
- [x] **Email Daily Digest** (Resend) — HTML email with risk summary, alerts, AI brief, portfolio snapshot. Configurable preferences, send now button, digest history
- [x] **Historical Risk Trend Charts** — Snapshots auto-saved on risk check. Line chart with VaR/Vol/Sharpe/Drawdown/Value metrics, 7/30/90 day ranges
- [x] **Black-Litterman Portfolio Optimizer** — Full optimization engine with 8 bond assets (UST 2Y/5Y/10Y/30Y, TIPS, IG Corp, HY Corp, MBS). Investor views input, BL Optimal/Max Sharpe/Min Variance portfolios, Efficient Frontier scatter plot, Asset Allocation bar chart, Detailed allocations table

## Key API Endpoints
- Auth: /api/auth/login, /register, /logout, /me, /refresh
- 2FA: /api/auth/2fa/setup, /confirm, /disable, /verify, /status
- Market: /api/market/current, /history, /historical, /bond-analytics
- Yield: /api/yield-curve/current, /historical, /heatmap
- Auctions: /api/auctions/upcoming, /results, /calendar
- System: /api/system/state, toggle-lock, toggle-lifecycle, kill-switch
- Backtest: /api/backtest/run, /history, /compare
- Paper Trading: /api/paper-trading/portfolio, /trade, /reset, /history
- Marketplace: /api/marketplace/strategies, /publish, /subscribe, /rate
- Social: /api/social/leaderboard, /feed, /followers, /following, /profile
- Risk Analytics: /api/risk-analytics
- AI Brief: /api/ai-brief
- Risk Alerts: /api/risk-alerts/config (GET/POST), /check (POST), /history (GET)
- Risk Trends: /api/risk-trends (GET), /summary (GET), /snapshot (POST)
- Email Digest: /api/email-digest/preferences (GET/POST), /send (POST), /history (GET)
- Portfolio Optimizer: /api/portfolio-optimizer/assets (GET), /optimize (POST)

## Upcoming / Future Tasks
- [ ] Integrate real-money trading API (e.g., IBKR)

## Test Credentials
- Admin: admin@trading.com / Admin@123456
