# WTI AI Trading Platform - Product Requirements Document

## Original Problem Statement
Build an AI-driven crude oil (WTI) futures trading model with comprehensive regime detection, risk management, trading signals, options strategies, and a frontend dashboard.

## Architecture
```
/app/
├── backend/
│   ├── server.py                 # Main FastAPI app (~370 lines)
│   ├── deps.py                   # Shared dependencies
│   ├── routers/
│   │   ├── auth.py               # Authentication (login, register, logout, refresh, reset)
│   │   ├── bot.py                # Trading bot
│   │   ├── options.py            # Options trading
│   │   ├── replay.py             # Replay, simulation, comparison, optimizer
│   │   ├── analytics.py          # Fragility, events, risk-control, gate, scoring
│   │   ├── system.py             # System, market, trades, notifications, calendar, backtest
│   │   ├── exports_alerts.py     # CSV export + Price alerts
│   │   └── social.py             # Social/copy trading (leaderboard, share, follow, PvP, templates)
│   └── (trading_engine, ml_service, options_service, trading_bot, replay_engine, etc.)
├── frontend/
│   ├── public/manifest.json      # PWA configuration
│   ├── src/
│   │   ├── App.js                # Main React app (~1850 lines) with LoginPage gate
│   │   ├── App.css               # Global + Mobile responsive CSS
│   │   └── components/tabs/
│   │       ├── DashboardTab.jsx  # Dashboard (~764 lines)
│   │       ├── OptionsTab.jsx    # Options (~473 lines)
│   │       └── ReplayTab.jsx     # Replay + Simulation + Optimizer (~566 lines)
```

## All Completed Features (Tested 100% - Iteration 14)
- [x] **Mandatory Login Page** (full-page auth gate, no guest access, cookie-based persistence)
- [x] Real-time WebSocket market data + Multi-asset (CL, BZ, NG)
- [x] ML regime detection (GPT-4o) + Auto Strategy Selector
- [x] Options (6 strategies) + Payoff Diagrams + AI Auto-Selector
- [x] Human-in-the-loop Trading Bot (Paper Trading) + Tiered TP
- [x] Fragility/Event/Risk Control/Execution Gate/Signal Scoring
- [x] Strategy Replay (8 events) + Bot Simulation + Multi-Event Comparison
- [x] Strategy Optimizer (grid search 108+ combos, risk-adjusted scoring)
- [x] Social/Copy Trading (leaderboard, share strategies, follow/unfollow)
- [x] Strategy PvP Battle (backtest two configs across events, per-event breakdown)
- [x] Strategy Template Market (browse top strategies, one-click import to Replay or PvP)
- [x] Price Alerts + Trade CSV Export
- [x] Auth (JWT) + Push notifications + PWA (manifest.json, responsive CSS, safe-area)
- [x] Full refactoring: server.py 2155->370 lines, App.js 2849->1850 lines
- [x] Mobile PWA Enhancements (scrollable tabs, touch targets, notch-safe)

## Backlog
### P2
- [ ] Tradovate Live broker (requires user API keys)
### P3
- [ ] Mobile native enhancements
- [ ] User rating/review system for strategy templates
