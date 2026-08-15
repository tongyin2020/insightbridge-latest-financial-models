from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class BreakoutRules:
    min_confidence: float = 0.80
    cooling_off_minutes: float = 15.0
    ofi_imbalance_ratio: float = 2.0
    pulse_ttl_minutes: float = 45.0


class MicrostructureBreakoutFilter:
    """虚假突破过滤器：ARMED → 冷却期 → OFI 验证 → IN_TRADE。"""

    def __init__(self, asset_class: str, event_type: str) -> None:
        self.asset_class = asset_class.upper()
        self.event_type = event_type.upper()
        self.system_state = "MONITORING"  # MONITORING -> ARMED -> IN_TRADE
        self.armed_timestamp: datetime | None = None
        self.rules = self._load_dynamic_rules()

    def _load_dynamic_rules(self) -> BreakoutRules:
        if self.event_type == "INTERVENTION" and self.asset_class == "FX":
            return BreakoutRules(min_confidence=0.80, cooling_off_minutes=5, ofi_imbalance_ratio=2.2, pulse_ttl_minutes=30)
        if self.event_type == "GEOPOLITICS" and self.asset_class == "OIL":
            return BreakoutRules(min_confidence=0.82, cooling_off_minutes=25, ofi_imbalance_ratio=1.7, pulse_ttl_minutes=60)
        if self.asset_class == "CRYPTO":
            return BreakoutRules(min_confidence=0.80, cooling_off_minutes=10, ofi_imbalance_ratio=2.0, pulse_ttl_minutes=30)
        if self.asset_class == "BOND":
            return BreakoutRules(min_confidence=0.80, cooling_off_minutes=20, ofi_imbalance_ratio=1.8, pulse_ttl_minutes=50)
        if self.asset_class == "INDEX":
            return BreakoutRules(min_confidence=0.80, cooling_off_minutes=8, ofi_imbalance_ratio=2.1, pulse_ttl_minutes=35)
        return BreakoutRules()

    def arm(self, confidence: float) -> bool:
        if confidence >= self.rules.min_confidence and self.system_state == "MONITORING":
            self.system_state = "ARMED"
            self.armed_timestamp = datetime.now(timezone.utc)
            return True
        return False

    def validate_breakout(self, current_price: float, l2_order_book: dict[str, Any]) -> bool:
        if self.system_state != "ARMED" or self.armed_timestamp is None:
            return False

        elapsed = (datetime.now(timezone.utc) - self.armed_timestamp).total_seconds()
        if elapsed < self.rules.cooling_off_minutes * 60:
            return False

        bids = sum(l2_order_book.get("bid_sizes_top_3", [0.0]))
        asks = sum(l2_order_book.get("ask_sizes_top_3", [0.0]))
        if asks == 0:
            ofi_ratio = bids
        else:
            ofi_ratio = bids / asks

        if ofi_ratio >= self.rules.ofi_imbalance_ratio:
            self.system_state = "IN_TRADE"
            return True
        return False
