from __future__ import annotations

from typing import Any


class PositionRiskBalancer:
    """多模型相关性敞口平衡：主模型 IN_TRADE 时，相关模型仓位上限下降。"""

    def __init__(self, secondary_scale: float = 0.25) -> None:
        self.secondary_scale = secondary_scale

    def scale(self, primary_bot: str, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not actions:
            return actions
        scaled: list[dict[str, Any]] = []
        for a in actions:
            if a.get("bot_id") != primary_bot:
                a = dict(a)
                a["suggested_size"] = a.get("suggested_size", 1.0) * self.secondary_scale
                a["size_multiplier"] = a.get("size_multiplier", 1.0) * self.secondary_scale
                a["risk_scaled"] = True
            scaled.append(a)
        return scaled
