from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np


class KineticInFlightBacktester:
    """动能衰退退出器：用二次多项式拟合实时价格，检测速度/加速度。"""

    def __init__(self, entry_price: float, max_duration_mins: float) -> None:
        self.entry_price = entry_price
        self.max_duration_mins = max_duration_mins
        self.trade_start_time = datetime.now(timezone.utc)
        self.price_series: list[float] = []
        self.time_deltas: list[float] = []

    def update_telemetry(self, current_price: float) -> None:
        self.price_series.append(current_price)
        elapsed = (datetime.now(timezone.utc) - self.trade_start_time).total_seconds() / 60.0
        self.time_deltas.append(elapsed)

    def evaluate_exit_criteria(self) -> str:
        if not self.time_deltas:
            return "HOLD"

        elapsed = self.time_deltas[-1]
        if elapsed >= self.max_duration_mins:
            return "EXIT_TTL"

        if len(self.price_series) < 7:
            return "HOLD"

        x = np.array(self.time_deltas[-7:])
        y = np.array(self.price_series[-7:])

        try:
            coeffs = np.polyfit(x, y, 2)
            acceleration = 2 * coeffs[0]
            velocity = 2 * coeffs[0] * x[-1] + coeffs[1]
            current_return = (y[-1] - self.entry_price) / self.entry_price

            # Apex: price in profit, momentum still positive but decelerating
            if current_return >= 0.004 and acceleration < -0.01 and velocity < 0.02:
                return "EXIT_MOMENTUM"
        except Exception:
            pass

        return "HOLD"
