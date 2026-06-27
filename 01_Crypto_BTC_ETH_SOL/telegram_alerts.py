"""
Telegram Alert Service for Crypto AI Trading System
Sends alerts on significant state changes (conviction > 65%)
Scheduled daily summaries at 8:00, 12:00, 18:00, 21:00
"""
import os
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '8670001641')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Conviction threshold for alerts
CONVICTION_THRESHOLD = 65.0


class AlertType(str, Enum):
    TRADING_OPPORTUNITY = "TRADING_OPPORTUNITY"  # BLOCK -> ALLOW
    EXIT_SIGNAL = "EXIT_SIGNAL"  # -> EXIT_NOW
    HIGH_RISK = "HIGH_RISK"  # -> HIGH_FRAGILITY
    SCHEDULED_SUMMARY = "SCHEDULED_SUMMARY"  # Daily summaries


@dataclass
class AlertState:
    """Track previous states to detect changes"""
    gate_action: str = "BLOCK"
    fragility_state: str = "LOW_FRAGILITY"
    regime: str = "NORMAL"


@dataclass
class SignalRecord:
    """Record of a trading signal for daily summary"""
    symbol: str
    timestamp: str
    signal_side: Optional[str]
    direction_score: float
    conviction_score: float
    gate_action: str
    price: float


class TelegramAlertService:
    """
    Telegram alert service for significant trading state changes
    Only sends alerts when conviction > 65% on:
    - BLOCK -> ALLOW/ALLOW_REDUCED (Trading opportunity)
    - Any -> EXIT_NOW (Emergency exit)
    - LOW/MEDIUM -> HIGH_FRAGILITY (High risk warning)
    
    Also sends scheduled summaries at 8:00, 12:00, 18:00, 21:00
    """
    
    def __init__(self):
        self.previous_states: Dict[str, AlertState] = {
            "BTC": AlertState(),
            "ETH": AlertState(),
            "SOL": AlertState()
        }
        self.enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        self.conviction_threshold = CONVICTION_THRESHOLD
        
        # Store signals for daily summary
        self.signal_history: List[SignalRecord] = []
        self.last_summary_time: Optional[datetime] = None
        
        if self.enabled:
            logger.info(f"Telegram Alert Service initialized (conviction threshold: {self.conviction_threshold}%)")
        else:
            logger.warning("Telegram Alert Service disabled - missing credentials")
    
    def escape_markdown(self, text: str) -> str:
        """Escape special characters for Telegram MarkdownV2"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    async def send_message(self, message: str, parse_mode: str = "MarkdownV2") -> bool:
        """Send a message to Telegram"""
        if not self.enabled:
            logger.warning("Telegram alerts disabled")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{TELEGRAM_API_URL}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": message,
                        "parse_mode": parse_mode
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.info("Telegram alert sent successfully")
                    return True
                else:
                    logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
    
    def _record_signal(self, symbol: str, state: Dict[str, Any]):
        """Record a signal for daily summary"""
        record = SignalRecord(
            symbol=symbol,
            timestamp=state.get("timestamp", datetime.now(timezone.utc).isoformat()),
            signal_side=state.get("signal_side"),
            direction_score=state.get("direction_score", 50),
            conviction_score=state.get("conviction_score", 50),
            gate_action=state.get("gate_action", "BLOCK"),
            price=state.get("price", 0)
        )
        
        self.signal_history.append(record)
        
        # Keep only last 24 hours of signals
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        self.signal_history = [
            s for s in self.signal_history 
            if datetime.fromisoformat(s.timestamp.replace('Z', '+00:00')) > cutoff
        ]
    
    async def check_and_alert(self, symbol: str, current_state: Dict[str, Any]) -> Optional[AlertType]:
        """
        Check for significant state changes and send alerts
        Only alerts when conviction > 65%
        Returns the type of alert sent, or None
        """
        if not self.enabled:
            return None
        
        prev = self.previous_states.get(symbol, AlertState())
        
        gate_action = current_state.get("gate_action", "BLOCK")
        fragility_state = current_state.get("fragility_state", "LOW_FRAGILITY")
        regime = current_state.get("regime", "NORMAL")
        conviction_score = current_state.get("conviction_score", 50)
        
        # Record signal for summary
        if gate_action in ["ALLOW", "ALLOW_REDUCED"] or current_state.get("signal_side"):
            self._record_signal(symbol, current_state)
        
        alert_sent = None
        
        # Check for EXIT_NOW (highest priority - no conviction check)
        if gate_action == "EXIT_NOW" and prev.gate_action != "EXIT_NOW":
            await self._send_exit_alert(symbol, current_state)
            alert_sent = AlertType.EXIT_SIGNAL
        
        # Check for trading opportunity (BLOCK -> ALLOW/ALLOW_REDUCED)
        # Only alert if conviction > 65%
        elif gate_action in ["ALLOW", "ALLOW_REDUCED"] and prev.gate_action == "BLOCK":
            if conviction_score >= self.conviction_threshold:
                await self._send_opportunity_alert(symbol, current_state)
                alert_sent = AlertType.TRADING_OPPORTUNITY
            else:
                logger.info(f"{symbol}: Trading opportunity but conviction {conviction_score:.1f}% < {self.conviction_threshold}% threshold, skipping alert")
        
        # Check for high fragility warning
        # Only alert if conviction was high (we were about to trade)
        elif fragility_state == "HIGH_FRAGILITY" and prev.fragility_state != "HIGH_FRAGILITY":
            if conviction_score >= self.conviction_threshold:
                await self._send_high_risk_alert(symbol, current_state)
                alert_sent = AlertType.HIGH_RISK
        
        # Update previous state
        self.previous_states[symbol] = AlertState(
            gate_action=gate_action,
            fragility_state=fragility_state,
            regime=regime
        )
        
        return alert_sent
    
    async def _send_opportunity_alert(self, symbol: str, state: Dict[str, Any]):
        """Send trading opportunity alert (conviction > 65%)"""
        price = state.get("price", 0)
        direction_score = state.get("direction_score", 50)
        conviction_score = state.get("conviction_score", 50)
        signal_side = state.get("signal_side", "N/A")
        gate_action = state.get("gate_action", "ALLOW")
        
        # Determine direction emoji
        direction_emoji = "📈" if signal_side == "LONG" else "📉" if signal_side == "SHORT" else "➡️"
        
        message = f"""
🚀 *TRADING OPPORTUNITY*

*{self.escape_markdown(symbol)}* {direction_emoji}

💰 Price: ${self.escape_markdown(f"{price:,.2f}")}
📊 Signal: *{self.escape_markdown(signal_side or 'N/A')}*
🎯 Direction Score: {self.escape_markdown(f"{direction_score:.1f}")}/100
💪 Conviction: *{self.escape_markdown(f"{conviction_score:.1f}")}%* \\(\\>{self.escape_markdown(str(int(self.conviction_threshold)))}%\\)

⚡ Gate: *{self.escape_markdown(gate_action)}*

⏰ {self.escape_markdown(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))}
        """.strip()
        
        await self.send_message(message)
    
    async def _send_exit_alert(self, symbol: str, state: Dict[str, Any]):
        """Send emergency exit alert"""
        price = state.get("price", 0)
        gate_reasons = state.get("gate_reasons", [])
        
        message = f"""
🚨 *EMERGENCY EXIT SIGNAL*

*{self.escape_markdown(symbol)}* ⚠️

💰 Current Price: ${self.escape_markdown(f"{price:,.2f}")}

❌ Reason: {self.escape_markdown(", ".join(gate_reasons) if gate_reasons else "Market conditions deteriorated")}

⚡ Action Required: *EXIT NOW*

⏰ {self.escape_markdown(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))}
        """.strip()
        
        await self.send_message(message)
    
    async def _send_high_risk_alert(self, symbol: str, state: Dict[str, Any]):
        """Send high fragility warning"""
        price = state.get("price", 0)
        fragility_score = state.get("fragility_score", 0)
        regime = state.get("regime", "NORMAL")
        conviction_score = state.get("conviction_score", 50)
        
        message = f"""
⚠️ *HIGH RISK WARNING*

*{self.escape_markdown(symbol)}*

💰 Price: ${self.escape_markdown(f"{price:,.2f}")}
📊 Fragility Score: {self.escape_markdown(f"{fragility_score:.1f}")}/100
💪 Conviction was: {self.escape_markdown(f"{conviction_score:.1f}")}%
🔄 Regime: {self.escape_markdown(regime)}

⛔ Status: *HIGH FRAGILITY*
💡 Recommendation: Avoid new positions, consider reducing exposure

⏰ {self.escape_markdown(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))}
        """.strip()
        
        await self.send_message(message)
    
    async def send_scheduled_summary(self, states: Dict[str, Dict[str, Any]], timezone_str: str = "Asia/Shanghai"):
        """
        Send scheduled trading summary
        Called at 8:00, 12:00, 18:00, 21:00 local time
        """
        import pytz
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        
        # Get recent high-conviction signals
        recent_signals = [
            s for s in self.signal_history 
            if s.conviction_score >= self.conviction_threshold
        ]
        
        # Build summary
        lines = [f"📊 *TRADING SUMMARY*\n"]
        lines.append(f"⏰ {self.escape_markdown(now.strftime('%Y-%m-%d %H:%M'))} \\({self.escape_markdown(timezone_str)}\\)\n")
        
        # Current market status
        lines.append("*Current Status:*")
        for symbol, state in states.items():
            price = state.get("price", 0)
            gate_action = state.get("gate_action", "BLOCK")
            conviction = state.get("conviction_score", 50)
            regime = state.get("regime", "NORMAL")
            change = state.get("price_change_24h", 0)
            
            gate_emoji = "✅" if gate_action in ["ALLOW", "ALLOW_REDUCED"] else "🚫" if gate_action == "BLOCK" else "⚠️"
            change_emoji = "📈" if change >= 0 else "📉"
            
            lines.append(f"  *{self.escape_markdown(symbol)}* {gate_emoji}")
            lines.append(f"    💰 ${self.escape_markdown(f'{price:,.2f}')} {change_emoji} {self.escape_markdown(f'{change:+.2f}')}%")
            lines.append(f"    📊 {self.escape_markdown(regime)} \\| Conviction: {self.escape_markdown(f'{conviction:.0f}')}%")
        
        # Recent high-conviction signals
        if recent_signals:
            lines.append(f"\n*Recent High\\-Conviction Signals \\(\\>{self.escape_markdown(str(int(self.conviction_threshold)))}%\\):*")
            for sig in recent_signals[-5:]:  # Last 5 signals
                side_emoji = "📈" if sig.signal_side == "LONG" else "📉" if sig.signal_side == "SHORT" else "➡️"
                sig_time = datetime.fromisoformat(sig.timestamp.replace('Z', '+00:00')).astimezone(tz)
                time_str = sig_time.strftime('%H:%M')
                lines.append(f"  {side_emoji} {self.escape_markdown(sig.symbol)} @ ${self.escape_markdown(f'{sig.price:,.2f}')} \\({self.escape_markdown(time_str)}\\)")
                lines.append(f"      Conv: {self.escape_markdown(f'{sig.conviction_score:.0f}')}% \\| Gate: {self.escape_markdown(sig.gate_action)}")
        else:
            lines.append(f"\n_No high\\-conviction signals since last summary_")
        
        # Data source
        lines.append(f"\n_Data: Binance Real\\-time_")
        
        message = "\n".join(lines)
        await self.send_message(message)
        
        self.last_summary_time = now
    
    async def send_system_status(self, states: Dict[str, Dict[str, Any]]):
        """Send system status summary (can be called manually)"""
        lines = ["📊 *CRYPTO AI TRADING SYSTEM STATUS*\n"]
        
        for symbol, state in states.items():
            price = state.get("price", 0)
            gate_action = state.get("gate_action", "BLOCK")
            regime = state.get("regime", "NORMAL")
            conviction = state.get("conviction_score", 50)
            
            gate_emoji = "✅" if gate_action in ["ALLOW", "ALLOW_REDUCED"] else "🚫" if gate_action == "BLOCK" else "⚠️"
            conviction_indicator = "🔥" if conviction >= self.conviction_threshold else ""
            
            lines.append(f"*{self.escape_markdown(symbol)}* {gate_emoji} {conviction_indicator}")
            lines.append(f"  💰 ${self.escape_markdown(f'{price:,.2f}')}")
            lines.append(f"  📊 {self.escape_markdown(regime)} \\| {self.escape_markdown(gate_action)}")
            lines.append(f"  💪 Conviction: {self.escape_markdown(f'{conviction:.0f}')}%\n")
        
        lines.append(f"⏰ {self.escape_markdown(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))}")
        lines.append(f"\n_Alert threshold: Conviction \\> {self.escape_markdown(str(int(self.conviction_threshold)))}%_")
        
        message = "\n".join(lines)
        await self.send_message(message)
    
    async def send_test_message(self) -> bool:
        """Send a test message to verify configuration"""
        message = f"""
🔔 *Telegram Alert Test*

✅ Your Crypto AI Trading System alerts are configured\\!

*Alert Conditions:*
• 🚀 Trading opportunities \\(Conviction \\> {self.escape_markdown(str(int(self.conviction_threshold)))}%\\)
• 🚨 Emergency exit signals
• ⚠️ High risk warnings

*Scheduled Summaries:*
• 📊 08:00 UTC \\- Morning report
• 📊 12:00 UTC \\- Midday report  
• 📊 18:00 UTC \\- Evening report
• 📊 21:00 UTC \\- Night report

_This is a test message\\._
        """.strip()
        
        return await self.send_message(message)


# Global instance
telegram_alert_service = TelegramAlertService()
