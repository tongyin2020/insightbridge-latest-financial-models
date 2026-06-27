"""
WTI Trading Platform - Tradovate Exchange Integration
Provides real-time market data and order execution via Tradovate API
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
from enum import Enum
import httpx

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    STOP = "Stop"
    STOP_LIMIT = "StopLimit"


class OrderAction(str, Enum):
    BUY = "Buy"
    SELL = "Sell"


class TimeInForce(str, Enum):
    DAY = "Day"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


@dataclass
class TradovateCredentials:
    """Tradovate API credentials"""
    username: str
    password: str
    client_id: str
    client_secret: str
    device_id: str
    is_demo: bool = True


@dataclass
class MarketDataQuote:
    """Real-time market quote"""
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    timestamp: datetime


@dataclass
class OrderResponse:
    """Order execution response"""
    order_id: str
    status: str
    filled_qty: int
    avg_fill_price: float
    message: str


class TradovateClient:
    """
    Tradovate API Client for futures trading
    Supports both demo and live environments
    """
    
    DEMO_AUTH_URL = "https://demo.tradovateapi.com/v1"
    LIVE_AUTH_URL = "https://live.tradovateapi.com/v1"
    DEMO_WS_URL = "wss://demo.tradovateapi.com/v1/websocket"
    LIVE_WS_URL = "wss://live.tradovateapi.com/v1/websocket"
    MD_WS_URL = "wss://md.tradovateapi.com/v1/websocket"
    
    def __init__(self, credentials: Optional[TradovateCredentials] = None):
        self.credentials = credentials or self._load_credentials()
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._ws_connection = None
        self._md_connection = None
        self._quote_callbacks: Dict[str, List[Callable]] = {}
        self._is_connected = False
    
    def _load_credentials(self) -> Optional[TradovateCredentials]:
        """Load credentials from environment variables"""
        username = os.environ.get("TRADOVATE_USERNAME")
        password = os.environ.get("TRADOVATE_PASSWORD")
        client_id = os.environ.get("TRADOVATE_CLIENT_ID")
        client_secret = os.environ.get("TRADOVATE_CLIENT_SECRET")
        device_id = os.environ.get("TRADOVATE_DEVICE_ID", "energy-ai-trading-platform")
        is_demo = os.environ.get("TRADOVATE_IS_DEMO", "true").lower() == "true"
        
        if not all([username, password, client_id, client_secret]):
            logger.warning("[Tradovate] Credentials not configured")
            return None
        
        return TradovateCredentials(
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            device_id=device_id,
            is_demo=is_demo
        )
    
    @property
    def is_configured(self) -> bool:
        return self.credentials is not None
    
    @property
    def base_url(self) -> str:
        if self.credentials and not self.credentials.is_demo:
            return self.LIVE_AUTH_URL
        return self.DEMO_AUTH_URL
    
    async def authenticate(self) -> bool:
        """Authenticate with Tradovate API"""
        if not self.credentials:
            logger.error("[Tradovate] No credentials configured")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/auth/accesstokenrequest",
                    json={
                        "name": self.credentials.username,
                        "password": self.credentials.password,
                        "appId": self.credentials.client_id,
                        "appVersion": "1.0",
                        "cid": self.credentials.client_id,
                        "sec": self.credentials.client_secret,
                        "deviceId": self.credentials.device_id,
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self._access_token = data.get("accessToken")
                    expires_in = data.get("expirationTime", 3600)
                    self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    logger.info("[Tradovate] Authentication successful")
                    return True
                else:
                    logger.error(f"[Tradovate] Auth failed: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"[Tradovate] Auth error: {e}")
            return False
    
    async def get_contracts(self, symbol: str = "CL") -> List[Dict]:
        """Get available contracts for a symbol"""
        if not self._access_token:
            await self.authenticate()
        
        if not self._access_token:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/contract/find",
                    params={"name": symbol},
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"[Tradovate] Get contracts failed: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"[Tradovate] Get contracts error: {e}")
            return []
    
    async def place_order(
        self,
        contract_id: int,
        action: OrderAction,
        qty: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        is_automated: bool = True
    ) -> Optional[OrderResponse]:
        """Place an order on Tradovate"""
        if not self._access_token:
            await self.authenticate()
        
        if not self._access_token:
            return None
        
        order_data = {
            "accountSpec": self.credentials.username,
            "accountId": 0,  # Will be filled by API
            "action": action.value,
            "symbol": "",
            "orderQty": qty,
            "orderType": order_type.value,
            "timeInForce": time_in_force.value,
            "isAutomated": is_automated,
            "contractId": contract_id,
        }
        
        if order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and price:
            order_data["price"] = price
        
        if order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and stop_price:
            order_data["stopPrice"] = stop_price
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/order/placeorder",
                    json=order_data,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return OrderResponse(
                        order_id=str(data.get("orderId", "")),
                        status=data.get("orderStatus", {}).get("status", "Unknown"),
                        filled_qty=data.get("orderStatus", {}).get("filledQty", 0),
                        avg_fill_price=data.get("orderStatus", {}).get("avgPx", 0),
                        message="Order placed successfully"
                    )
                else:
                    logger.error(f"[Tradovate] Place order failed: {response.status_code} - {response.text}")
                    return OrderResponse(
                        order_id="",
                        status="Failed",
                        filled_qty=0,
                        avg_fill_price=0,
                        message=response.text
                    )
                    
        except Exception as e:
            logger.error(f"[Tradovate] Place order error: {e}")
            return None
    
    async def place_bracket_order(
        self,
        contract_id: int,
        action: OrderAction,
        qty: int,
        profit_target: float,
        stop_loss: float,
        is_automated: bool = True
    ) -> Optional[Dict]:
        """Place an OCO bracket order"""
        if not self._access_token:
            await self.authenticate()
        
        if not self._access_token:
            return None
        
        bracket_data = {
            "accountSpec": self.credentials.username,
            "accountId": 0,
            "action": action.value,
            "symbol": "",
            "orderQty": qty,
            "orderType": "Market",
            "isAutomated": is_automated,
            "contractId": contract_id,
            "bracket1": {
                "action": "Sell" if action == OrderAction.BUY else "Buy",
                "orderType": "Limit",
                "price": profit_target,
            },
            "bracket2": {
                "action": "Sell" if action == OrderAction.BUY else "Buy",
                "orderType": "Stop",
                "stopPrice": stop_loss,
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/order/placeoco",
                    json=bracket_data,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"[Tradovate] Bracket order failed: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"[Tradovate] Bracket order error: {e}")
            return None
    
    async def cancel_order(self, order_id: int) -> bool:
        """Cancel an open order"""
        if not self._access_token:
            await self.authenticate()
        
        if not self._access_token:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/order/cancelorder",
                    json={"orderId": order_id},
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=30.0
                )
                
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"[Tradovate] Cancel order error: {e}")
            return False
    
    async def get_positions(self) -> List[Dict]:
        """Get current positions"""
        if not self._access_token:
            await self.authenticate()
        
        if not self._access_token:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/position/list",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"[Tradovate] Get positions error: {e}")
            return []
    
    async def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        if not self._access_token:
            await self.authenticate()
        
        if not self._access_token:
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/account/list",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    accounts = response.json()
                    return accounts[0] if accounts else None
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"[Tradovate] Get account error: {e}")
            return None
    
    def subscribe_quotes(self, symbol: str, callback: Callable[[MarketDataQuote], None]):
        """Subscribe to real-time quotes for a symbol"""
        if symbol not in self._quote_callbacks:
            self._quote_callbacks[symbol] = []
        self._quote_callbacks[symbol].append(callback)
    
    def unsubscribe_quotes(self, symbol: str):
        """Unsubscribe from quotes for a symbol"""
        if symbol in self._quote_callbacks:
            del self._quote_callbacks[symbol]


class TradovateService:
    """High-level service for Tradovate integration"""
    
    def __init__(self):
        self.client = TradovateClient()
        self._symbol_to_contract: Dict[str, int] = {}
    
    @property
    def is_configured(self) -> bool:
        return self.client.is_configured
    
    async def initialize(self) -> bool:
        """Initialize connection and get contract IDs"""
        if not self.client.is_configured:
            logger.warning("[TradovateService] Not configured, using simulation mode")
            return False
        
        authenticated = await self.client.authenticate()
        if not authenticated:
            return False
        
        # Get contract IDs for supported symbols
        symbols = ["CL", "BZ", "NG"]  # WTI, Brent, Natural Gas
        
        for symbol in symbols:
            contracts = await self.client.get_contracts(symbol)
            if contracts:
                # Get front month contract
                front_month = contracts[0]
                self._symbol_to_contract[symbol] = front_month.get("id")
                logger.info(f"[TradovateService] {symbol} contract ID: {front_month.get('id')}")
        
        return True
    
    async def place_trade(
        self,
        symbol: str,
        direction: str,
        quantity: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Optional[Dict]:
        """Place a trade with optional bracket orders"""
        contract_id = self._symbol_to_contract.get(symbol)
        if not contract_id:
            return {"error": f"No contract found for {symbol}"}
        
        action = OrderAction.BUY if direction.lower() == "long" else OrderAction.SELL
        
        if stop_loss and take_profit:
            result = await self.client.place_bracket_order(
                contract_id=contract_id,
                action=action,
                qty=quantity,
                profit_target=take_profit,
                stop_loss=stop_loss,
            )
        else:
            order = await self.client.place_order(
                contract_id=contract_id,
                action=action,
                qty=quantity,
            )
            if order:
                result = {
                    "order_id": order.order_id,
                    "status": order.status,
                    "filled_qty": order.filled_qty,
                    "avg_price": order.avg_fill_price,
                }
            else:
                result = {"error": "Order placement failed"}
        
        return result
    
    async def get_portfolio(self) -> Dict:
        """Get current portfolio summary"""
        positions = await self.client.get_positions()
        account = await self.client.get_account_info()
        
        return {
            "positions": positions,
            "account": account,
            "is_live": not self.client.credentials.is_demo if self.client.credentials else False,
        }
    
    def get_status(self) -> Dict:
        """Get connection status"""
        return {
            "is_configured": self.is_configured,
            "is_demo": self.client.credentials.is_demo if self.client.credentials else True,
            "connected": self.client._access_token is not None,
        }


# Global instance
tradovate_service = TradovateService()
