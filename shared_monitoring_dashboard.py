"""
Security Monitoring Dashboard Backend
Real-time monitoring for risk status, kill switch events, and audit logs.
"""
import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Add shared_security to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shared_security'))

from shared_security import RiskEngine, RiskPolicies, AuditService, OrderLedger
from shared_security.models import OrderStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SecurityDashboard")


# ============= Data Models =============

class DashboardState(BaseModel):
    models: Dict[str, Dict[str, Any]]
    global_stats: Dict[str, Any]
    recent_alerts: List[Dict[str, Any]]
    kill_switch_events: List[Dict[str, Any]]


class ModelConfig(BaseModel):
    name: str
    display_name: str
    api_url: str
    enabled: bool = True


# ============= Dashboard Service =============

class DashboardService:
    """Aggregates data from all trading models for monitoring."""
    
    MODEL_CONFIGS = [
        ModelConfig(name="crypto", display_name="Crypto (BTC/ETH/SOL)", api_url="http://localhost:8001", enabled=True),
        ModelConfig(name="fx", display_name="FX (AUD/USD, NZD/USD)", api_url="http://localhost:8002", enabled=True),
        ModelConfig(name="bond", display_name="Bond (10Y)", api_url="http://localhost:8003", enabled=True),
        ModelConfig(name="oil", display_name="Oil (WTI/CL)", api_url="http://localhost:8004", enabled=True),
    ]
    
    def __init__(self):
        self.risk_engines: Dict[str, RiskEngine] = {}
        self.audit_services: Dict[str, AuditService] = {}
        self.alerts: List[Dict] = []
        self.kill_switch_events: List[Dict] = []
        self._connected_websockets: List[WebSocket] = []
        
        # Initialize local risk engines for demo
        self._init_demo_engines()
    
    def _init_demo_engines(self):
        """Initialize demo risk engines for each model."""
        configs = {
            "crypto": RiskPolicies(max_single_trade_notional_usd=50000, max_daily_loss_usd=-10000, kill_switch_max_drawdown_pct=15),
            "fx": RiskPolicies(max_single_trade_notional_usd=100000, max_daily_loss_usd=-5000, kill_switch_max_drawdown_pct=8),
            "bond": RiskPolicies(max_single_trade_notional_usd=200000, max_daily_loss_usd=-10000, kill_switch_max_drawdown_pct=5),
            "oil": RiskPolicies(max_single_trade_notional_usd=50000, max_daily_loss_usd=-5000, kill_switch_max_drawdown_pct=10),
        }
        
        for model_name, policy in configs.items():
            self.risk_engines[model_name] = RiskEngine(policies=policy)
    
    def get_model_status(self, model_name: str) -> Dict[str, Any]:
        """Get status for a specific model."""
        engine = self.risk_engines.get(model_name)
        if not engine:
            return {"error": "Model not found"}
        
        status = engine.get_status()
        return {
            "name": model_name,
            "kill_switch_active": status["kill_switch_active"],
            "kill_switch_reason": status.get("kill_switch_reason"),
            "policy_version": status["policy_version"],
            "policies": engine.policies.to_dict(),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all models."""
        return {name: self.get_model_status(name) for name in self.risk_engines}
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get aggregated global statistics."""
        active_kill_switches = sum(1 for e in self.risk_engines.values() if e.is_halted)
        total_models = len(self.risk_engines)
        
        return {
            "total_models": total_models,
            "active_models": total_models - active_kill_switches,
            "halted_models": active_kill_switches,
            "total_alerts_24h": len([a for a in self.alerts if self._is_recent(a.get("timestamp"), hours=24)]),
            "total_kill_switch_events_24h": len([e for e in self.kill_switch_events if self._is_recent(e.get("timestamp"), hours=24)]),
            "system_health": "HEALTHY" if active_kill_switches == 0 else "DEGRADED" if active_kill_switches < total_models else "CRITICAL",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _is_recent(self, timestamp_str: Optional[str], hours: int = 24) -> bool:
        """Check if timestamp is within recent hours."""
        if not timestamp_str:
            return False
        try:
            ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - ts) < timedelta(hours=hours)
        except:
            return False
    
    def trigger_kill_switch(self, model_name: str, reason: str) -> Dict[str, Any]:
        """Manually trigger kill switch for a model."""
        engine = self.risk_engines.get(model_name)
        if not engine:
            return {"success": False, "error": "Model not found"}
        
        engine._kill_switch_active = True
        engine._kill_switch_reason = reason
        
        event = {
            "event_id": f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "model": model_name,
            "triggered_by": "DASHBOARD_ADMIN",
            "trigger_reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.kill_switch_events.append(event)
        
        logger.warning(f"MANUAL KILL SWITCH: {model_name} - {reason}")
        return {"success": True, "event": event}
    
    def reset_kill_switch(self, model_name: str, reset_by: str, reason: str) -> Dict[str, Any]:
        """Reset kill switch for a model."""
        engine = self.risk_engines.get(model_name)
        if not engine:
            return {"success": False, "error": "Model not found"}
        
        success = engine.reset_kill_switch(reset_by, reason)
        
        if success:
            event = {
                "event_id": f"reset-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "model": model_name,
                "reset_by": reset_by,
                "reset_reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.kill_switch_events.append(event)
        
        return {"success": success}
    
    def add_alert(self, model: str, level: str, message: str):
        """Add an alert."""
        alert = {
            "id": f"alert-{len(self.alerts)+1}",
            "model": model,
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.alerts.append(alert)
        return alert
    
    async def broadcast_update(self):
        """Broadcast state update to all connected websockets."""
        state = {
            "type": "state_update",
            "data": {
                "models": self.get_all_statuses(),
                "global_stats": self.get_global_stats(),
                "recent_alerts": self.alerts[-20:],
                "kill_switch_events": self.kill_switch_events[-20:]
            }
        }
        
        disconnected = []
        for ws in self._connected_websockets:
            try:
                await ws.send_json(state)
            except:
                disconnected.append(ws)
        
        for ws in disconnected:
            self._connected_websockets.remove(ws)


# ============= FastAPI App =============

dashboard_service = DashboardService()

app = FastAPI(
    title="Security Monitoring Dashboard",
    description="Real-time monitoring for Financial Trading Security",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= REST Endpoints =============

@app.get("/")
async def root():
    """Dashboard home - returns HTML dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/api/status")
async def get_status():
    """Get all model statuses."""
    return {
        "models": dashboard_service.get_all_statuses(),
        "global_stats": dashboard_service.get_global_stats()
    }


@app.get("/api/status/{model_name}")
async def get_model_status(model_name: str):
    """Get status for specific model."""
    return dashboard_service.get_model_status(model_name)


@app.post("/api/kill-switch/{model_name}/trigger")
async def trigger_kill_switch(model_name: str, reason: str = "Manual trigger"):
    """Manually trigger kill switch."""
    result = dashboard_service.trigger_kill_switch(model_name, reason)
    await dashboard_service.broadcast_update()
    return result


@app.post("/api/kill-switch/{model_name}/reset")
async def reset_kill_switch(model_name: str, reset_by: str = "admin", reason: str = "Manual reset"):
    """Reset kill switch."""
    result = dashboard_service.reset_kill_switch(model_name, reset_by, reason)
    await dashboard_service.broadcast_update()
    return result


@app.get("/api/alerts")
async def get_alerts(limit: int = Query(default=50, le=200)):
    """Get recent alerts."""
    return {"alerts": dashboard_service.alerts[-limit:]}


@app.get("/api/kill-switch-events")
async def get_kill_switch_events(limit: int = Query(default=50, le=200)):
    """Get kill switch events."""
    return {"events": dashboard_service.kill_switch_events[-limit:]}


@app.post("/api/alerts")
async def create_alert(model: str, level: str, message: str):
    """Create a new alert."""
    alert = dashboard_service.add_alert(model, level, message)
    await dashboard_service.broadcast_update()
    return alert


# ============= WebSocket =============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    dashboard_service._connected_websockets.append(websocket)
    
    try:
        # Send initial state
        await websocket.send_json({
            "type": "initial_state",
            "data": {
                "models": dashboard_service.get_all_statuses(),
                "global_stats": dashboard_service.get_global_stats(),
                "recent_alerts": dashboard_service.alerts[-20:],
                "kill_switch_events": dashboard_service.kill_switch_events[-20:]
            }
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "trigger_kill_switch":
                    result = dashboard_service.trigger_kill_switch(
                        message.get("model"),
                        message.get("reason", "WebSocket trigger")
                    )
                    await dashboard_service.broadcast_update()
                elif message.get("type") == "reset_kill_switch":
                    result = dashboard_service.reset_kill_switch(
                        message.get("model"),
                        message.get("reset_by", "websocket"),
                        message.get("reason", "WebSocket reset")
                    )
                    await dashboard_service.broadcast_update()
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in dashboard_service._connected_websockets:
            dashboard_service._connected_websockets.remove(websocket)


# ============= Dashboard HTML =============

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security Monitoring Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .glass { backdrop-filter: blur(12px); background: rgba(15, 23, 42, 0.8); }
        .gradient-border { 
            background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899);
            padding: 1px;
        }
        .status-pulse { animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .kill-switch-active { 
            animation: shake 0.5s ease-in-out infinite;
            background: linear-gradient(135deg, #dc2626, #991b1b);
        }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-2px); }
            75% { transform: translateX(2px); }
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
    <div class="container mx-auto px-4 py-8 max-w-7xl">
        <!-- Header -->
        <header class="mb-8">
            <div class="flex items-center justify-between">
                <div>
                    <h1 class="text-3xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
                        Security Monitoring Dashboard
                    </h1>
                    <p class="text-slate-400 mt-1">Real-time Financial Trading Security</p>
                </div>
                <div id="connection-status" class="flex items-center gap-2 px-4 py-2 rounded-full glass">
                    <span id="status-dot" class="w-2 h-2 rounded-full bg-gray-500"></span>
                    <span id="status-text" class="text-sm">Connecting...</span>
                </div>
            </div>
        </header>

        <!-- Global Stats -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="glass rounded-xl p-6 border border-slate-700/50">
                <div class="text-slate-400 text-sm mb-2">System Health</div>
                <div id="system-health" class="text-2xl font-bold text-green-400">--</div>
            </div>
            <div class="glass rounded-xl p-6 border border-slate-700/50">
                <div class="text-slate-400 text-sm mb-2">Active Models</div>
                <div id="active-models" class="text-2xl font-bold text-blue-400">--</div>
            </div>
            <div class="glass rounded-xl p-6 border border-slate-700/50">
                <div class="text-slate-400 text-sm mb-2">Halted Models</div>
                <div id="halted-models" class="text-2xl font-bold text-red-400">--</div>
            </div>
            <div class="glass rounded-xl p-6 border border-slate-700/50">
                <div class="text-slate-400 text-sm mb-2">Alerts (24h)</div>
                <div id="alerts-24h" class="text-2xl font-bold text-amber-400">--</div>
            </div>
        </div>

        <!-- Model Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <!-- Crypto -->
            <div id="card-crypto" class="glass rounded-xl p-6 border border-slate-700/50 transition-all">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-lg bg-orange-500/20 flex items-center justify-center">
                            <span class="text-orange-400 text-xl">₿</span>
                        </div>
                        <div>
                            <h3 class="font-semibold">Crypto</h3>
                            <p class="text-slate-400 text-sm">BTC / ETH / SOL</p>
                        </div>
                    </div>
                    <div id="status-crypto" class="px-3 py-1 rounded-full text-sm bg-green-500/20 text-green-400">ACTIVE</div>
                </div>
                <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
                    <div>
                        <span class="text-slate-400">Max Trade</span>
                        <div class="font-mono">$50,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Daily Loss Limit</span>
                        <div class="font-mono text-red-400">-$10,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Kill Switch</span>
                        <div class="font-mono">15% DD</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Policy</span>
                        <div id="policy-crypto" class="font-mono text-xs text-slate-400 truncate">--</div>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="triggerKillSwitch('crypto')" class="flex-1 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition-colors">
                        Trigger Kill Switch
                    </button>
                    <button onclick="resetKillSwitch('crypto')" class="flex-1 px-4 py-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-lg text-sm transition-colors">
                        Reset
                    </button>
                </div>
            </div>

            <!-- FX -->
            <div id="card-fx" class="glass rounded-xl p-6 border border-slate-700/50 transition-all">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                            <span class="text-blue-400 text-xl">$</span>
                        </div>
                        <div>
                            <h3 class="font-semibold">FX</h3>
                            <p class="text-slate-400 text-sm">AUD/USD / NZD/USD</p>
                        </div>
                    </div>
                    <div id="status-fx" class="px-3 py-1 rounded-full text-sm bg-green-500/20 text-green-400">ACTIVE</div>
                </div>
                <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
                    <div>
                        <span class="text-slate-400">Max Trade</span>
                        <div class="font-mono">$100,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Daily Loss Limit</span>
                        <div class="font-mono text-red-400">-$5,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Kill Switch</span>
                        <div class="font-mono">8% DD</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Policy</span>
                        <div id="policy-fx" class="font-mono text-xs text-slate-400 truncate">--</div>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="triggerKillSwitch('fx')" class="flex-1 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition-colors">
                        Trigger Kill Switch
                    </button>
                    <button onclick="resetKillSwitch('fx')" class="flex-1 px-4 py-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-lg text-sm transition-colors">
                        Reset
                    </button>
                </div>
            </div>

            <!-- Bond -->
            <div id="card-bond" class="glass rounded-xl p-6 border border-slate-700/50 transition-all">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                            <span class="text-purple-400 text-xl">📊</span>
                        </div>
                        <div>
                            <h3 class="font-semibold">Bond</h3>
                            <p class="text-slate-400 text-sm">10Y Treasury</p>
                        </div>
                    </div>
                    <div id="status-bond" class="px-3 py-1 rounded-full text-sm bg-green-500/20 text-green-400">ACTIVE</div>
                </div>
                <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
                    <div>
                        <span class="text-slate-400">Max Trade</span>
                        <div class="font-mono">$200,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Daily Loss Limit</span>
                        <div class="font-mono text-red-400">-$10,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Kill Switch</span>
                        <div class="font-mono">5% DD</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Policy</span>
                        <div id="policy-bond" class="font-mono text-xs text-slate-400 truncate">--</div>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="triggerKillSwitch('bond')" class="flex-1 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition-colors">
                        Trigger Kill Switch
                    </button>
                    <button onclick="resetKillSwitch('bond')" class="flex-1 px-4 py-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-lg text-sm transition-colors">
                        Reset
                    </button>
                </div>
            </div>

            <!-- Oil -->
            <div id="card-oil" class="glass rounded-xl p-6 border border-slate-700/50 transition-all">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
                            <span class="text-amber-400 text-xl">🛢️</span>
                        </div>
                        <div>
                            <h3 class="font-semibold">Oil</h3>
                            <p class="text-slate-400 text-sm">WTI / CL Futures</p>
                        </div>
                    </div>
                    <div id="status-oil" class="px-3 py-1 rounded-full text-sm bg-green-500/20 text-green-400">ACTIVE</div>
                </div>
                <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
                    <div>
                        <span class="text-slate-400">Max Trade</span>
                        <div class="font-mono">$50,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Daily Loss Limit</span>
                        <div class="font-mono text-red-400">-$5,000</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Kill Switch</span>
                        <div class="font-mono">10% DD</div>
                    </div>
                    <div>
                        <span class="text-slate-400">Policy</span>
                        <div id="policy-oil" class="font-mono text-xs text-slate-400 truncate">--</div>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="triggerKillSwitch('oil')" class="flex-1 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition-colors">
                        Trigger Kill Switch
                    </button>
                    <button onclick="resetKillSwitch('oil')" class="flex-1 px-4 py-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-lg text-sm transition-colors">
                        Reset
                    </button>
                </div>
            </div>
        </div>

        <!-- Events Log -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Kill Switch Events -->
            <div class="glass rounded-xl p-6 border border-slate-700/50">
                <h3 class="font-semibold mb-4 flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-red-400 status-pulse"></span>
                    Kill Switch Events
                </h3>
                <div id="kill-switch-events" class="space-y-2 max-h-64 overflow-y-auto">
                    <div class="text-slate-500 text-sm">No events yet</div>
                </div>
            </div>

            <!-- Recent Alerts -->
            <div class="glass rounded-xl p-6 border border-slate-700/50">
                <h3 class="font-semibold mb-4 flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-amber-400 status-pulse"></span>
                    Recent Alerts
                </h3>
                <div id="alerts-log" class="space-y-2 max-h-64 overflow-y-auto">
                    <div class="text-slate-500 text-sm">No alerts yet</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        const wsUrl = `ws://${window.location.host}/ws`;

        function connect() {
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                document.getElementById('status-dot').className = 'w-2 h-2 rounded-full bg-green-400 status-pulse';
                document.getElementById('status-text').textContent = 'Connected';
            };
            
            ws.onclose = () => {
                document.getElementById('status-dot').className = 'w-2 h-2 rounded-full bg-red-400';
                document.getElementById('status-text').textContent = 'Disconnected';
                setTimeout(connect, 3000);
            };
            
            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                if (msg.type === 'initial_state' || msg.type === 'state_update') {
                    updateDashboard(msg.data);
                }
            };
        }

        function updateDashboard(data) {
            // Update global stats
            const stats = data.global_stats;
            document.getElementById('system-health').textContent = stats.system_health;
            document.getElementById('system-health').className = `text-2xl font-bold ${
                stats.system_health === 'HEALTHY' ? 'text-green-400' : 
                stats.system_health === 'DEGRADED' ? 'text-amber-400' : 'text-red-400'
            }`;
            document.getElementById('active-models').textContent = stats.active_models;
            document.getElementById('halted-models').textContent = stats.halted_models;
            document.getElementById('alerts-24h').textContent = stats.total_alerts_24h;

            // Update model statuses
            for (const [name, model] of Object.entries(data.models)) {
                const statusEl = document.getElementById(`status-${name}`);
                const cardEl = document.getElementById(`card-${name}`);
                const policyEl = document.getElementById(`policy-${name}`);
                
                if (statusEl) {
                    if (model.kill_switch_active) {
                        statusEl.textContent = 'HALTED';
                        statusEl.className = 'px-3 py-1 rounded-full text-sm bg-red-500/20 text-red-400 kill-switch-active';
                        cardEl.classList.add('border-red-500/50');
                    } else {
                        statusEl.textContent = 'ACTIVE';
                        statusEl.className = 'px-3 py-1 rounded-full text-sm bg-green-500/20 text-green-400';
                        cardEl.classList.remove('border-red-500/50');
                    }
                }
                
                if (policyEl) {
                    policyEl.textContent = model.policy_version;
                }
            }

            // Update kill switch events
            const eventsEl = document.getElementById('kill-switch-events');
            if (data.kill_switch_events.length > 0) {
                eventsEl.innerHTML = data.kill_switch_events.slice().reverse().map(e => `
                    <div class="p-3 bg-slate-800/50 rounded-lg text-sm">
                        <div class="flex justify-between">
                            <span class="font-medium text-red-400">${e.model?.toUpperCase() || 'SYSTEM'}</span>
                            <span class="text-slate-500 text-xs">${new Date(e.timestamp).toLocaleTimeString()}</span>
                        </div>
                        <div class="text-slate-300 mt-1">${e.trigger_reason || e.reset_reason || 'Event'}</div>
                    </div>
                `).join('');
            }

            // Update alerts
            const alertsEl = document.getElementById('alerts-log');
            if (data.recent_alerts.length > 0) {
                alertsEl.innerHTML = data.recent_alerts.slice().reverse().map(a => `
                    <div class="p-3 bg-slate-800/50 rounded-lg text-sm">
                        <div class="flex justify-between">
                            <span class="font-medium ${
                                a.level === 'critical' ? 'text-red-400' : 
                                a.level === 'warning' ? 'text-amber-400' : 'text-blue-400'
                            }">${a.model?.toUpperCase() || 'SYSTEM'}</span>
                            <span class="text-slate-500 text-xs">${new Date(a.timestamp).toLocaleTimeString()}</span>
                        </div>
                        <div class="text-slate-300 mt-1">${a.message}</div>
                    </div>
                `).join('');
            }
        }

        function triggerKillSwitch(model) {
            if (confirm(`Trigger kill switch for ${model.toUpperCase()}?`)) {
                ws.send(JSON.stringify({
                    type: 'trigger_kill_switch',
                    model: model,
                    reason: 'Manual dashboard trigger'
                }));
            }
        }

        function resetKillSwitch(model) {
            if (confirm(`Reset kill switch for ${model.toUpperCase()}?`)) {
                ws.send(JSON.stringify({
                    type: 'reset_kill_switch',
                    model: model,
                    reset_by: 'dashboard_admin',
                    reason: 'Manual dashboard reset'
                }));
            }
        }

        // Connect on load
        connect();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
