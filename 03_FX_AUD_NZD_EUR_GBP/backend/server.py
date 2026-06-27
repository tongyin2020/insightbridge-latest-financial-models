"""
FX Trading System - Main FastAPI Application
AUD/USD and NZD/USD Event-Driven Short-Term Trading System
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, Any

import httpx
import numpy as np
import bcrypt
import jwt as pyjwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

import database as db
from event_response_engine import EventResponseEngine, EventResponseManager, MarketSnapshot, PAIR_CONFIG
from execution_gate import ExecutionGate, GateInput, PAIR_RISK_CONFIG, REGIME_MULTIPLIERS
from strategy_monitor import StrategyMonitor

# ─── Auth Helpers ──────────────────────────────────────────────────────────────

JWT_ALGORITHM = "HS256"

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(user_id: str, email: str) -> str:
    from datetime import timedelta
    payload = {"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=60), "type": "access"}
    return pyjwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    from datetime import timedelta
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return pyjwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = pyjwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        from bson import ObjectId
        mongo_db = db.get_db()
        loop = asyncio.get_event_loop()
        user = await loop.run_in_executor(None, lambda: mongo_db.users.find_one({"_id": ObjectId(payload["sub"])}))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ─── Configuration ─────────────────────────────────────────────────────────────

class Settings:
    def __init__(self):
        self.twelve_data_api_key: str = os.getenv("TWELVE_DATA_API_KEY", "")
        self.dukascopy_api_url: str = os.getenv("DUKASCOPY_API_URL", "http://localhost:9090")
        self.ib_tws_host: str = os.getenv("IB_TWS_HOST", "127.0.0.1")
        self.ib_tws_port: int = int(os.getenv("IB_TWS_PORT", "7497"))
        self.emergent_llm_key: str = os.getenv("EMERGENT_LLM_KEY", "")
        self.host: str = "0.0.0.0"
        self.port: int = 8001
        self.pairs: list = ["AUD/USD", "NZD/USD"]
        self.api_poll_interval: int = 60
        self.sim_poll_interval: int = 3
        # Load Telegram config from env first, then override from MongoDB
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self._load_telegram_from_db()

    def _load_telegram_from_db(self):
        try:
            tg_config = db.load_telegram_config()
            if tg_config.get("bot_token"):
                self.telegram_bot_token = tg_config["bot_token"]
            if tg_config.get("chat_id"):
                self.telegram_chat_id = tg_config["chat_id"]
        except Exception as e:
            logger.warning(f"Failed to load Telegram config from DB: {e}")

    @property
    def use_simulated_data(self) -> bool:
        return not self.twelve_data_api_key or self.twelve_data_api_key == "your_twelve_data_key_here"

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token) and bool(self.telegram_chat_id)

    @property
    def ai_configured(self) -> bool:
        return bool(self.emergent_llm_key)

settings = Settings()

# ─── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fx_main")

# ─── Advanced Risk Control System (高级风险控制系统) ──────────────────────────────

class RiskControlSystem:
    """
    多层级风险控制系统 - 基于高杠杆交易风险控制方案
    核心原则: 预设边界、分层退出、极端情况下优先保命
    """
    
    # 系统状态
    STATUS_NORMAL = "NORMAL"              # 正常交易
    STATUS_WARNING = "WARNING"            # 预警状态
    STATUS_REDUCING = "REDUCING"          # 减仓中
    STATUS_EMERGENCY = "EMERGENCY"        # 紧急平仓
    STATUS_COOLDOWN = "COOLDOWN"          # 冷却期
    STATUS_GRADUATED_RESTART = "GRADUATED_RESTART"  # 渐进重启
    
    def __init__(self):
        # ═══ 多层级止损配置 ═══
        self.stop_loss_levels = {
            "warning_pips": 8,           # 警告点 (预警)
            "reduction_pips": 12,        # 减仓点 (减半仓位)
            "primary_stop_pips": 15,     # 主止损点 (止损)
            "disaster_stop_pips": 25,    # 灾难保护点 (强制清仓)
        }
        
        # ═══ 每日/每周风险限额 ═══
        self.daily_limits = {
            "max_daily_loss_pips": 50,      # 每日最大亏损 (pips)
            "max_daily_loss_percent": 2.0,  # 每日最大亏损 (账户%)
            "max_daily_trades": 10,         # 每日最大交易次数
            "max_consecutive_losses": 3,    # 最大连续亏损次数
        }
        
        self.weekly_limits = {
            "max_weekly_loss_pips": 150,    # 每周最大亏损 (pips)
            "max_weekly_loss_percent": 5.0, # 每周最大亏损 (账户%)
            "max_weekly_drawdown_percent": 8.0,  # 每周最大回撤
        }
        
        # ═══ 市场恶化检测阈值 ═══
        self.deterioration_thresholds = {
            "volatility_multiplier": 2.5,    # 波动率异常倍数
            "spread_multiplier": 3.0,        # 点差扩大倍数
            "rapid_move_pips": 15,           # 10秒内快速移动 (pips)
            "rapid_drawdown_percent": 1.0,   # 3分钟内快速回撤 (%)
            "depth_deterioration": 0.5,      # 市场深度下降比例
        }
        
        # ═══ 冷却期和渐进重启配置 ═══
        self.cooldown_config = {
            "emergency_cooldown_minutes": 30,    # 紧急冷却期
            "warning_cooldown_minutes": 10,      # 警告冷却期
            "restart_leverage_ratio": 0.3,       # 重启时杠杆比例 (30%)
            "graduated_steps": 3,                # 渐进恢复步数
            "step_duration_minutes": 15,         # 每步持续时间
        }
        
        # ═══ 仓位管理 ═══
        self.position_config = {
            "max_position_percent": 5.0,         # 单笔最大仓位 (账户%)
            "max_total_exposure_percent": 15.0,  # 总敞口上限 (账户%)
            "reduction_ratio": 0.5,              # 减仓比例
            "emergency_close_all": True,         # 紧急时全部平仓
        }
        
        # ═══ 当前状态 ═══
        self._status = self.STATUS_NORMAL
        self._status_since: float = time.time()
        self._cooldown_end: float = 0
        self._current_leverage_ratio: float = 1.0
        self._graduated_step: int = 0
        
        # ═══ 风险统计 ═══
        self._daily_stats = self._init_daily_stats()
        self._weekly_stats = self._init_weekly_stats()
        self._recent_prices: dict[str, list[dict]] = {"AUD/USD": [], "NZD/USD": []}
        self._alerts: list[dict] = []
        self._risk_events: list[dict] = []
        
    def _init_daily_stats(self) -> dict:
        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "total_pnl_pips": 0.0,
            "trade_count": 0,
            "consecutive_losses": 0,
            "peak_equity": 10000.0,  # 假设初始权益
            "current_equity": 10000.0,
            "max_drawdown_pips": 0.0,
            "warnings_triggered": 0,
            "emergencies_triggered": 0,
        }
    
    def _init_weekly_stats(self) -> dict:
        return {
            "week_start": datetime.now(timezone.utc).date().isoformat(),
            "total_pnl_pips": 0.0,
            "trade_count": 0,
            "max_drawdown_percent": 0.0,
            "emergency_count": 0,
        }
    
    def get_status(self) -> dict:
        """获取当前风险控制状态"""
        now = time.time()
        remaining_cooldown = max(0, self._cooldown_end - now)
        
        return {
            "status": self._status,
            "status_since": datetime.fromtimestamp(self._status_since, tz=timezone.utc).isoformat(),
            "remaining_cooldown_seconds": round(remaining_cooldown, 0),
            "current_leverage_ratio": round(self._current_leverage_ratio * 100, 1),
            "graduated_step": self._graduated_step,
            "can_trade": self._can_trade(),
            "risk_level": self._calculate_risk_level(),
            "daily_stats": self._daily_stats.copy(),
            "weekly_stats": self._weekly_stats.copy(),
            "recent_alerts": self._alerts[-10:],
            "stop_loss_levels": self.stop_loss_levels.copy(),
            "daily_limits": self.daily_limits.copy(),
        }
    
    def _can_trade(self) -> bool:
        """检查是否允许交易"""
        if self._status == self.STATUS_EMERGENCY:
            return False
        if self._status == self.STATUS_COOLDOWN and time.time() < self._cooldown_end:
            return False
        
        # 检查每日限额
        if abs(self._daily_stats["total_pnl_pips"]) >= self.daily_limits["max_daily_loss_pips"]:
            if self._daily_stats["total_pnl_pips"] < 0:
                return False
        if self._daily_stats["trade_count"] >= self.daily_limits["max_daily_trades"]:
            return False
        if self._daily_stats["consecutive_losses"] >= self.daily_limits["max_consecutive_losses"]:
            return False
        
        return True
    
    def _calculate_risk_level(self) -> dict:
        """计算当前风险等级 (0-100)"""
        risk_score = 0
        factors = []
        
        # 每日亏损占比
        daily_loss_ratio = abs(self._daily_stats["total_pnl_pips"]) / self.daily_limits["max_daily_loss_pips"]
        if self._daily_stats["total_pnl_pips"] < 0:
            daily_risk = min(daily_loss_ratio * 40, 40)
            risk_score += daily_risk
            if daily_loss_ratio > 0.5:
                factors.append(f"日亏损已达{daily_loss_ratio*100:.0f}%限额")
        
        # 连续亏损
        consecutive_ratio = self._daily_stats["consecutive_losses"] / self.daily_limits["max_consecutive_losses"]
        consecutive_risk = min(consecutive_ratio * 25, 25)
        risk_score += consecutive_risk
        if consecutive_ratio > 0.5:
            factors.append(f"连续亏损{self._daily_stats['consecutive_losses']}次")
        
        # 状态风险
        status_risk = {
            self.STATUS_NORMAL: 0,
            self.STATUS_WARNING: 15,
            self.STATUS_REDUCING: 25,
            self.STATUS_GRADUATED_RESTART: 10,
            self.STATUS_COOLDOWN: 5,
            self.STATUS_EMERGENCY: 35,
        }
        risk_score += status_risk.get(self._status, 0)
        
        # 风险等级
        if risk_score >= 80:
            level = "CRITICAL"
            color = "#FF3B30"
        elif risk_score >= 60:
            level = "HIGH"
            color = "#FF9500"
        elif risk_score >= 40:
            level = "ELEVATED"
            color = "#FFCC00"
        elif risk_score >= 20:
            level = "MODERATE"
            color = "#34C759"
        else:
            level = "LOW"
            color = "#007AFF"
        
        return {
            "score": round(risk_score, 1),
            "level": level,
            "color": color,
            "factors": factors,
        }
    
    def check_entry_allowed(self, pair: str, direction: str, spread_pips: float) -> dict:
        """检查是否允许入场"""
        result = {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "adjusted_size_ratio": self._current_leverage_ratio,
        }
        
        # 基本检查
        if not self._can_trade():
            result["allowed"] = False
            result["reasons"].append(f"交易已暂停: {self._status}")
            return result
        
        # 点差检查
        normal_spread = 1.5  # 正常点差
        if spread_pips > normal_spread * self.deterioration_thresholds["spread_multiplier"]:
            result["allowed"] = False
            result["reasons"].append(f"点差异常扩大: {spread_pips:.1f} pips")
            self._add_alert("SPREAD_WARNING", f"{pair} 点差扩大至 {spread_pips:.1f} pips")
        elif spread_pips > normal_spread * 2:
            result["warnings"].append(f"点差偏高: {spread_pips:.1f} pips")
        
        # 渐进重启期间调整仓位
        if self._status == self.STATUS_GRADUATED_RESTART:
            result["adjusted_size_ratio"] = self.cooldown_config["restart_leverage_ratio"] * (1 + self._graduated_step * 0.2)
            result["warnings"].append(f"渐进重启中，仓位调整至{result['adjusted_size_ratio']*100:.0f}%")
        
        return result
    
    def check_market_deterioration(self, pair: str, current_price: float, spread_pips: float) -> dict:
        """检测市场恶化情况"""
        result = {
            "deteriorated": False,
            "triggers": [],
            "severity": "NONE",
            "action_required": None,
        }
        
        # 存储最近价格
        now = time.time()
        if pair not in self._recent_prices:
            self._recent_prices[pair] = []
        self._recent_prices[pair].append({"price": current_price, "time": now, "spread": spread_pips})
        
        # 只保留最近60秒的数据
        self._recent_prices[pair] = [p for p in self._recent_prices[pair] if now - p["time"] < 60]
        
        if len(self._recent_prices[pair]) < 3:
            return result
        
        prices_10s = [p for p in self._recent_prices[pair] if now - p["time"] < 10]
        if len(prices_10s) >= 2:
            # 10秒内价格变动
            price_move = abs(prices_10s[-1]["price"] - prices_10s[0]["price"]) * 10000
            if price_move >= self.deterioration_thresholds["rapid_move_pips"]:
                result["deteriorated"] = True
                result["triggers"].append(f"10秒内价格变动{price_move:.1f}pips")
        
        # 点差检查
        avg_spread = np.mean([p["spread"] for p in self._recent_prices[pair][-10:]])
        if spread_pips > avg_spread * self.deterioration_thresholds["spread_multiplier"]:
            result["deteriorated"] = True
            result["triggers"].append(f"点差扩大{spread_pips/avg_spread:.1f}倍")
        
        # 确定严重程度和行动
        if result["deteriorated"]:
            if len(result["triggers"]) >= 2:
                result["severity"] = "CRITICAL"
                result["action_required"] = "EMERGENCY_CLOSE"
            else:
                result["severity"] = "HIGH"
                result["action_required"] = "REDUCE_POSITION"
            
            self._add_alert("MARKET_DETERIORATION", f"{pair}: {', '.join(result['triggers'])}")
        
        return result
    
    def process_trade_result(self, pnl_pips: float, pair: str) -> dict:
        """处理交易结果，更新统计并检查是否触发保护"""
        self._daily_stats["total_pnl_pips"] += pnl_pips
        self._daily_stats["trade_count"] += 1
        self._weekly_stats["total_pnl_pips"] += pnl_pips
        self._weekly_stats["trade_count"] += 1
        
        action = None
        
        if pnl_pips < 0:
            self._daily_stats["consecutive_losses"] += 1
            
            # 检查连续亏损
            if self._daily_stats["consecutive_losses"] >= self.daily_limits["max_consecutive_losses"]:
                action = self._trigger_warning(f"连续亏损{self._daily_stats['consecutive_losses']}次")
        else:
            self._daily_stats["consecutive_losses"] = 0
        
        # 检查每日亏损限额
        if self._daily_stats["total_pnl_pips"] <= -self.daily_limits["max_daily_loss_pips"]:
            action = self._trigger_emergency("日亏损达到限额")
        elif self._daily_stats["total_pnl_pips"] <= -self.daily_limits["max_daily_loss_pips"] * 0.7:
            action = self._trigger_warning("日亏损接近限额70%")
        
        # 更新峰值和回撤
        self._daily_stats["current_equity"] += pnl_pips * 10  # 假设每pip=$10
        if self._daily_stats["current_equity"] > self._daily_stats["peak_equity"]:
            self._daily_stats["peak_equity"] = self._daily_stats["current_equity"]
        
        drawdown = self._daily_stats["peak_equity"] - self._daily_stats["current_equity"]
        self._daily_stats["max_drawdown_pips"] = max(self._daily_stats["max_drawdown_pips"], drawdown / 10)
        
        return {
            "pnl_pips": pnl_pips,
            "daily_total": self._daily_stats["total_pnl_pips"],
            "consecutive_losses": self._daily_stats["consecutive_losses"],
            "action_triggered": action,
            "status": self._status,
        }
    
    def check_position_risk(self, pair: str, entry_price: float, current_price: float, direction: str) -> dict:
        """检查持仓风险，返回应采取的行动"""
        if direction == "BUY":
            pnl_pips = (current_price - entry_price) * 10000
        else:
            pnl_pips = (entry_price - current_price) * 10000
        
        abs_pnl = abs(pnl_pips)
        
        result = {
            "pnl_pips": round(pnl_pips, 1),
            "action": None,
            "level": "NORMAL",
            "message": None,
        }
        
        if pnl_pips >= 0:
            return result
        
        # 多层级止损检查
        if abs_pnl >= self.stop_loss_levels["disaster_stop_pips"]:
            result["action"] = "EMERGENCY_CLOSE"
            result["level"] = "DISASTER"
            result["message"] = f"触发灾难保护点 ({abs_pnl:.1f} >= {self.stop_loss_levels['disaster_stop_pips']} pips)"
            self._trigger_emergency(f"{pair} 触发灾难保护")
            
        elif abs_pnl >= self.stop_loss_levels["primary_stop_pips"]:
            result["action"] = "STOP_LOSS"
            result["level"] = "STOP"
            result["message"] = f"触发主止损点 ({abs_pnl:.1f} >= {self.stop_loss_levels['primary_stop_pips']} pips)"
            
        elif abs_pnl >= self.stop_loss_levels["reduction_pips"]:
            result["action"] = "REDUCE_50"
            result["level"] = "REDUCTION"
            result["message"] = f"触发减仓点 ({abs_pnl:.1f} >= {self.stop_loss_levels['reduction_pips']} pips)"
            self._add_alert("REDUCTION_TRIGGERED", f"{pair} 触发减仓")
            
        elif abs_pnl >= self.stop_loss_levels["warning_pips"]:
            result["action"] = "WARNING"
            result["level"] = "WARNING"
            result["message"] = f"触发警告点 ({abs_pnl:.1f} >= {self.stop_loss_levels['warning_pips']} pips)"
            
        return result
    
    def _trigger_warning(self, reason: str) -> str:
        """触发警告状态"""
        if self._status not in (self.STATUS_EMERGENCY, self.STATUS_COOLDOWN):
            self._status = self.STATUS_WARNING
            self._status_since = time.time()
            self._daily_stats["warnings_triggered"] += 1
            self._add_alert("WARNING", reason)
            self._add_risk_event("WARNING", reason)
        return "WARNING"
    
    def _trigger_emergency(self, reason: str) -> str:
        """触发紧急平仓"""
        self._status = self.STATUS_EMERGENCY
        self._status_since = time.time()
        self._cooldown_end = time.time() + self.cooldown_config["emergency_cooldown_minutes"] * 60
        self._daily_stats["emergencies_triggered"] += 1
        self._weekly_stats["emergency_count"] += 1
        self._add_alert("EMERGENCY", reason)
        self._add_risk_event("EMERGENCY", reason)
        return "EMERGENCY"
    
    def start_graduated_restart(self) -> dict:
        """开始渐进重启"""
        if self._status != self.STATUS_COOLDOWN or time.time() < self._cooldown_end:
            return {"error": "冷却期未结束"}
        
        self._status = self.STATUS_GRADUATED_RESTART
        self._status_since = time.time()
        self._graduated_step = 0
        self._current_leverage_ratio = self.cooldown_config["restart_leverage_ratio"]
        self._add_alert("GRADUATED_RESTART", f"开始渐进重启，初始杠杆{self._current_leverage_ratio*100:.0f}%")
        
        return self.get_status()
    
    def advance_graduated_step(self) -> dict:
        """推进渐进重启步骤"""
        if self._status != self.STATUS_GRADUATED_RESTART:
            return {"error": "不在渐进重启状态"}
        
        self._graduated_step += 1
        
        if self._graduated_step >= self.cooldown_config["graduated_steps"]:
            self._status = self.STATUS_NORMAL
            self._current_leverage_ratio = 1.0
            self._graduated_step = 0
            self._add_alert("NORMAL_RESTORED", "交易恢复正常")
        else:
            step_increment = (1.0 - self.cooldown_config["restart_leverage_ratio"]) / self.cooldown_config["graduated_steps"]
            self._current_leverage_ratio = self.cooldown_config["restart_leverage_ratio"] + step_increment * self._graduated_step
            self._add_alert("GRADUATED_STEP", f"渐进重启第{self._graduated_step}步，杠杆{self._current_leverage_ratio*100:.0f}%")
        
        return self.get_status()
    
    def end_cooldown(self) -> dict:
        """手动结束冷却期（进入渐进重启）"""
        if self._status == self.STATUS_EMERGENCY:
            self._status = self.STATUS_COOLDOWN
            self._add_alert("COOLDOWN_START", "进入冷却期")
        
        if self._status == self.STATUS_COOLDOWN:
            return self.start_graduated_restart()
        
        return self.get_status()
    
    def reset_daily_stats(self) -> dict:
        """重置每日统计（每日开盘时调用）"""
        self._daily_stats = self._init_daily_stats()
        if self._status == self.STATUS_WARNING:
            self._status = self.STATUS_NORMAL
        return self._daily_stats
    
    def reset_to_normal(self) -> dict:
        """强制重置到正常状态（紧急操作）"""
        self._status = self.STATUS_NORMAL
        self._status_since = time.time()
        self._current_leverage_ratio = 1.0
        self._graduated_step = 0
        self._cooldown_end = 0
        self._add_alert("MANUAL_RESET", "手动重置到正常状态")
        return self.get_status()
    
    def update_stop_loss_levels(self, levels: dict) -> dict:
        """更新止损层级"""
        for key, value in levels.items():
            if key in self.stop_loss_levels:
                self.stop_loss_levels[key] = float(value)
        return self.stop_loss_levels
    
    def update_daily_limits(self, limits: dict) -> dict:
        """更新每日限额"""
        for key, value in limits.items():
            if key in self.daily_limits:
                self.daily_limits[key] = float(value) if "percent" in key or "pips" in key else int(value)
        return self.daily_limits
    
    def _add_alert(self, alert_type: str, message: str) -> None:
        """添加警报"""
        alert = {
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._alerts.append(alert)
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]
        logger.warning(f"[RISK ALERT] {alert_type}: {message}")
    
    def _add_risk_event(self, event_type: str, reason: str) -> None:
        """记录风险事件"""
        event = {
            "type": event_type,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "daily_stats": self._daily_stats.copy(),
            "status_before": self._status,
        }
        self._risk_events.append(event)
        if len(self._risk_events) > 50:
            self._risk_events = self._risk_events[-50:]
    
    def get_risk_events(self) -> list:
        """获取风险事件历史"""
        return self._risk_events.copy()
    
    def get_capital_protection_summary(self) -> dict:
        """获取资金保护总结"""
        daily = self._daily_stats
        weekly = self._weekly_stats
        
        daily_loss_used = abs(daily["total_pnl_pips"]) / self.daily_limits["max_daily_loss_pips"] * 100 if daily["total_pnl_pips"] < 0 else 0
        weekly_loss_used = abs(weekly["total_pnl_pips"]) / self.weekly_limits["max_weekly_loss_pips"] * 100 if weekly["total_pnl_pips"] < 0 else 0
        
        return {
            "daily_pnl": round(daily["total_pnl_pips"], 1),
            "daily_limit": self.daily_limits["max_daily_loss_pips"],
            "daily_loss_used_percent": round(daily_loss_used, 1),
            "daily_trades_used": f"{daily['trade_count']}/{self.daily_limits['max_daily_trades']}",
            "consecutive_losses": daily["consecutive_losses"],
            "max_consecutive_allowed": self.daily_limits["max_consecutive_losses"],
            "weekly_pnl": round(weekly["total_pnl_pips"], 1),
            "weekly_limit": self.weekly_limits["max_weekly_loss_pips"],
            "weekly_loss_used_percent": round(weekly_loss_used, 1),
            "current_leverage_ratio": round(self._current_leverage_ratio * 100, 1),
            "status": self._status,
            "warnings_today": daily["warnings_triggered"],
            "emergencies_today": daily["emergencies_triggered"],
            "emergencies_this_week": weekly["emergency_count"],
            "capital_safety_score": self._calculate_capital_safety_score(),
        }
    
    def _calculate_capital_safety_score(self) -> dict:
        """计算资金安全评分 (0-100, 越高越安全)"""
        score = 100
        factors = []
        
        # 每日亏损扣分
        if self._daily_stats["total_pnl_pips"] < 0:
            loss_ratio = abs(self._daily_stats["total_pnl_pips"]) / self.daily_limits["max_daily_loss_pips"]
            deduction = min(loss_ratio * 30, 30)
            score -= deduction
            if loss_ratio > 0.3:
                factors.append(f"日亏损 {self._daily_stats['total_pnl_pips']:.1f} pips")
        
        # 连续亏损扣分
        if self._daily_stats["consecutive_losses"] > 0:
            deduction = self._daily_stats["consecutive_losses"] * 10
            score -= min(deduction, 30)
            if self._daily_stats["consecutive_losses"] >= 2:
                factors.append(f"连续亏损 {self._daily_stats['consecutive_losses']} 次")
        
        # 状态扣分
        status_deductions = {
            self.STATUS_WARNING: 10,
            self.STATUS_REDUCING: 15,
            self.STATUS_EMERGENCY: 25,
            self.STATUS_COOLDOWN: 5,
            self.STATUS_GRADUATED_RESTART: 5,
        }
        score -= status_deductions.get(self._status, 0)
        
        # 紧急事件扣分
        score -= self._daily_stats["emergencies_triggered"] * 15
        
        score = max(0, min(100, score))
        
        if score >= 80:
            level = "安全"
            color = "#34C759"
        elif score >= 60:
            level = "正常"
            color = "#007AFF"
        elif score >= 40:
            level = "注意"
            color = "#FFCC00"
        elif score >= 20:
            level = "警告"
            color = "#FF9500"
        else:
            level = "危险"
            color = "#FF3B30"
        
        return {
            "score": round(score, 0),
            "level": level,
            "color": color,
            "factors": factors,
        }


# ─── In-Memory Storage (替代SQLite简化部署) ────────────────────────────────────

class Storage:
    DEFAULT_SETTINGS = {
        "aud_usd_direction": "LONG_ONLY",
        "nzd_usd_direction": "LONG_ONLY",
        "override_mode": "NORMAL",
        "max_hold_minutes": "30",
        "stop_loss_pips": "15",
        "take_profit_pips": "25",
        "spread_threshold_pips": "3.0",
        "event_a_cooldown_seconds": "30",
        "event_b_cooldown_seconds": "20",
        "kill_switch": "false",
    }

    def __init__(self):
        # Ephemeral real-time data (stays in memory)
        self.prices: dict[str, list[dict]] = {"AUD/USD": [], "NZD/USD": []}
        self.signals: list[dict] = []
        self.trades: list[dict] = []
        self.logs: list[dict] = []
        # Persistent data loaded from MongoDB
        self.settings: dict[str, str] = db.load_settings(self.DEFAULT_SETTINGS)
        self.ai_analyses: list[dict] = db.get_ai_analyses(20)
        self.events: list[dict] = []
        self.backtest_results: list[dict] = db.get_backtest_results()
        self.confirmation_stats: dict = db.get_confirmation_stats()
        # 高级风险控制系统
        self.risk_control = RiskControlSystem()
        self._seed_events()
        if not self.backtest_results:
            self._seed_backtest_data()

    def update_setting(self, key: str, value: str):
        self.settings[key] = value
        db.save_setting(key, value)

    def add_ai_analysis(self, analysis: dict):
        self.ai_analyses.insert(0, analysis)
        self.ai_analyses = self.ai_analyses[:20]
        db.store_ai_analysis(analysis)

    def _seed_events(self):
        now = datetime.now(timezone.utc)
        sample_events = [
            {"title": "RBA Interest Rate Decision", "country": "AU", "impact": "A", "pair_affected": "AUD/USD"},
            {"title": "AU Employment Change", "country": "AU", "impact": "A", "pair_affected": "AUD/USD"},
            {"title": "RBNZ Interest Rate Decision", "country": "NZ", "impact": "A", "pair_affected": "NZD/USD"},
            {"title": "NZ CPI q/q", "country": "NZ", "impact": "A", "pair_affected": "NZD/USD"},
            {"title": "China Manufacturing PMI", "country": "CN", "impact": "B", "pair_affected": "AUD/USD"},
            {"title": "US Non-Farm Payrolls", "country": "US", "impact": "A", "pair_affected": "AUD/USD"},
            {"title": "FOMC Statement", "country": "US", "impact": "A", "pair_affected": "NZD/USD"},
            {"title": "AU Trade Balance", "country": "AU", "impact": "B", "pair_affected": "AUD/USD"},
        ]
        for i, ev in enumerate(sample_events):
            event_time = datetime.fromtimestamp(now.timestamp() + (i + 1) * 3600 * 6, tz=timezone.utc)
            self.events.append({
                "id": i + 1,
                "title": ev["title"],
                "country": ev["country"],
                "impact": ev["impact"],
                "datetime": event_time.isoformat(),
                "actual": "",
                "forecast": f"{random.uniform(-0.5, 2.5):.1f}%",
                "previous": f"{random.uniform(-0.5, 2.5):.1f}%",
                "pair_affected": ev["pair_affected"],
            })

    def _seed_backtest_data(self):
        """Seed historical backtest data for demonstration"""
        now = datetime.now(timezone.utc)
        event_types = [
            ("RBA Interest Rate Decision", "A", "AUD/USD"),
            ("RBNZ Interest Rate Decision", "A", "NZD/USD"),
            ("US Non-Farm Payrolls", "A", "AUD/USD"),
            ("FOMC Statement", "A", "NZD/USD"),
            ("China Manufacturing PMI", "B", "AUD/USD"),
            ("AU Employment Change", "A", "AUD/USD"),
            ("NZ CPI q/q", "A", "NZD/USD"),
            ("RBA Governor Speech", "B", "AUD/USD"),
        ]
        
        for i in range(50):
            event = random.choice(event_types)
            event_title, event_level, pair = event
            
            # Simulate confirmation results based on realistic probabilities
            # A-level events: ~65% success rate for direction confirmation
            # B-level events: ~55% success rate
            base_success_rate = 0.65 if event_level == "A" else 0.55
            is_success = random.random() < base_success_rate
            
            direction = random.choice(["BUY", "SELL"])
            price_before = 0.6300 if "AUD" in pair else 0.5700
            price_change = random.uniform(0.0005, 0.0025) * (1 if direction == "BUY" else -1)
            price_after = price_before + price_change
            
            # Calculate PnL based on success
            if is_success:
                pnl_pips = random.uniform(5, 25)
            else:
                pnl_pips = random.uniform(-15, -3)
            
            # Update stats
            self.confirmation_stats[pair][event_level]["total"] += 1
            if is_success:
                self.confirmation_stats[pair][event_level]["success"] += 1
            
            backtest_record = {
                "id": i + 1,
                "timestamp": datetime.fromtimestamp(now.timestamp() - (50 - i) * 86400, tz=timezone.utc).isoformat(),
                "pair": pair,
                "event_title": event_title,
                "event_level": event_level,
                "direction_confirmed": direction,
                "price_before_event": round(price_before, 5),
                "price_at_30s": round(price_before + price_change * 0.4, 5),
                "price_at_exit": round(price_after, 5),
                "confirmation_success": is_success,
                "pnl_pips": round(pnl_pips, 1),
                "hold_duration_minutes": random.randint(8, 28),
                "spread_at_entry": round(random.uniform(1.2, 2.8), 1),
            }
            self.backtest_results.append(backtest_record)
        # Persist seeded data to MongoDB
        db.store_backtest_results(self.backtest_results)
        self.confirmation_stats = db.get_confirmation_stats()

storage = Storage()

# ─── Technical Indicators ──────────────────────────────────────────────────────

class TechnicalIndicators:
    @staticmethod
    def calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
        sma = np.full_like(prices, np.nan, dtype=np.float64)
        if len(prices) < period:
            return sma
        cumsum = np.cumsum(prices, dtype=np.float64)
        cumsum[period:] = cumsum[period:] - cumsum[:-period]
        sma[period - 1:] = cumsum[period - 1:] / period
        return sma

    @staticmethod
    def calculate_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
        n = len(closes)
        adx = np.full(n, np.nan, dtype=np.float64)
        if n < period * 2:
            return adx

        tr = np.zeros(n, dtype=np.float64)
        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr[i] = max(hl, hc, lc)

        plus_dm = np.zeros(n, dtype=np.float64)
        minus_dm = np.zeros(n, dtype=np.float64)
        for i in range(1, n):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move

        atr_smooth = np.zeros(n, dtype=np.float64)
        plus_dm_smooth = np.zeros(n, dtype=np.float64)
        minus_dm_smooth = np.zeros(n, dtype=np.float64)

        if period < n:
            atr_smooth[period] = np.sum(tr[1:period + 1])
            plus_dm_smooth[period] = np.sum(plus_dm[1:period + 1])
            minus_dm_smooth[period] = np.sum(minus_dm[1:period + 1])

            for i in range(period + 1, n):
                atr_smooth[i] = atr_smooth[i - 1] - (atr_smooth[i - 1] / period) + tr[i]
                plus_dm_smooth[i] = plus_dm_smooth[i - 1] - (plus_dm_smooth[i - 1] / period) + plus_dm[i]
                minus_dm_smooth[i] = minus_dm_smooth[i - 1] - (minus_dm_smooth[i - 1] / period) + minus_dm[i]

        plus_di = np.zeros(n, dtype=np.float64)
        minus_di = np.zeros(n, dtype=np.float64)
        dx = np.zeros(n, dtype=np.float64)

        for i in range(period, n):
            if atr_smooth[i] != 0:
                plus_di[i] = 100.0 * plus_dm_smooth[i] / atr_smooth[i]
                minus_di[i] = 100.0 * minus_dm_smooth[i] / atr_smooth[i]
            di_sum = plus_di[i] + minus_di[i]
            if di_sum != 0:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

        start = period * 2
        if start < n:
            adx[start] = np.mean(dx[period:start + 1])
            for i in range(start + 1, n):
                adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return adx

    @staticmethod
    def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
        n = len(closes)
        atr = np.full(n, np.nan, dtype=np.float64)
        if n < period + 1:
            return atr

        tr = np.zeros(n, dtype=np.float64)
        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr[i] = max(hl, hc, lc)

        atr[period] = np.mean(tr[1:period + 1])
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        return atr

    @staticmethod
    def calculate_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
        n = len(closes)
        rsi = np.full(n, np.nan, dtype=np.float64)
        if n < period + 1:
            return rsi

        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        if avg_loss == 0:
            rsi[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    @staticmethod
    def calculate_bollinger(closes: np.ndarray, period: int = 20, std_dev: float = 2.0):
        n = len(closes)
        middle = np.full(n, np.nan, dtype=np.float64)
        upper = np.full(n, np.nan, dtype=np.float64)
        lower = np.full(n, np.nan, dtype=np.float64)

        if n < period:
            return upper, middle, lower

        for i in range(period - 1, n):
            window = closes[i - period + 1: i + 1]
            mean = np.mean(window)
            std = np.std(window, ddof=0)
            middle[i] = mean
            upper[i] = mean + std_dev * std
            lower[i] = mean - std_dev * std

        return upper, middle, lower

indicators = TechnicalIndicators()

# ─── Event Engine ──────────────────────────────────────────────────────────────

class EventEngine:
    VALID_STATES = ("NORMAL", "PRE_EVENT", "COOLDOWN", "CONFIRMING", "POST_EVENT")
    COOLDOWN_SECONDS = {"A": 30, "B": 20, "C": 0}
    CONFIRMATION_WINDOW_SECONDS = 30

    def __init__(self):
        self._state: str = "NORMAL"
        self._event_level: Optional[str] = None
        self._cooldown_end: float = 0.0
        self._confirmation_end: float = 0.0
        self._confirmed_direction: dict[str, str] = {}
        self._current_event_title: str = ""
        self._transition_task: Optional[asyncio.Task] = None

    def get_event_state(self) -> dict:
        now = time.time()
        remaining = 0.0
        if self._state == "COOLDOWN" and self._cooldown_end > now:
            remaining = self._cooldown_end - now
        elif self._state == "CONFIRMING" and self._confirmation_end > now:
            remaining = self._confirmation_end - now

        return {
            "state": self._state,
            "event_level": self._event_level,
            "event_title": self._current_event_title,
            "remaining_seconds": round(remaining, 1),
            "confirmed_direction": dict(self._confirmed_direction),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @property
    def state(self) -> str:
        return self._state

    async def start_event_cooldown(self, event_level: str, title: str = "Manual trigger") -> dict:
        if event_level not in self.COOLDOWN_SECONDS:
            return {"error": f"Invalid event level: {event_level}"}

        cooldown_secs = self.COOLDOWN_SECONDS[event_level]
        if cooldown_secs == 0:
            return self.get_event_state()

        self._event_level = event_level
        self._current_event_title = title
        self._state = "COOLDOWN"
        self._cooldown_end = time.time() + cooldown_secs
        self._confirmed_direction = {}

        if self._transition_task and not self._transition_task.done():
            self._transition_task.cancel()

        self._transition_task = asyncio.create_task(self._auto_transition_to_confirming(cooldown_secs))
        return self.get_event_state()

    async def _auto_transition_to_confirming(self, cooldown_secs: float) -> None:
        try:
            await asyncio.sleep(cooldown_secs)
            if self._state == "COOLDOWN":
                self._state = "CONFIRMING"
                self._confirmation_end = time.time() + self.CONFIRMATION_WINDOW_SECONDS
                self._transition_task = asyncio.create_task(
                    self._auto_transition_to_post_event(self.CONFIRMATION_WINDOW_SECONDS)
                )
        except asyncio.CancelledError:
            pass

    async def _auto_transition_to_post_event(self, confirmation_secs: float) -> None:
        try:
            await asyncio.sleep(confirmation_secs)
            if self._state == "CONFIRMING":
                self._state = "POST_EVENT"
                await asyncio.sleep(5)
                if self._state == "POST_EVENT":
                    self._state = "NORMAL"
                    self._event_level = None
                    self._current_event_title = ""
        except asyncio.CancelledError:
            pass

    async def confirm_direction(self, pair: str, prices_before: list[float], prices_after: list[float]) -> dict:
        if not prices_before or not prices_after:
            return {"pair": pair, "direction": "NEUTRAL", "confidence": 0, "reason": "Insufficient data"}

        before_arr = np.array(prices_before, dtype=np.float64)
        after_arr = np.array(prices_after, dtype=np.float64)

        avg_before = np.mean(before_arr[-5:]) if len(before_arr) >= 5 else np.mean(before_arr)
        avg_after = np.mean(after_arr[-5:]) if len(after_arr) >= 5 else np.mean(after_arr)
        net_change = avg_after - avg_before
        net_change_pips = net_change * 10000

        direction = "NEUTRAL"
        confidence = 0.0

        if abs(net_change_pips) >= 3:
            direction = "BUY" if net_change > 0 else "SELL"
            confidence = min(abs(net_change_pips) * 5, 95)

        self._confirmed_direction[pair] = direction

        if self._state == "CONFIRMING":
            self._state = "POST_EVENT"
            if self._transition_task and not self._transition_task.done():
                self._transition_task.cancel()
            self._transition_task = asyncio.create_task(self._return_to_normal(5))

        return {
            "pair": pair,
            "direction": direction,
            "confidence": round(confidence, 1),
            "net_change_pips": round(net_change_pips, 1),
        }

    async def _return_to_normal(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if self._state == "POST_EVENT":
                self._state = "NORMAL"
                self._event_level = None
                self._current_event_title = ""
        except asyncio.CancelledError:
            pass

    async def reset(self) -> None:
        if self._transition_task and not self._transition_task.done():
            self._transition_task.cancel()
        self._state = "NORMAL"
        self._event_level = None
        self._current_event_title = ""
        self._cooldown_end = 0.0
        self._confirmation_end = 0.0
        self._confirmed_direction = {}

event_engine = EventEngine()
event_response = EventResponseManager(["AUD/USD", "NZD/USD"])
execution_gate = ExecutionGate()
strategy_monitor = StrategyMonitor(["AUD/USD", "NZD/USD"])

# ─── Market Data Service ───────────────────────────────────────────────────────

class MarketDataService:
    BASE_PRICES = {"AUD/USD": 0.6300, "NZD/USD": 0.5700}

    def __init__(self):
        self._sim_prices: dict[str, float] = {pair: base for pair, base in self.BASE_PRICES.items()}
        self._connected_clients: list[asyncio.Queue] = []
        self._running = False
        self._http_client: Optional[httpx.AsyncClient] = None

    def register_client(self, queue: asyncio.Queue) -> None:
        self._connected_clients.append(queue)

    def unregister_client(self, queue: asyncio.Queue) -> None:
        if queue in self._connected_clients:
            self._connected_clients.remove(queue)

    async def broadcast(self, message: dict) -> None:
        dead: list[asyncio.Queue] = []
        for q in self._connected_clients:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._connected_clients.remove(q)

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=15.0)
        return self._http_client

    async def fetch_price_live(self, pair: str) -> Optional[dict]:
        client = await self._get_http_client()
        symbol = pair.replace("/", "")
        try:
            resp = await client.get(
                "https://api.twelvedata.com/price",
                params={"symbol": symbol, "apikey": settings.twelve_data_api_key},
            )
            data = resp.json()
            if "price" not in data:
                return None
            mid = float(data["price"])
            half_spread = random.uniform(0.00006, 0.000125)
            return {
                "pair": pair,
                "bid": round(mid - half_spread, 5),
                "ask": round(mid + half_spread, 5),
                "mid": round(mid, 5),
                "spread_pips": round(half_spread * 2 * 10000, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "twelvedata",
            }
        except Exception as e:
            logger.error(f"Failed to fetch {pair}: {e}")
            return None

    def fetch_price_simulated(self, pair: str) -> dict:
        current = self._sim_prices[pair]
        drift = random.gauss(0, 0.00002)
        volatility = random.gauss(0, 0.00015)
        change = drift + volatility
        base = self.BASE_PRICES[pair]
        reversion = (base - current) * 0.002
        new_price = current + change + reversion
        self._sim_prices[pair] = new_price

        half_spread = random.uniform(0.00006, 0.000125)
        spread_pips = round(half_spread * 2 * 10000, 2)
        mid = round(new_price, 5)

        return {
            "pair": pair,
            "bid": round(mid - half_spread, 5),
            "ask": round(mid + half_spread, 5),
            "mid": mid,
            "spread_pips": spread_pips,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "simulated",
        }

    async def fetch_price(self, pair: str) -> dict:
        if settings.use_simulated_data:
            return self.fetch_price_simulated(pair)
        result = await self.fetch_price_live(pair)
        if result is None:
            return self.fetch_price_simulated(pair)
        return result

    def compute_indicators(self, pair: str) -> dict:
        prices = storage.prices.get(pair, [])
        if len(prices) < 20:
            return {
                "sma20": None, "sma50": None, "adx": None, "atr": None,
                "rsi": None, "regime": "RANGE", "bb_upper": None, "bb_middle": None, "bb_lower": None,
            }

        closes = np.array([p["close"] for p in prices], dtype=np.float64)
        highs = np.array([p["high"] for p in prices], dtype=np.float64)
        lows = np.array([p["low"] for p in prices], dtype=np.float64)

        sma20 = indicators.calculate_sma(closes, 20)
        sma50 = indicators.calculate_sma(closes, 50)
        adx = indicators.calculate_adx(highs, lows, closes, 14)
        atr = indicators.calculate_atr(highs, lows, closes, 14)
        rsi = indicators.calculate_rsi(closes, 14)
        bb_upper, bb_middle, bb_lower = indicators.calculate_bollinger(closes, 20, 2.0)

        def latest_valid(arr):
            for v in reversed(arr):
                if not np.isnan(v):
                    return round(float(v), 5)
            return None

        latest_adx = latest_valid(adx)
        regime = "TREND" if latest_adx and latest_adx > 25 else "RANGE"

        return {
            "sma20": latest_valid(sma20),
            "sma50": latest_valid(sma50),
            "adx": latest_adx,
            "atr": latest_valid(atr),
            "rsi": latest_valid(rsi),
            "regime": regime,
            "bb_upper": latest_valid(bb_upper),
            "bb_middle": latest_valid(bb_middle),
            "bb_lower": latest_valid(bb_lower),
        }

    async def poll_once(self, pair: str) -> Optional[dict]:
        price_data = await self.fetch_price(pair)
        if price_data is None:
            return None

        mid = price_data["mid"]
        bar = {
            "timestamp": price_data["timestamp"],
            "open": mid,
            "high": mid + abs(random.gauss(0, 0.00005)),
            "low": mid - abs(random.gauss(0, 0.00005)),
            "close": mid,
            "volume": round(random.uniform(100, 1000), 0),
        }

        storage.prices[pair].append(bar)
        if len(storage.prices[pair]) > 500:
            storage.prices[pair] = storage.prices[pair][-500:]

        ind = self.compute_indicators(pair)

        broadcast_data = {
            "type": "price_update",
            "data": {**price_data, "indicators": ind},
        }
        await self.broadcast(broadcast_data)

        # 更新特征引擎和事件响应引擎
        snapshot = feature_engine.update(pair, price_data)
        event_response.update(pair, snapshot)

        return {**price_data, "indicators": ind}

    async def start_polling(self) -> None:
        self._running = True
        interval = settings.sim_poll_interval if settings.use_simulated_data else settings.api_poll_interval
        logger.info(f"Starting price polling (interval={interval}s)")

        while self._running:
            for pair in settings.pairs:
                try:
                    await self.poll_once(pair)
                except Exception as e:
                    logger.error(f"Poll error for {pair}: {e}")
            await asyncio.sleep(interval)

    def stop_polling(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        self.stop_polling()
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

market_data = MarketDataService()

# ─── Feature Engine (波动率/点差特征计算) ──────────────────────────────────────

class FeatureEngine:
    """计算实时市场特征: vol_ratio, spread_ratio, trend_score"""

    def __init__(self):
        self._spread_baselines: dict[str, float] = {"AUD/USD": 1.5, "NZD/USD": 1.8}
        self._recent_spreads: dict[str, list[float]] = {"AUD/USD": [], "NZD/USD": []}
        self._recent_prices_1m: dict[str, list[float]] = {"AUD/USD": [], "NZD/USD": []}
        self._recent_prices_5m: dict[str, list[float]] = {"AUD/USD": [], "NZD/USD": []}

    def update(self, pair: str, price_data: dict) -> MarketSnapshot:
        """每次行情到来时更新特征"""
        mid = price_data.get("mid", 0)
        spread_pips = price_data.get("spread_pips", 0)

        # 更新点差历史
        self._recent_spreads.setdefault(pair, []).append(spread_pips)
        if len(self._recent_spreads[pair]) > 100:
            self._recent_spreads[pair] = self._recent_spreads[pair][-100:]

        # 更新价格历史
        self._recent_prices_1m.setdefault(pair, []).append(mid)
        if len(self._recent_prices_1m[pair]) > 20:  # ~1min at 3s interval
            self._recent_prices_1m[pair] = self._recent_prices_1m[pair][-20:]

        self._recent_prices_5m.setdefault(pair, []).append(mid)
        if len(self._recent_prices_5m[pair]) > 100:  # ~5min
            self._recent_prices_5m[pair] = self._recent_prices_5m[pair][-100:]

        # 计算 spread_ratio
        spreads = self._recent_spreads[pair]
        baseline = sum(spreads) / len(spreads) if len(spreads) > 10 else self._spread_baselines.get(pair, 1.5)
        spread_ratio = spread_pips / baseline if baseline > 0 else 1.0

        # 计算波动率
        vol_1m = self._calc_vol(self._recent_prices_1m.get(pair, []))
        vol_5m = self._calc_vol(self._recent_prices_5m.get(pair, []))
        vol_ratio = vol_1m / vol_5m if vol_5m > 0 else 1.0

        # 趋势得分 (5分钟方向)
        prices_5m = self._recent_prices_5m.get(pair, [])
        trend_score = 0.0
        if len(prices_5m) >= 10:
            recent = prices_5m[-5:]
            older = prices_5m[-10:-5]
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older)
            diff_pips = (recent_avg - older_avg) * 10000
            trend_score = max(-1.0, min(1.0, diff_pips / 5.0))

        return MarketSnapshot(
            pair=pair,
            price=mid,
            bid=price_data.get("bid", mid),
            ask=price_data.get("ask", mid),
            spread_pips=spread_pips,
            vol_1m=round(vol_1m * 10000, 2),
            vol_5m=round(vol_5m * 10000, 2),
            vol_ratio=round(vol_ratio, 3),
            spread_ratio=round(spread_ratio, 3),
            trend_score_5m=round(trend_score, 3),
            ts=time.time(),
        )

    @staticmethod
    def _calc_vol(prices: list[float]) -> float:
        if len(prices) < 3:
            return 0.0
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] != 0:
                returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        return variance ** 0.5

feature_engine = FeatureEngine()

# ─── Signal Engine ─────────────────────────────────────────────────────────────

class SignalEngine:
    def __init__(self):
        self._latest_signals: dict[str, dict] = {}

    def get_all_latest_signals(self) -> dict[str, dict]:
        return self._latest_signals

    async def generate_signal(self, pair: str, ind: dict, direction_permission: str, event_state: dict, override_mode: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()

        if storage.settings.get("kill_switch", "false").lower() == "true":
            return self._make_signal(pair, "WAIT", 0, "RANGE", "Kill switch is active", now)

        if override_mode == "OBSERVE_ONLY":
            return self._make_signal(pair, "WAIT", 0, "RANGE", "System in OBSERVE_ONLY mode", now)

        if event_state.get("state") in ("PRE_EVENT", "COOLDOWN"):
            remaining = event_state.get("remaining_seconds", 0)
            return self._make_signal(pair, "WAIT", 0, "EVENT", f"Event cooldown ({remaining:.0f}s)", now)

        sma20 = ind.get("sma20")
        sma50 = ind.get("sma50")
        adx = ind.get("adx") or 15
        rsi = ind.get("rsi")
        regime = ind.get("regime", "RANGE")

        prices = storage.prices.get(pair, [])
        if not prices or sma20 is None or rsi is None:
            return self._make_signal(pair, "WAIT", 0, "RANGE", "Insufficient data", now)

        price = prices[-1]["close"]

        # ── 双信号确认: Breakout + Vol Expansion ──
        # 获取当前市场快照的 vol_ratio
        snapshot = feature_engine.update(pair, {"mid": price, "spread_pips": 0, "bid": price, "ask": price})
        vol_expanding = snapshot.vol_ratio >= 1.2  # 波动率放大

        if regime == "TREND" and sma50:
            if direction_permission in ("LONG_ONLY", "BOTH") and price > sma20 > sma50 and rsi < 70:
                base_conf = min(60 * min(adx / 50, 1.5), 100)
                # 双确认: 有 vol expansion 提高置信度
                confidence = base_conf * (1.1 if vol_expanding else 0.7)
                confidence = min(confidence, 100)
                vol_tag = "VOL_EXPAND" if vol_expanding else "VOL_FLAT"
                reason = f"TREND BUY: price > SMA20 > SMA50, RSI={rsi:.1f}, ADX={adx:.1f} [{vol_tag}]"
                sig = self._make_signal(pair, "BUY", confidence, regime, reason, now)
                self._store_signal(sig)
                return sig

            if direction_permission in ("SHORT_ONLY", "BOTH") and price < sma20 < sma50 and rsi > 30:
                base_conf = min(60 * min(adx / 50, 1.5), 100)
                confidence = base_conf * (1.1 if vol_expanding else 0.7)
                confidence = min(confidence, 100)
                vol_tag = "VOL_EXPAND" if vol_expanding else "VOL_FLAT"
                reason = f"TREND SELL: price < SMA20 < SMA50, RSI={rsi:.1f}, ADX={adx:.1f} [{vol_tag}]"
                sig = self._make_signal(pair, "SELL", confidence, regime, reason, now)
                self._store_signal(sig)
                return sig

        bb_upper = ind.get("bb_upper")
        bb_lower = ind.get("bb_lower")
        if regime == "RANGE" and bb_upper and bb_lower:
            bb_width = bb_upper - bb_lower
            if bb_width > 0:
                if direction_permission in ("LONG_ONLY", "BOTH") and price <= bb_lower + bb_width * 0.1 and rsi < 35:
                    confidence = min(40 + (35 - rsi), 85)
                    reason = f"RANGE BUY: price near lower BB, RSI={rsi:.1f}"
                    sig = self._make_signal(pair, "BUY", confidence, regime, reason, now)
                    self._store_signal(sig)
                    return sig

                if direction_permission in ("SHORT_ONLY", "BOTH") and price >= bb_upper - bb_width * 0.1 and rsi > 65:
                    confidence = min(40 + (rsi - 65), 85)
                    reason = f"RANGE SELL: price near upper BB, RSI={rsi:.1f}"
                    sig = self._make_signal(pair, "SELL", confidence, regime, reason, now)
                    self._store_signal(sig)
                    return sig

        return self._make_signal(pair, "WAIT", 0, regime, "No signal conditions met", now)

    def _make_signal(self, pair: str, direction: str, confidence: float, regime: str, reason: str, timestamp: str) -> dict:
        sig = {
            "pair": pair,
            "direction": direction,
            "confidence": round(confidence, 1),
            "regime": regime,
            "reason": reason,
            "timestamp": timestamp,
        }
        self._latest_signals[pair] = sig
        return sig

    def _store_signal(self, signal: dict) -> None:
        storage.signals.insert(0, signal)
        if len(storage.signals) > 200:
            storage.signals = storage.signals[:200]

    async def evaluate_all(self, event_state: dict) -> list[dict]:
        signals = []
        override_mode = storage.settings.get("override_mode", "NORMAL")

        for pair in settings.pairs:
            result = await market_data.poll_once(pair)
            if result is None:
                continue

            key = pair.replace("/", "_").lower() + "_direction"
            direction_permission = storage.settings.get(key, "LONG_ONLY")
            ind = result.get("indicators", {})

            signal = await self.generate_signal(pair, ind, direction_permission, event_state, override_mode)
            signals.append(signal)

            if signal["direction"] != "WAIT":
                await market_data.broadcast({"type": "signal", "data": signal})

        return signals

signal_engine = SignalEngine()

# ─── Alert Service (增强版 - 风险警报) ──────────────────────────────────────────

class AlertService:
    """增强版警报服务 - 支持交易信号和风险警报的Telegram推送"""
    
    # 警报类型
    ALERT_SIGNAL = "SIGNAL"
    ALERT_RISK_WARNING = "RISK_WARNING"
    ALERT_RISK_EMERGENCY = "RISK_EMERGENCY"
    ALERT_RISK_RECOVERY = "RISK_RECOVERY"
    ALERT_EVENT = "EVENT"
    ALERT_SYSTEM = "SYSTEM"
    
    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._daily_alert_count: int = 0
        self._last_reset_date: str = datetime.now(timezone.utc).date().isoformat()
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client
    
    def _check_daily_reset(self):
        """检查并重置每日警报计数"""
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self._last_reset_date:
            self._daily_alert_count = 0
            self._last_reset_date = today
    
    async def send_telegram(self, message: str, silent: bool = False) -> bool:
        """发送Telegram消息"""
        if not settings.telegram_configured:
            logger.info(f"[TELEGRAM FALLBACK] {message}")
            self._store_alert("TELEGRAM_FALLBACK", message, False)
            return False
        
        self._check_daily_reset()
        
        # 防止警报风暴
        if self._daily_alert_count > 100:
            logger.warning("Daily alert limit reached, skipping Telegram notification")
            return False
        
        client = await self._get_client()
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        
        try:
            resp = await client.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "disable_notification": silent,
                },
            )
            data = resp.json()
            success = data.get("ok", False)
            
            if not success:
                logger.error(f"Telegram API error: {data}")
            
            if success:
                self._daily_alert_count += 1
            
            self._store_alert("TELEGRAM", message, success)
            return success
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            self._store_alert("TELEGRAM_ERROR", str(e), False)
            return False
    
    def _store_alert(self, alert_type: str, content: str, success: bool):
        """存储警报历史到MongoDB"""
        db.store_alert(alert_type, content, success)
    
    def get_alert_history(self, limit: int = 50) -> list:
        return db.get_alert_history(limit)
    
    async def alert_signal(self, signal: dict) -> None:
        """发送交易信号警报"""
        direction_emoji = {"BUY": "📈", "SELL": "📉", "WAIT": "⏸"}.get(signal.get("direction", ""), "?")
        confidence = signal.get('confidence', 0)
        
        # 高置信度信号使用更醒目的格式
        if confidence >= 70:
            header = f"🔥 <b>HIGH CONFIDENCE SIGNAL</b> 🔥"
        else:
            header = f"[{direction_emoji} SIGNAL]"
        
        message = (
            f"<b>{header}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"货币对: <b>{signal.get('pair', '???')}</b>\n"
            f"方向: <b>{signal.get('direction', '?')}</b>\n"
            f"置信度: <b>{confidence:.1f}%</b>\n"
            f"市场状态: {signal.get('regime', '???')}\n"
            f"原因: {signal.get('reason', '')}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        await self.send_telegram(message)
    
    async def alert_risk_warning(self, warning_type: str, details: dict) -> None:
        """发送风险预警"""
        message = (
            f"⚠️ <b>RISK WARNING</b> ⚠️\n"
            f"━━━━━━━━━━━━━━━\n"
            f"类型: <b>{warning_type}</b>\n"
        )
        
        if "pair" in details:
            message += f"货币对: {details['pair']}\n"
        if "pnl_pips" in details:
            message += f"当前盈亏: {details['pnl_pips']:.1f} pips\n"
        if "level" in details:
            message += f"触发级别: {details['level']}\n"
        if "action" in details:
            message += f"建议操作: <b>{details['action']}</b>\n"
        if "message" in details:
            message += f"详情: {details['message']}\n"
        
        message += (
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        
        await self.send_telegram(message)
    
    async def alert_risk_emergency(self, reason: str, stats: dict) -> None:
        """发送紧急平仓警报 - 最高优先级"""
        message = (
            f"🚨🚨🚨 <b>EMERGENCY CLOSE</b> 🚨🚨🚨\n"
            f"━━━━━━━━━━━━━━━\n"
            f"原因: <b>{reason}</b>\n"
            f"\n"
            f"📊 <b>当日统计:</b>\n"
            f"• 日盈亏: {stats.get('total_pnl_pips', 0):.1f} pips\n"
            f"• 交易次数: {stats.get('trade_count', 0)}\n"
            f"• 连续亏损: {stats.get('consecutive_losses', 0)}\n"
            f"\n"
            f"⛔ <b>所有交易已暂停</b>\n"
            f"🕐 冷却期: 30分钟\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        
        # 紧急警报不静音
        await self.send_telegram(message, silent=False)
    
    async def alert_market_deterioration(self, pair: str, triggers: list[str], severity: str) -> None:
        """发送市场恶化警报"""
        severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(severity, "⚪")
        
        message = (
            f"{severity_emoji} <b>MARKET DETERIORATION</b> {severity_emoji}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"货币对: <b>{pair}</b>\n"
            f"严重程度: <b>{severity}</b>\n"
            f"\n"
            f"触发条件:\n"
        )
        
        for trigger in triggers:
            message += f"• {trigger}\n"
        
        message += (
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        
        await self.send_telegram(message)
    
    async def alert_daily_summary(self, stats: dict) -> None:
        """发送每日交易摘要"""
        pnl = stats.get('total_pnl_pips', 0)
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        
        message = (
            f"📋 <b>DAILY TRADING SUMMARY</b> 📋\n"
            f"━━━━━━━━━━━━━━━\n"
            f"日期: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"\n"
            f"{pnl_emoji} 日盈亏: <b>{pnl:+.1f} pips</b>\n"
            f"📊 交易次数: {stats.get('trade_count', 0)}\n"
            f"⚠️ 警告触发: {stats.get('warnings_triggered', 0)}\n"
            f"🚨 紧急触发: {stats.get('emergencies_triggered', 0)}\n"
            f"📉 最大回撤: {stats.get('max_drawdown_pips', 0):.1f} pips\n"
            f"\n"
        )
        
        # 评价
        if pnl >= 50:
            message += "💪 表现优秀！继续保持！"
        elif pnl >= 0:
            message += "👍 稳健交易，明天继续！"
        elif pnl > -30:
            message += "⚡ 小幅回撤，保持冷静！"
        else:
            message += "🛡️ 请检视策略，注意风控！"
        
        message += f"\n━━━━━━━━━━━━━━━"
        
        await self.send_telegram(message)
    
    async def alert_event_trigger(self, event_level: str, event_title: str) -> None:
        """发送事件触发警报"""
        level_emoji = {"A": "🔴", "B": "🟠", "C": "🟡"}.get(event_level, "⚪")
        
        message = (
            f"{level_emoji} <b>EVENT TRIGGERED</b> {level_emoji}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"级别: <b>{event_level}</b>\n"
            f"事件: {event_title}\n"
            f"\n"
            f"⏸️ 交易已暂停，等待30秒确认窗口\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        
        await self.send_telegram(message)
    
    async def alert_recovery(self, step: int, leverage_ratio: float) -> None:
        """发送恢复通知"""
        if step == 0:
            message = (
                f"🔄 <b>GRADUATED RESTART INITIATED</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"初始杠杆比例: <b>{leverage_ratio:.0f}%</b>\n"
                f"计划: 30% → 50% → 70% → 100%\n"
                f"━━━━━━━━━━━━━━━"
            )
        elif leverage_ratio >= 100:
            message = (
                f"✅ <b>TRADING FULLY RESTORED</b> ✅\n"
                f"━━━━━━━━━━━━━━━\n"
                f"杠杆比例: <b>100%</b>\n"
                f"系统已恢复正常交易\n"
                f"━━━━━━━━━━━━━━━"
            )
        else:
            message = (
                f"🔄 <b>RESTART STEP {step}</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"当前杠杆比例: <b>{leverage_ratio:.0f}%</b>\n"
                f"━━━━━━━━━━━━━━━"
            )
        
        await self.send_telegram(message)
    
    def get_daily_stats(self) -> dict:
        """获取每日警报统计"""
        self._check_daily_reset()
        return {
            "date": self._last_reset_date,
            "alert_count": self._daily_alert_count,
            "telegram_configured": settings.telegram_configured,
        }
    
    async def shutdown(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

alert_service = AlertService()

# ─── AI Analysis Service ───────────────────────────────────────────────────────

class AIAnalysisService:
    def __init__(self):
        self._chat = None

    async def analyze_market(self, pair: str, context: dict) -> dict:
        if not settings.ai_configured:
            return {
                "pair": pair,
                "analysis": "AI analysis not configured. Please set EMERGENT_LLM_KEY.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "error",
            }

        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage

            chat = LlmChat(
                api_key=settings.emergent_llm_key,
                session_id=f"fx-analysis-{pair}-{int(time.time())}",
                system_message="""你是一位专业的外汇市场分析师，专注于AUD/USD和NZD/USD交易。
请根据提供的技术指标和市场数据，给出简洁的分析和交易建议。
分析应包括：1)当前趋势判断 2)关键支撑/阻力位 3)短期方向建议 4)风险提示
请用中英文混合的专业术语回答。"""
            ).with_model("openai", "gpt-5.2")

            indicators = context.get("indicators", {})
            prices = storage.prices.get(pair, [])[-20:]
            recent_closes = [p["close"] for p in prices] if prices else []

            prompt = f"""
货币对: {pair}
当前价格: {context.get('price', 'N/A')}
技术指标:
- SMA20: {indicators.get('sma20', 'N/A')}
- SMA50: {indicators.get('sma50', 'N/A')}
- RSI(14): {indicators.get('rsi', 'N/A')}
- ADX(14): {indicators.get('adx', 'N/A')}
- ATR(14): {indicators.get('atr', 'N/A')}
- Bollinger Bands: Upper={indicators.get('bb_upper', 'N/A')}, Middle={indicators.get('bb_middle', 'N/A')}, Lower={indicators.get('bb_lower', 'N/A')}
市场状态: {indicators.get('regime', 'N/A')}
最近20个收盘价: {recent_closes[-5:] if recent_closes else 'N/A'}

请给出简洁的分析和10-30分钟短线交易建议。
"""
            user_message = UserMessage(text=prompt)
            response = await chat.send_message(user_message)

            result = {
                "pair": pair,
                "analysis": response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "indicators": indicators,
            }

            storage.add_ai_analysis(result)

            return result

        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return {
                "pair": pair,
                "analysis": f"Analysis failed: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "error",
            }

ai_service = AIAnalysisService()

# ─── Background Tasks ──────────────────────────────────────────────────────────

_background_tasks: list[asyncio.Task] = []

async def signal_evaluation_loop():
    interval = settings.sim_poll_interval if settings.use_simulated_data else settings.api_poll_interval
    await asyncio.sleep(interval / 2)

    while True:
        try:
            event_state = event_engine.get_event_state()
            signals = await signal_engine.evaluate_all(event_state)
            for sig in signals:
                if sig["direction"] != "WAIT" and sig["confidence"] >= 50:
                    await alert_service.alert_signal(sig)
        except Exception as e:
            logger.error(f"Signal evaluation error: {e}")
        await asyncio.sleep(interval)

async def event_calendar_check_loop():
    while True:
        try:
            now = datetime.now(timezone.utc)
            for ev in storage.events:
                event_time = datetime.fromisoformat(ev["datetime"].replace("Z", "+00:00"))
                diff = (event_time - now).total_seconds()
                if 0 < diff <= 60 and event_engine.state == "NORMAL":
                    impact = ev.get("impact", "C")
                    if impact in ("A", "B"):
                        await event_engine.start_event_cooldown(
                            event_level=impact,
                            title=ev.get("title", "Unknown Event"),
                        )
                        state = event_engine.get_event_state()
                        await market_data.broadcast({"type": "event_state", "data": state})
        except Exception as e:
            logger.error(f"Event calendar check error: {e}")
        await asyncio.sleep(30)

# ─── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    source = "simulated" if settings.use_simulated_data else "Twelve Data API"
    logger.info(f"FX Trading System started - data source: {source}")

    # Seed admin user
    seed_admin_user()

    _background_tasks.append(asyncio.create_task(market_data.start_polling()))
    _background_tasks.append(asyncio.create_task(signal_evaluation_loop()))
    _background_tasks.append(asyncio.create_task(event_calendar_check_loop()))

    yield

    logger.info("Shutting down FX Trading System...")
    market_data.stop_polling()
    for task in _background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await market_data.shutdown()
    await alert_service.shutdown()


def seed_admin_user():
    """Seed admin user on startup"""
    mongo_db = db.get_db()
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@fxtrading.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "FXAdmin2026!")
    existing = mongo_db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = hash_password(admin_password)
        mongo_db.users.insert_one({
            "email": admin_email,
            "password_hash": hashed,
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Admin user seeded: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        mongo_db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}}
        )
        logger.info(f"Admin password updated: {admin_email}")
    mongo_db.users.create_index("email", unique=True)

# ─── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="FX Trading System",
    description="AUD/USD and NZD/USD Event-Driven Trading System",
    version="1.0.0",
    lifespan=lifespan,
)

# Include security router
try:
    from security_routes import fx_security_router, set_fx_security_instance
    from security_integration import get_fx_security_integration
    
    # Initialize FX security integration
    async def init_fx_security():
        mongo_db = db.get_db()
        security = get_fx_security_integration(mongo_db)
        await security.initialize()
        set_fx_security_instance(security)
        logger.info("FX Security integration initialized successfully")
    
    # Add startup event for security
    @app.on_event("startup")
    async def startup_fx_security():
        await init_fx_security()
    
    app.include_router(fx_security_router)
    logger.info("FX Security router included")
except ImportError as e:
    logger.warning(f"FX Security module not available: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ───────────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    value: str

class EventTrigger(BaseModel):
    level: str
    title: str = "Manual trigger"

class DirectionConfirm(BaseModel):
    pair: str
    prices_before: list[float] = []
    prices_after: list[float] = []

class AIAnalysisRequest(BaseModel):
    pair: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ─── Auth Endpoints ────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def auth_login(body: LoginRequest, response: Response):
    mongo_db = db.get_db()
    email = body.email.strip().lower()
    loop = asyncio.get_event_loop()
    user = await loop.run_in_executor(None, lambda: mongo_db.users.find_one({"email": email}))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    _set_auth_cookies(response, access_token, refresh_token)
    return {
        "id": user_id,
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "user"),
        "token": access_token,
    }

@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return user

@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"success": True}

@app.post("/api/auth/refresh")
async def auth_refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = pyjwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        from bson import ObjectId
        mongo_db = db.get_db()
        loop = asyncio.get_event_loop()
        user = await loop.run_in_executor(None, lambda: mongo_db.users.find_one({"_id": ObjectId(payload["sub"])}))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access_token = create_access_token(str(user["_id"]), user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
        return {"success": True}
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# ─── Helper Functions ──────────────────────────────────────────────────────────

def _normalize_pair(pair: str) -> str:
    return pair.upper().replace("_", "/").replace("-", "/")

# ─── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_source": "simulated" if settings.use_simulated_data else "twelvedata",
        "telegram_configured": settings.telegram_configured,
        "ai_configured": settings.ai_configured,
        "pairs": settings.pairs,
        "event_state": event_engine.get_event_state()["state"],
    }

# ─── Prices ────────────────────────────────────────────────────────────────────

@app.get("/api/prices/{pair}")
async def get_price(pair: str):
    pair = _normalize_pair(pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=404, detail=f"Pair {pair} not supported")

    result = await market_data.poll_once(pair)
    if result is None:
        raise HTTPException(status_code=503, detail="Unable to fetch price data")

    return {
        "pair": pair,
        "price": result,
        "indicators": {k: v for k, v in result.get("indicators", {}).items()},
    }

@app.get("/api/prices/{pair}/history")
async def get_price_history(pair: str, limit: int = Query(100, ge=1, le=500)):
    pair = _normalize_pair(pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=404, detail=f"Pair {pair} not supported")

    prices = storage.prices.get(pair, [])[-limit:]
    return {"pair": pair, "count": len(prices), "prices": prices}

# ─── Signals ───────────────────────────────────────────────────────────────────

@app.get("/api/signals")
async def list_signals(pair: Optional[str] = None, limit: int = Query(50, ge=1, le=500)):
    signals = storage.signals[:limit]
    if pair:
        pair = _normalize_pair(pair)
        signals = [s for s in signals if s.get("pair") == pair]
    return {"count": len(signals), "signals": signals}

@app.get("/api/signals/current")
async def current_signals():
    return {
        "signals": signal_engine.get_all_latest_signals(),
        "event_state": event_engine.get_event_state(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ─── Trades ────────────────────────────────────────────────────────────────────

@app.get("/api/trades")
async def list_trades(status: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    trades = storage.trades[:limit]
    if status:
        trades = [t for t in trades if t.get("status") == status]
    return {"count": len(trades), "trades": trades}

@app.get("/api/trades/stats")
async def trade_stats():
    all_trades = [t for t in storage.trades if t.get("status") == "CLOSED"]
    if not all_trades:
        return {
            "total_trades": 0,
            "open_trades": len([t for t in storage.trades if t.get("status") == "OPEN"]),
            "win_rate": 0.0,
            "total_pnl_pips": 0.0,
            "avg_pnl_pips": 0.0,
            "by_pair": {},
        }

    wins = [t for t in all_trades if (t.get("pnl_pips") or 0) > 0]
    total_pnl = sum(t.get("pnl_pips", 0) or 0 for t in all_trades)

    return {
        "total_trades": len(all_trades),
        "open_trades": len([t for t in storage.trades if t.get("status") == "OPEN"]),
        "win_rate": round(len(wins) / len(all_trades) * 100, 1) if all_trades else 0.0,
        "total_pnl_pips": round(total_pnl, 1),
        "avg_pnl_pips": round(total_pnl / len(all_trades), 1) if all_trades else 0.0,
        "by_pair": {},
    }

# ─── Events ────────────────────────────────────────────────────────────────────

@app.get("/api/events")
async def list_events():
    return {"count": len(storage.events), "events": storage.events}

@app.get("/api/events/state")
async def event_state():
    return event_engine.get_event_state()

@app.post("/api/event/trigger")
async def trigger_event(body: EventTrigger):
    if body.level not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="Level must be A, B, or C")

    result = await event_engine.start_event_cooldown(event_level=body.level, title=body.title)
    state = event_engine.get_event_state()
    await market_data.broadcast({"type": "event_state", "data": state})
    return result

@app.post("/api/event/confirm")
async def confirm_event_direction(body: DirectionConfirm):
    pair = _normalize_pair(body.pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=400, detail=f"Pair {pair} not supported")

    prices_before = body.prices_before
    prices_after = body.prices_after

    if not prices_before or not prices_after:
        prices = storage.prices.get(pair, [])
        if len(prices) >= 10:
            all_closes = [p["close"] for p in prices]
            mid = len(all_closes) // 2
            prices_before = all_closes[:mid]
            prices_after = all_closes[mid:]
        else:
            raise HTTPException(status_code=400, detail="Insufficient price data")

    result = await event_engine.confirm_direction(pair, prices_before, prices_after)
    state = event_engine.get_event_state()
    await market_data.broadcast({"type": "event_state", "data": state})
    return result

@app.post("/api/event/reset")
async def reset_event():
    await event_engine.reset()
    state = event_engine.get_event_state()
    await market_data.broadcast({"type": "event_state", "data": state})
    return state

# ─── Settings ──────────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def list_settings():
    return storage.settings

@app.put("/api/settings/{key}")
async def update_setting(key: str, body: SettingUpdate):
    valid_keys = {
        "aud_usd_direction", "nzd_usd_direction", "override_mode",
        "max_hold_minutes", "stop_loss_pips", "take_profit_pips",
        "spread_threshold_pips", "event_a_cooldown_seconds",
        "event_b_cooldown_seconds", "kill_switch",
    }
    if key not in valid_keys:
        raise HTTPException(status_code=400, detail=f"Invalid setting key: {key}")

    if key in ("aud_usd_direction", "nzd_usd_direction"):
        if body.value not in ("LONG_ONLY", "SHORT_ONLY", "BOTH"):
            raise HTTPException(status_code=400, detail="Direction must be LONG_ONLY, SHORT_ONLY, or BOTH")

    storage.update_setting(key, body.value)
    await market_data.broadcast({
        "type": "setting_update",
        "data": {"key": key, "value": body.value},
    })
    return {"key": key, "value": body.value, "status": "updated"}

# ─── AI Analysis ───────────────────────────────────────────────────────────────

@app.post("/api/ai/analyze")
async def ai_analyze(body: AIAnalysisRequest):
    pair = _normalize_pair(body.pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=400, detail=f"Pair {pair} not supported")

    result = await market_data.poll_once(pair)
    context = {
        "price": result.get("mid") if result else None,
        "indicators": result.get("indicators", {}) if result else {},
    }

    analysis = await ai_service.analyze_market(pair, context)
    return analysis

@app.get("/api/ai/history")
async def ai_history(limit: int = Query(10, ge=1, le=50)):
    return {"count": len(storage.ai_analyses[:limit]), "analyses": storage.ai_analyses[:limit]}

# ─── Model Drivers ─────────────────────────────────────────────────────────────

@app.get("/api/model/drivers")
async def model_drivers():
    return {
        "AUD/USD": [
            {"factor": "中国经济与商品", "weight": 35},
            {"factor": "RBA 政策预期", "weight": 27},
            {"factor": "美联储与美元", "weight": 23},
            {"factor": "全球风险偏好", "weight": 15},
        ],
        "NZD/USD": [
            {"factor": "出口商品与需求", "weight": 32},
            {"factor": "RBNZ 政策预期", "weight": 28},
            {"factor": "中国/亚洲需求", "weight": 18},
            {"factor": "美联储与美元", "weight": 12},
            {"factor": "全球风险偏好", "weight": 10},
        ],
    }

@app.get("/api/model/regime")
async def model_regime():
    all_signals = signal_engine.get_all_latest_signals()
    return {
        pair: {"regime": sig.get("regime", "RANGE"), "adx": sig.get("adx", 0)}
        for pair, sig in all_signals.items()
    }

# ─── Broker Status ─────────────────────────────────────────────────────────────

@app.get("/api/broker/status")
async def broker_status():
    return {
        "dukascopy": {
            "name": "Dukascopy Bank",
            "configured": settings.dukascopy_api_url != "http://localhost:9090",
            "connected": False,
            "url": settings.dukascopy_api_url,
            "features": ["SWFX 实时行情", "ECN 市场深度", "点差监控", "订单执行"],
        },
        "interactive_brokers": {
            "name": "Interactive Brokers",
            "configured": False,
            "connected": False,
            "host": settings.ib_tws_host,
            "port": settings.ib_tws_port,
            "features": ["新闻推送", "经济日历", "实时行情", "订单执行"],
        },
        "status": "Phase 2 - 待接入",
    }

@app.get("/api/broker/datasources")
async def data_sources():
    return [
        {"name": "Twelve Data", "type": "行情", "status": "运行中" if not settings.use_simulated_data else "未配置", "role": "主源"},
        {"name": "Dukascopy SWFX", "type": "行情", "status": "未连接", "role": "备源"},
        {"name": "IB TWS", "type": "行情", "status": "未连接", "role": "备源"},
        {"name": "模拟数据", "type": "行情", "status": "运行中" if settings.use_simulated_data else "待机", "role": "开发"},
    ]

# ─── Event Response Engine APIs (事件响应引擎) ──────────────────────────────────

@app.get("/api/event-response/status")
async def event_response_status():
    """获取事件响应引擎状态 (所有品种)"""
    states = event_response.get_all_states()
    return {
        "engines": states,
        "pair_config": {pair: dict(cfg) for pair, cfg in PAIR_CONFIG.items()},
    }

@app.post("/api/event-response/trigger")
async def event_response_trigger(event_level: str = Query("A"), title: str = Query("Manual trigger")):
    """触发事件 - 所有品种进入结构化等待"""
    # 获取当前价格作为快照
    results = {}
    for pair in settings.pairs:
        prices = storage.prices.get(pair, [])
        if prices:
            price_data = {"mid": prices[-1]["close"], "spread_pips": 1.5, "bid": prices[-1]["close"], "ask": prices[-1]["close"]}
            snapshot = feature_engine.update(pair, price_data)
            engine = event_response.engines.get(pair)
            if engine:
                state = engine.on_event_detected(snapshot, event_level, title)
                results[pair] = state.__dict__
    # 同时触发旧引擎保持兼容
    await event_engine.start_event_cooldown(event_level, title)
    return {"event_response": results, "legacy_engine": event_engine.get_event_state()}

@app.post("/api/event-response/reset")
async def event_response_reset(pair: str = Query(None)):
    """重置事件响应引擎"""
    if pair:
        event_response.reset(pair)
    else:
        event_response.reset_all()
    await event_engine.reset()
    return {"success": True, "states": event_response.get_all_states()}

# ─── Execution Gate APIs (执行闸门) ────────────────────────────────────────────

@app.get("/api/execution-gate/status")
async def gate_status():
    """获取执行闸门状态"""
    return execution_gate.get_status()

@app.post("/api/execution-gate/evaluate")
async def gate_evaluate(pair: str = Query("AUD/USD")):
    """手动评估执行闸门 (调试用)"""
    # 构建 GateInput
    prices = storage.prices.get(pair, [])
    price = prices[-1]["close"] if prices else 0
    price_data = {"mid": price, "spread_pips": 1.5, "bid": price, "ask": price}
    snapshot = feature_engine.update(pair, price_data)
    
    event_state = event_response.engines.get(pair)
    er_state = event_state.state if event_state else "IDLE"
    er_direction = event_state.confirmed_direction if event_state else ""
    er_confidence = event_state.confidence if event_state else 0
    
    health = strategy_monitor.health.get(pair)
    
    gi = GateInput(
        symbol=pair,
        ts=time.time(),
        event_state=er_state,
        event_direction=er_direction,
        event_confidence=er_confidence,
        regime=market_data.compute_indicators(pair).get("regime", "RANGE"),
        trade_allowed=True,
        signal_side=signal_engine.get_all_latest_signals().get(pair, {}).get("direction", "WAIT"),
        signal_confidence=signal_engine.get_all_latest_signals().get(pair, {}).get("confidence", 0),
        spread_ratio=snapshot.spread_ratio,
        vol_ratio=snapshot.vol_ratio,
        consecutive_losses=health.consecutive_losses if health else 0,
        cooldown_state=health.recovery_state if health else "GREEN",
        kill_switch=storage.settings.get("kill_switch", "false").lower() == "true",
        deterioration_triggered=storage.risk_control._status == "EMERGENCY",
    )
    decision = execution_gate.decide(gi)
    return {
        "input": {
            "symbol": gi.symbol,
            "event_state": gi.event_state,
            "regime": gi.regime,
            "signal_side": gi.signal_side,
            "vol_ratio": gi.vol_ratio,
            "spread_ratio": gi.spread_ratio,
            "consecutive_losses": gi.consecutive_losses,
            "cooldown_state": gi.cooldown_state,
        },
        "decision": decision.to_dict(),
    }

# ─── Strategy Monitor APIs (策略失效检测器) ────────────────────────────────────

@app.get("/api/strategy-monitor/health")
async def strategy_health():
    """获取策略健康状态"""
    return strategy_monitor.get_all_health()

@app.post("/api/strategy-monitor/record-trade")
async def record_trade(pair: str = Query("AUD/USD"), pnl_pips: float = Query(0)):
    """记录模拟交易结果"""
    strategy_monitor.record_trade(pair, pnl_pips)
    return strategy_monitor.get_all_health()

@app.post("/api/strategy-monitor/unfreeze")
async def unfreeze_pair(pair: str = Query("AUD/USD")):
    """解冻品种"""
    strategy_monitor.unfreeze(pair)
    return strategy_monitor.get_all_health()

@app.post("/api/strategy-monitor/reset-daily")
async def reset_daily_monitor():
    """每日重置"""
    strategy_monitor.reset_daily()
    return strategy_monitor.get_all_health()

# ─── Feature Engine API ────────────────────────────────────────────────────────

@app.get("/api/features/{pair_key}")
async def get_features(pair_key: str):
    """获取品种实时特征 (vol_ratio, spread_ratio, trend_score)"""
    pair = pair_key.replace("_", "/")
    prices = storage.prices.get(pair, [])
    if not prices:
        return {"error": "No price data"}
    price_data = {"mid": prices[-1]["close"], "spread_pips": 1.5, "bid": prices[-1]["close"], "ask": prices[-1]["close"]}
    snapshot = feature_engine.update(pair, price_data)
    return {
        "pair": pair,
        "vol_1m": snapshot.vol_1m,
        "vol_5m": snapshot.vol_5m,
        "vol_ratio": snapshot.vol_ratio,
        "spread_pips": snapshot.spread_pips,
        "spread_ratio": snapshot.spread_ratio,
        "trend_score_5m": snapshot.trend_score_5m,
        "price": snapshot.price,
    }

# ─── System Logs ───────────────────────────────────────────────────────────────

@app.get("/api/system/logs")
async def system_logs(limit: int = Query(100, ge=1, le=1000)):
    return {"count": len(storage.logs[:limit]), "logs": storage.logs[:limit]}

# ─── Telegram Alert APIs ───────────────────────────────────────────────────────

class TelegramConfigUpdate(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None

class TelegramTestMessage(BaseModel):
    message: str = "Test message from FX Trading System"

@app.post("/api/telegram/config")
async def update_telegram_config(body: TelegramConfigUpdate):
    """更新Telegram配置（运行时 + 持久化到MongoDB）"""
    if body.bot_token is not None:
        settings.telegram_bot_token = body.bot_token
    if body.chat_id is not None:
        settings.telegram_chat_id = body.chat_id
    db.save_telegram_config(settings.telegram_bot_token, settings.telegram_chat_id)
    return {
        "success": True,
        "configured": settings.telegram_configured,
        "bot_token_set": bool(settings.telegram_bot_token),
        "chat_id_set": bool(settings.telegram_chat_id),
    }

@app.get("/api/telegram/status")
async def telegram_status():
    """获取Telegram配置状态"""
    stats = alert_service.get_daily_stats()
    return {
        "configured": settings.telegram_configured,
        "daily_alerts_sent": stats["alert_count"],
        "bot_token_set": bool(settings.telegram_bot_token),
        "chat_id_set": bool(settings.telegram_chat_id),
    }

@app.post("/api/telegram/test")
async def telegram_test_message(body: TelegramTestMessage):
    """发送测试消息"""
    success = await alert_service.send_telegram(f"🔔 <b>TEST</b>\n{body.message}")
    return {"success": success, "message": "Test message sent" if success else "Failed to send (check configuration)"}

@app.get("/api/telegram/history")
async def telegram_alert_history(limit: int = Query(50, ge=1, le=200)):
    """获取警报历史"""
    return {"alerts": alert_service.get_alert_history(limit)}

@app.post("/api/telegram/send-daily-summary")
async def send_daily_summary():
    """发送每日交易摘要"""
    stats = storage.risk_control._daily_stats
    await alert_service.alert_daily_summary(stats)
    return {"success": True, "message": "Daily summary sent"}

@app.post("/api/telegram/send-signal-alert")
async def send_signal_alert(pair: str, direction: str, confidence: float, reason: str = "Manual signal"):
    """手动发送信号警报"""
    signal = {
        "pair": _normalize_pair(pair),
        "direction": direction.upper(),
        "confidence": confidence,
        "regime": "MANUAL",
        "reason": reason,
    }
    await alert_service.alert_signal(signal)
    return {"success": True, "signal": signal}

@app.post("/api/telegram/send-risk-alert")
async def send_risk_alert(alert_type: str, message: str):
    """发送风险警报"""
    if alert_type == "WARNING":
        await alert_service.alert_risk_warning("Manual Warning", {"message": message})
    elif alert_type == "EMERGENCY":
        await alert_service.alert_risk_emergency(message, storage.risk_control._daily_stats)
    else:
        await alert_service.send_telegram(f"⚠️ {message}")
    return {"success": True}

# ─── Risk Control APIs (高级风险控制) ──────────────────────────────────────────

class StopLossLevelsUpdate(BaseModel):
    warning_pips: Optional[float] = None
    reduction_pips: Optional[float] = None
    primary_stop_pips: Optional[float] = None
    disaster_stop_pips: Optional[float] = None

class DailyLimitsUpdate(BaseModel):
    max_daily_loss_pips: Optional[float] = None
    max_daily_loss_percent: Optional[float] = None
    max_daily_trades: Optional[int] = None
    max_consecutive_losses: Optional[int] = None

@app.get("/api/risk/status")
async def risk_control_status():
    """获取完整的风险控制状态"""
    return storage.risk_control.get_status()

@app.get("/api/risk/capital-protection")
async def capital_protection_summary():
    """获取资金保护摘要"""
    return storage.risk_control.get_capital_protection_summary()

@app.get("/api/risk/events")
async def risk_events():
    """获取风险事件历史"""
    return {"events": storage.risk_control.get_risk_events()}

@app.post("/api/risk/check-entry")
async def check_entry_permission(pair: str, direction: str = "BUY", spread_pips: float = 1.5):
    """检查是否允许入场"""
    pair = _normalize_pair(pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=400, detail=f"Pair {pair} not supported")
    
    return storage.risk_control.check_entry_allowed(pair, direction, spread_pips)

@app.post("/api/risk/check-deterioration")
async def check_market_deterioration(pair: str, current_price: float, spread_pips: float = 1.5):
    """检测市场恶化情况"""
    pair = _normalize_pair(pair)
    if pair not in settings.pairs:
        raise HTTPException(status_code=400, detail=f"Pair {pair} not supported")
    
    return storage.risk_control.check_market_deterioration(pair, current_price, spread_pips)

@app.post("/api/risk/process-trade")
async def process_trade_result(pnl_pips: float, pair: str):
    """处理交易结果"""
    pair = _normalize_pair(pair)
    result = storage.risk_control.process_trade_result(pnl_pips, pair)
    
    # 广播风险状态更新
    status = storage.risk_control.get_status()
    await market_data.broadcast({"type": "risk_status", "data": status})
    
    return result

@app.post("/api/risk/check-position")
async def check_position_risk(pair: str, entry_price: float, current_price: float, direction: str = "BUY"):
    """检查持仓风险"""
    pair = _normalize_pair(pair)
    return storage.risk_control.check_position_risk(pair, entry_price, current_price, direction)

@app.post("/api/risk/trigger-warning")
async def manual_trigger_warning(reason: str = "Manual warning"):
    """手动触发警告状态"""
    storage.risk_control._trigger_warning(reason)
    status = storage.risk_control.get_status()
    await market_data.broadcast({"type": "risk_status", "data": status})
    return status

@app.post("/api/risk/trigger-emergency")
async def manual_trigger_emergency(reason: str = "Manual emergency"):
    """手动触发紧急平仓"""
    storage.risk_control._trigger_emergency(reason)
    status = storage.risk_control.get_status()
    await market_data.broadcast({"type": "risk_status", "data": status})
    return status

@app.post("/api/risk/end-cooldown")
async def end_cooldown_period():
    """结束冷却期，进入渐进重启"""
    status = storage.risk_control.end_cooldown()
    await market_data.broadcast({"type": "risk_status", "data": status})
    return status

@app.post("/api/risk/advance-restart")
async def advance_graduated_restart():
    """推进渐进重启步骤"""
    status = storage.risk_control.advance_graduated_step()
    await market_data.broadcast({"type": "risk_status", "data": status})
    return status

@app.post("/api/risk/reset")
async def reset_risk_control():
    """强制重置风险控制系统"""
    status = storage.risk_control.reset_to_normal()
    await market_data.broadcast({"type": "risk_status", "data": status})
    return status

@app.post("/api/risk/reset-daily")
async def reset_daily_stats():
    """重置每日统计"""
    return storage.risk_control.reset_daily_stats()

@app.put("/api/risk/stop-loss-levels")
async def update_stop_loss_levels(body: StopLossLevelsUpdate):
    """更新多层级止损配置"""
    updates = {k: v for k, v in body.dict().items() if v is not None}
    return storage.risk_control.update_stop_loss_levels(updates)

@app.put("/api/risk/daily-limits")
async def update_daily_limits(body: DailyLimitsUpdate):
    """更新每日风险限额"""
    updates = {k: v for k, v in body.dict().items() if v is not None}
    return storage.risk_control.update_daily_limits(updates)

@app.get("/api/risk/config")
async def get_risk_config():
    """获取完整风险控制配置"""
    rc = storage.risk_control
    return {
        "stop_loss_levels": rc.stop_loss_levels,
        "daily_limits": rc.daily_limits,
        "weekly_limits": rc.weekly_limits,
        "deterioration_thresholds": rc.deterioration_thresholds,
        "cooldown_config": rc.cooldown_config,
        "position_config": rc.position_config,
    }

# ─── Backtest Module ───────────────────────────────────────────────────────────

@app.get("/api/backtest/results")
async def backtest_results(
    pair: Optional[str] = None,
    event_level: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200)
):
    """Get historical backtest results with optional filtering"""
    results = storage.backtest_results.copy()
    
    if pair:
        pair = _normalize_pair(pair)
        results = [r for r in results if r["pair"] == pair]
    
    if event_level:
        results = [r for r in results if r["event_level"] == event_level.upper()]
    
    return {
        "count": len(results[:limit]),
        "results": results[:limit],
    }

@app.get("/api/backtest/stats")
async def backtest_stats():
    """Get aggregated backtest statistics for 30-second confirmation mechanism"""
    stats = storage.confirmation_stats
    
    # Calculate overall stats
    all_results = storage.backtest_results
    
    if not all_results:
        return {"error": "No backtest data available"}
    
    # By pair statistics
    pair_stats = {}
    for pair in ["AUD/USD", "NZD/USD"]:
        pair_results = [r for r in all_results if r["pair"] == pair]
        if pair_results:
            successes = [r for r in pair_results if r["confirmation_success"]]
            total_pnl = sum(r["pnl_pips"] for r in pair_results)
            avg_pnl = total_pnl / len(pair_results)
            win_rate = len(successes) / len(pair_results) * 100
            
            # By event level
            level_stats = {}
            for level in ["A", "B"]:
                level_results = [r for r in pair_results if r["event_level"] == level]
                if level_results:
                    level_successes = [r for r in level_results if r["confirmation_success"]]
                    level_stats[level] = {
                        "total_trades": len(level_results),
                        "successful": len(level_successes),
                        "success_rate": round(len(level_successes) / len(level_results) * 100, 1),
                        "avg_pnl_pips": round(sum(r["pnl_pips"] for r in level_results) / len(level_results), 1),
                    }
            
            pair_stats[pair] = {
                "total_trades": len(pair_results),
                "win_rate": round(win_rate, 1),
                "total_pnl_pips": round(total_pnl, 1),
                "avg_pnl_pips": round(avg_pnl, 1),
                "avg_hold_duration": round(sum(r["hold_duration_minutes"] for r in pair_results) / len(pair_results), 1),
                "by_event_level": level_stats,
            }
    
    # Overall statistics
    total_trades = len(all_results)
    total_successes = len([r for r in all_results if r["confirmation_success"]])
    total_pnl = sum(r["pnl_pips"] for r in all_results)
    
    # Best performing event types
    event_performance = {}
    for result in all_results:
        event_type = result["event_title"]
        if event_type not in event_performance:
            event_performance[event_type] = {"total": 0, "success": 0, "pnl": 0}
        event_performance[event_type]["total"] += 1
        event_performance[event_type]["pnl"] += result["pnl_pips"]
        if result["confirmation_success"]:
            event_performance[event_type]["success"] += 1
    
    best_events = sorted(
        [
            {
                "event": k,
                "success_rate": round(v["success"] / v["total"] * 100, 1),
                "avg_pnl": round(v["pnl"] / v["total"], 1),
                "total_trades": v["total"],
            }
            for k, v in event_performance.items()
        ],
        key=lambda x: x["success_rate"],
        reverse=True
    )[:5]
    
    return {
        "summary": {
            "total_trades": total_trades,
            "overall_success_rate": round(total_successes / total_trades * 100, 1) if total_trades else 0,
            "total_pnl_pips": round(total_pnl, 1),
            "avg_pnl_per_trade": round(total_pnl / total_trades, 1) if total_trades else 0,
        },
        "by_pair": pair_stats,
        "best_performing_events": best_events,
        "confirmation_window_analysis": {
            "optimal_window_seconds": 30,
            "a_level_success_rate": round(stats["AUD/USD"]["A"]["success"] / max(stats["AUD/USD"]["A"]["total"], 1) * 100, 1),
            "b_level_success_rate": round(stats["AUD/USD"]["B"]["success"] / max(stats["AUD/USD"]["B"]["total"], 1) * 100, 1),
            "recommendation": "30秒确认窗口对A级事件效果最佳，建议保持当前参数",
        },
    }

@app.get("/api/backtest/chart-data")
async def backtest_chart_data(pair: Optional[str] = None):
    """Get chart-ready backtest data for visualization"""
    results = storage.backtest_results.copy()
    
    if pair:
        pair = _normalize_pair(pair)
        results = [r for r in results if r["pair"] == pair]
    
    # Sort by timestamp
    results.sort(key=lambda x: x["timestamp"])
    
    # Cumulative PnL
    cumulative_pnl = 0
    chart_data = []
    for i, r in enumerate(results):
        cumulative_pnl += r["pnl_pips"]
        chart_data.append({
            "index": i + 1,
            "timestamp": r["timestamp"],
            "pnl": r["pnl_pips"],
            "cumulative_pnl": round(cumulative_pnl, 1),
            "success": r["confirmation_success"],
            "event_level": r["event_level"],
        })
    
    return {
        "pair": pair or "ALL",
        "data_points": len(chart_data),
        "chart_data": chart_data,
    }

# ─── Monte Carlo Simulation ────────────────────────────────────────────────────

class MonteCarloSimulator:
    """Monte Carlo simulation for strategy robustness analysis"""
    
    def __init__(self, pnl_data: list[float], num_simulations: int = 1000, num_trades: int = 100):
        self.pnl_data = np.array(pnl_data, dtype=np.float64)
        self.num_simulations = num_simulations
        self.num_trades = num_trades
        self.mean_pnl = np.mean(self.pnl_data)
        self.std_pnl = np.std(self.pnl_data)
    
    def run_simulation(self) -> dict:
        """Run Monte Carlo simulation and return comprehensive statistics"""
        if len(self.pnl_data) < 5:
            return {"error": "Insufficient historical data for simulation"}
        
        # Generate random trade sequences
        simulated_paths = []
        final_pnls = []
        max_drawdowns = []
        win_rates = []
        
        for _ in range(self.num_simulations):
            # Bootstrap sampling from historical PnL
            sampled_pnls = np.random.choice(self.pnl_data, size=self.num_trades, replace=True)
            
            # Calculate cumulative PnL path
            cumulative = np.cumsum(sampled_pnls)
            simulated_paths.append(cumulative.tolist())
            final_pnls.append(cumulative[-1])
            
            # Calculate max drawdown
            running_max = np.maximum.accumulate(cumulative)
            drawdown = running_max - cumulative
            max_dd = np.max(drawdown)
            max_drawdowns.append(max_dd)
            
            # Calculate win rate
            wins = np.sum(sampled_pnls > 0)
            win_rates.append(wins / self.num_trades * 100)
        
        final_pnls = np.array(final_pnls)
        max_drawdowns = np.array(max_drawdowns)
        win_rates = np.array(win_rates)
        
        # Calculate risk metrics
        var_95 = np.percentile(final_pnls, 5)  # Value at Risk 95%
        var_99 = np.percentile(final_pnls, 1)  # Value at Risk 99%
        cvar_95 = np.mean(final_pnls[final_pnls <= var_95])  # Conditional VaR
        
        # Sharpe-like ratio (assuming risk-free rate = 0)
        avg_return = np.mean(final_pnls)
        std_return = np.std(final_pnls)
        sharpe_ratio = avg_return / std_return if std_return > 0 else 0
        
        # Probability of profit
        prob_profit = np.sum(final_pnls > 0) / self.num_simulations * 100
        
        # Percentile distribution
        percentiles = {
            "p5": round(np.percentile(final_pnls, 5), 1),
            "p10": round(np.percentile(final_pnls, 10), 1),
            "p25": round(np.percentile(final_pnls, 25), 1),
            "p50": round(np.percentile(final_pnls, 50), 1),
            "p75": round(np.percentile(final_pnls, 75), 1),
            "p90": round(np.percentile(final_pnls, 90), 1),
            "p95": round(np.percentile(final_pnls, 95), 1),
        }
        
        # Distribution histogram data
        hist_bins = 20
        hist_counts, hist_edges = np.histogram(final_pnls, bins=hist_bins)
        histogram_data = [
            {
                "range_start": round(hist_edges[i], 1),
                "range_end": round(hist_edges[i + 1], 1),
                "count": int(hist_counts[i]),
                "percentage": round(hist_counts[i] / self.num_simulations * 100, 1),
            }
            for i in range(len(hist_counts))
        ]
        
        # Sample paths for visualization (10 representative paths)
        sample_indices = np.linspace(0, self.num_simulations - 1, 10, dtype=int)
        sample_paths = [
            {"path_id": i, "values": [round(v, 1) for v in simulated_paths[idx]]}
            for i, idx in enumerate(sample_indices)
        ]
        
        # Position sizing recommendations
        kelly_fraction = self._calculate_kelly_fraction()
        recommended_risk = self._calculate_recommended_risk(max_drawdowns)
        
        return {
            "simulation_params": {
                "num_simulations": self.num_simulations,
                "trades_per_simulation": self.num_trades,
                "historical_trades": len(self.pnl_data),
            },
            "pnl_statistics": {
                "mean": round(np.mean(final_pnls), 1),
                "median": round(np.median(final_pnls), 1),
                "std_dev": round(std_return, 1),
                "min": round(np.min(final_pnls), 1),
                "max": round(np.max(final_pnls), 1),
                "skewness": round(float(self._calculate_skewness(final_pnls)), 2),
            },
            "risk_metrics": {
                "var_95": round(var_95, 1),
                "var_99": round(var_99, 1),
                "cvar_95": round(cvar_95, 1) if not np.isnan(cvar_95) else None,
                "max_drawdown_mean": round(np.mean(max_drawdowns), 1),
                "max_drawdown_worst": round(np.max(max_drawdowns), 1),
                "sharpe_ratio": round(sharpe_ratio, 2),
            },
            "probability_analysis": {
                "prob_profit": round(prob_profit, 1),
                "prob_loss": round(100 - prob_profit, 1),
                "prob_exceed_50_pips": round(np.sum(final_pnls > 50) / self.num_simulations * 100, 1),
                "prob_exceed_100_pips": round(np.sum(final_pnls > 100) / self.num_simulations * 100, 1),
                "prob_drawdown_exceed_50": round(np.sum(max_drawdowns > 50) / self.num_simulations * 100, 1),
            },
            "win_rate_distribution": {
                "mean": round(np.mean(win_rates), 1),
                "min": round(np.min(win_rates), 1),
                "max": round(np.max(win_rates), 1),
            },
            "percentiles": percentiles,
            "histogram": histogram_data,
            "sample_paths": sample_paths,
            "position_sizing": {
                "kelly_fraction": round(kelly_fraction * 100, 1),
                "half_kelly": round(kelly_fraction * 50, 1),
                "recommended_risk_per_trade": recommended_risk,
                "max_position_size_suggestion": f"{recommended_risk['conservative']}% - {recommended_risk['moderate']}% of capital per trade",
            },
            "robustness_score": self._calculate_robustness_score(prob_profit, sharpe_ratio, max_drawdowns),
        }
    
    def _calculate_kelly_fraction(self) -> float:
        """Calculate Kelly Criterion for optimal position sizing"""
        wins = self.pnl_data[self.pnl_data > 0]
        losses = self.pnl_data[self.pnl_data < 0]
        
        if len(wins) == 0 or len(losses) == 0:
            return 0.0
        
        win_rate = len(wins) / len(self.pnl_data)
        avg_win = np.mean(wins)
        avg_loss = abs(np.mean(losses))
        
        if avg_loss == 0:
            return 0.0
        
        win_loss_ratio = avg_win / avg_loss
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        return max(0, min(kelly, 0.5))  # Cap at 50%
    
    def _calculate_recommended_risk(self, max_drawdowns: np.ndarray) -> dict:
        """Calculate recommended risk levels based on drawdown analysis"""
        avg_dd = np.mean(max_drawdowns)
        worst_dd = np.max(max_drawdowns)
        
        # Conservative: survive worst case with 3x buffer
        conservative = max(0.5, min(5, 100 / (worst_dd * 3) if worst_dd > 0 else 2))
        # Moderate: survive worst case with 2x buffer
        moderate = max(1, min(10, 100 / (worst_dd * 2) if worst_dd > 0 else 3))
        # Aggressive: survive average drawdown with 1.5x buffer
        aggressive = max(2, min(15, 100 / (avg_dd * 1.5) if avg_dd > 0 else 5))
        
        return {
            "conservative": round(conservative, 1),
            "moderate": round(moderate, 1),
            "aggressive": round(aggressive, 1),
        }
    
    def _calculate_skewness(self, data: np.ndarray) -> float:
        """Calculate skewness of distribution"""
        n = len(data)
        if n < 3:
            return 0.0
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return np.mean(((data - mean) / std) ** 3)
    
    def _calculate_robustness_score(self, prob_profit: float, sharpe: float, max_drawdowns: np.ndarray) -> dict:
        """Calculate overall strategy robustness score (0-100)"""
        # Score components
        profit_score = min(prob_profit, 100) * 0.3
        sharpe_score = min(max(sharpe + 1, 0), 3) / 3 * 100 * 0.3
        drawdown_score = max(0, 100 - np.mean(max_drawdowns)) * 0.4
        
        total_score = profit_score + sharpe_score + drawdown_score
        
        if total_score >= 70:
            rating = "优秀 (Excellent)"
            recommendation = "策略表现稳健，可考虑适度增加仓位"
        elif total_score >= 50:
            rating = "良好 (Good)"
            recommendation = "策略整体可行，建议使用半凯利公式管理仓位"
        elif total_score >= 30:
            rating = "一般 (Fair)"
            recommendation = "策略存在风险，建议保守仓位并持续优化"
        else:
            rating = "需改进 (Needs Improvement)"
            recommendation = "策略风险较高，建议重新评估参数或暂停使用"
        
        return {
            "score": round(total_score, 1),
            "rating": rating,
            "recommendation": recommendation,
            "components": {
                "profit_probability": round(profit_score / 0.3, 1),
                "risk_adjusted_return": round(sharpe_score / 0.3, 1),
                "drawdown_control": round(drawdown_score / 0.4, 1),
            },
        }


@app.get("/api/backtest/monte-carlo")
async def monte_carlo_simulation(
    num_simulations: int = Query(1000, ge=100, le=10000),
    trades_per_sim: int = Query(100, ge=20, le=500),
    pair: Optional[str] = None,
):
    """Run Monte Carlo simulation on historical backtest data"""
    results = storage.backtest_results.copy()
    
    if pair:
        pair = _normalize_pair(pair)
        results = [r for r in results if r["pair"] == pair]
    
    if len(results) < 10:
        return {
            "error": "Insufficient historical data",
            "message": "Need at least 10 historical trades for Monte Carlo simulation",
            "available_trades": len(results),
        }
    
    pnl_data = [r["pnl_pips"] for r in results]
    
    simulator = MonteCarloSimulator(
        pnl_data=pnl_data,
        num_simulations=num_simulations,
        num_trades=trades_per_sim,
    )
    
    simulation_result = simulator.run_simulation()
    simulation_result["pair_filter"] = pair or "ALL"
    simulation_result["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    return simulation_result

# ─── Grid Search Optimizer ─────────────────────────────────────────────────────

class GridSearchOptimizer:
    """Grid search for optimal strategy parameters"""
    
    def __init__(self, historical_trades: list[dict]):
        self.trades = historical_trades
        self.base_pnls = [t["pnl_pips"] for t in historical_trades]
    
    def _simulate_with_params(
        self, 
        cooldown_a: int, 
        cooldown_b: int, 
        stop_loss: float, 
        take_profit: float,
        confirmation_window: int,
        num_simulations: int = 200
    ) -> dict:
        """Simulate strategy performance with given parameters"""
        
        # Adjust PnL based on stop loss and take profit ratio
        base_win_rate = len([p for p in self.base_pnls if p > 0]) / len(self.base_pnls)
        base_avg_win = np.mean([p for p in self.base_pnls if p > 0]) if any(p > 0 for p in self.base_pnls) else 10
        base_avg_loss = abs(np.mean([p for p in self.base_pnls if p < 0])) if any(p < 0 for p in self.base_pnls) else 10
        
        # Risk-reward ratio impact
        rr_ratio = take_profit / stop_loss if stop_loss > 0 else 1.5
        
        # Higher RR means lower win rate but bigger wins
        adjusted_win_rate = base_win_rate * (1 / (0.5 + rr_ratio * 0.3))
        adjusted_win_rate = max(0.3, min(0.85, adjusted_win_rate))
        
        # Confirmation window impact (longer window = slightly higher accuracy but fewer trades)
        window_factor = 1 + (confirmation_window - 30) * 0.005  # baseline is 30s
        adjusted_win_rate *= min(1.15, max(0.9, window_factor))
        
        # Cooldown impact (appropriate cooldown improves accuracy)
        optimal_a = 30
        optimal_b = 20
        cooldown_penalty = abs(cooldown_a - optimal_a) * 0.002 + abs(cooldown_b - optimal_b) * 0.003
        adjusted_win_rate = max(0.25, adjusted_win_rate - cooldown_penalty)
        
        # Generate simulated trades
        simulated_results = []
        for _ in range(num_simulations):
            trades_pnl = []
            for _ in range(50):  # 50 trades per simulation
                if random.random() < adjusted_win_rate:
                    # Win
                    pnl = take_profit * random.uniform(0.7, 1.0)
                else:
                    # Loss
                    pnl = -stop_loss * random.uniform(0.7, 1.0)
                trades_pnl.append(pnl)
            
            total_pnl = sum(trades_pnl)
            wins = len([p for p in trades_pnl if p > 0])
            
            # Calculate drawdown
            cumsum = np.cumsum(trades_pnl)
            running_max = np.maximum.accumulate(cumsum)
            drawdown = np.max(running_max - cumsum)
            
            simulated_results.append({
                "total_pnl": total_pnl,
                "win_rate": wins / 50 * 100,
                "max_drawdown": drawdown,
            })
        
        # Aggregate results
        total_pnls = [r["total_pnl"] for r in simulated_results]
        win_rates = [r["win_rate"] for r in simulated_results]
        drawdowns = [r["max_drawdown"] for r in simulated_results]
        
        avg_pnl = np.mean(total_pnls)
        std_pnl = np.std(total_pnls)
        sharpe = avg_pnl / std_pnl if std_pnl > 0 else 0
        
        # Calculate composite score
        pnl_score = min(100, max(0, (avg_pnl + 200) / 4))  # Scale PnL to 0-100
        risk_score = min(100, max(0, 100 - np.mean(drawdowns)))
        consistency_score = min(100, np.mean(win_rates))
        
        composite_score = pnl_score * 0.4 + risk_score * 0.35 + consistency_score * 0.25
        
        return {
            "params": {
                "cooldown_a": cooldown_a,
                "cooldown_b": cooldown_b,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "confirmation_window": confirmation_window,
            },
            "metrics": {
                "avg_pnl": round(avg_pnl, 1),
                "std_pnl": round(std_pnl, 1),
                "sharpe_ratio": round(sharpe, 2),
                "avg_win_rate": round(np.mean(win_rates), 1),
                "avg_max_drawdown": round(np.mean(drawdowns), 1),
                "prob_profit": round(len([p for p in total_pnls if p > 0]) / len(total_pnls) * 100, 1),
            },
            "scores": {
                "pnl_score": round(pnl_score, 1),
                "risk_score": round(risk_score, 1),
                "consistency_score": round(consistency_score, 1),
                "composite_score": round(composite_score, 1),
            },
        }
    
    def run_grid_search(
        self,
        cooldown_a_range: list[int] = None,
        cooldown_b_range: list[int] = None,
        stop_loss_range: list[float] = None,
        take_profit_range: list[float] = None,
        confirmation_window_range: list[int] = None,
    ) -> dict:
        """Run grid search across parameter combinations"""
        
        # Default ranges
        if cooldown_a_range is None:
            cooldown_a_range = [20, 25, 30, 35, 40]
        if cooldown_b_range is None:
            cooldown_b_range = [10, 15, 20, 25, 30]
        if stop_loss_range is None:
            stop_loss_range = [10, 12, 15, 18, 20]
        if take_profit_range is None:
            take_profit_range = [15, 20, 25, 30, 35]
        if confirmation_window_range is None:
            confirmation_window_range = [20, 25, 30, 35, 40]
        
        total_combinations = (
            len(cooldown_a_range) * 
            len(cooldown_b_range) * 
            len(stop_loss_range) * 
            len(take_profit_range) * 
            len(confirmation_window_range)
        )
        
        results = []
        
        for cooldown_a in cooldown_a_range:
            for cooldown_b in cooldown_b_range:
                for stop_loss in stop_loss_range:
                    for take_profit in take_profit_range:
                        for confirmation_window in confirmation_window_range:
                            result = self._simulate_with_params(
                                cooldown_a=cooldown_a,
                                cooldown_b=cooldown_b,
                                stop_loss=stop_loss,
                                take_profit=take_profit,
                                confirmation_window=confirmation_window,
                            )
                            results.append(result)
        
        # Sort by composite score
        results.sort(key=lambda x: x["scores"]["composite_score"], reverse=True)
        
        # Get top 10 results
        top_results = results[:10]
        
        # Analyze parameter sensitivity
        param_sensitivity = self._analyze_sensitivity(results)
        
        # Best parameters
        best = results[0]
        worst = results[-1]
        
        return {
            "search_info": {
                "total_combinations": total_combinations,
                "parameters_tested": {
                    "cooldown_a": cooldown_a_range,
                    "cooldown_b": cooldown_b_range,
                    "stop_loss": stop_loss_range,
                    "take_profit": take_profit_range,
                    "confirmation_window": confirmation_window_range,
                },
            },
            "best_parameters": best,
            "top_10_results": top_results,
            "worst_parameters": worst,
            "parameter_sensitivity": param_sensitivity,
            "recommendations": self._generate_recommendations(best, param_sensitivity),
        }
    
    def _analyze_sensitivity(self, results: list[dict]) -> dict:
        """Analyze which parameters have most impact on performance"""
        
        params_impact = {
            "cooldown_a": {},
            "cooldown_b": {},
            "stop_loss": {},
            "take_profit": {},
            "confirmation_window": {},
        }
        
        for param_name in params_impact.keys():
            param_values = {}
            for r in results:
                val = r["params"][param_name]
                if val not in param_values:
                    param_values[val] = []
                param_values[val].append(r["scores"]["composite_score"])
            
            # Calculate average score for each parameter value
            avg_scores = {k: round(np.mean(v), 1) for k, v in param_values.items()}
            best_val = max(avg_scores, key=avg_scores.get)
            worst_val = min(avg_scores, key=avg_scores.get)
            impact = avg_scores[best_val] - avg_scores[worst_val]
            
            params_impact[param_name] = {
                "scores_by_value": avg_scores,
                "best_value": best_val,
                "worst_value": worst_val,
                "impact_range": round(impact, 1),
            }
        
        # Rank parameters by impact
        ranked = sorted(
            params_impact.items(),
            key=lambda x: x[1]["impact_range"],
            reverse=True
        )
        
        return {
            "by_parameter": params_impact,
            "impact_ranking": [
                {"parameter": k, "impact": v["impact_range"], "best_value": v["best_value"]}
                for k, v in ranked
            ],
        }
    
    def _generate_recommendations(self, best: dict, sensitivity: dict) -> list[dict]:
        """Generate actionable recommendations"""
        
        recommendations = []
        
        # Best parameters recommendation
        bp = best["params"]
        recommendations.append({
            "type": "optimal_config",
            "priority": "高",
            "title": "最优参数配置",
            "description": f"A级冷却: {bp['cooldown_a']}s, B级冷却: {bp['cooldown_b']}s, 止损: {bp['stop_loss']} pips, 止盈: {bp['take_profit']} pips, 确认窗口: {bp['confirmation_window']}s",
            "expected_score": best["scores"]["composite_score"],
        })
        
        # Risk-reward ratio
        rr_ratio = bp["take_profit"] / bp["stop_loss"]
        recommendations.append({
            "type": "risk_reward",
            "priority": "高",
            "title": "风险收益比",
            "description": f"推荐风险收益比 1:{rr_ratio:.1f}，止损{bp['stop_loss']}pips，止盈{bp['take_profit']}pips",
            "expected_score": None,
        })
        
        # Most sensitive parameter
        top_sensitive = sensitivity["impact_ranking"][0]
        recommendations.append({
            "type": "sensitivity",
            "priority": "中",
            "title": f"关键参数: {top_sensitive['parameter']}",
            "description": f"该参数对策略影响最大({top_sensitive['impact']}分差)，建议优先设置为 {top_sensitive['best_value']}",
            "expected_score": None,
        })
        
        # Confirmation window recommendation
        cw = bp["confirmation_window"]
        if cw < 30:
            cw_advice = "较短确认窗口可能增加误判风险，但能更快入场"
        elif cw > 30:
            cw_advice = "较长确认窗口提高准确性，但可能错过部分机会"
        else:
            cw_advice = "30秒是经典的确认窗口，平衡了准确性和时效性"
        
        recommendations.append({
            "type": "confirmation",
            "priority": "中",
            "title": f"确认窗口: {cw}秒",
            "description": cw_advice,
            "expected_score": None,
        })
        
        return recommendations


class GridSearchRequest(BaseModel):
    cooldown_a_range: Optional[list[int]] = None
    cooldown_b_range: Optional[list[int]] = None
    stop_loss_range: Optional[list[float]] = None
    take_profit_range: Optional[list[float]] = None
    confirmation_window_range: Optional[list[int]] = None


@app.post("/api/backtest/grid-search")
async def run_grid_search(request: GridSearchRequest = None):
    """Run grid search optimization to find best parameters"""
    
    if len(storage.backtest_results) < 10:
        return {
            "error": "Insufficient historical data",
            "message": "Need at least 10 historical trades for grid search",
            "available_trades": len(storage.backtest_results),
        }
    
    optimizer = GridSearchOptimizer(storage.backtest_results)
    
    params = {}
    if request:
        if request.cooldown_a_range:
            params["cooldown_a_range"] = request.cooldown_a_range
        if request.cooldown_b_range:
            params["cooldown_b_range"] = request.cooldown_b_range
        if request.stop_loss_range:
            params["stop_loss_range"] = request.stop_loss_range
        if request.take_profit_range:
            params["take_profit_range"] = request.take_profit_range
        if request.confirmation_window_range:
            params["confirmation_window_range"] = request.confirmation_window_range
    
    result = optimizer.run_grid_search(**params)
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    return result


@app.get("/api/backtest/grid-search/quick")
async def quick_grid_search():
    """Run a quick grid search with default parameters"""
    
    if len(storage.backtest_results) < 10:
        return {
            "error": "Insufficient historical data",
            "message": "Need at least 10 historical trades for grid search",
            "available_trades": len(storage.backtest_results),
        }
    
    optimizer = GridSearchOptimizer(storage.backtest_results)
    result = optimizer.run_grid_search()
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    return result

# ─── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    market_data.register_client(queue)

    try:
        await websocket.send_json({
            "type": "alert",
            "data": {"message": "Connected to FX Trading System WebSocket"},
        })

        current_signals = signal_engine.get_all_latest_signals()
        if current_signals:
            await websocket.send_json({"type": "signal", "data": current_signals})

        await websocket.send_json({"type": "event_state", "data": event_engine.get_event_state()})

        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(message)
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "heartbeat",
                    "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        market_data.unregister_client(queue)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)
