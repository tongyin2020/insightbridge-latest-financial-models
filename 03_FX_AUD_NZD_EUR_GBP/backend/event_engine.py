"""
Economic event engine.
Manages the state machine for pre-event cooldowns, post-event confirmation,
and direction bias updates.
"""
from __future__ import annotations

import asyncio
import time
import numpy as np
from datetime import datetime, timezone
from typing import Optional
from database import insert_log, get_setting


class EventEngine:
    """
    State machine for economic event handling.

    States:
        NORMAL     -> No event in progress
        PRE_EVENT  -> Event approaching, preparing cooldown
        COOLDOWN   -> Active cooldown, no trading
        CONFIRMING -> 30-second post-release confirmation window
        POST_EVENT -> Direction confirmed, resuming with new bias
    """

    VALID_STATES = ("NORMAL", "PRE_EVENT", "COOLDOWN", "CONFIRMING", "POST_EVENT")

    COOLDOWN_SECONDS = {
        "A": 30,
        "B": 20,
        "C": 0,
    }

    CONFIRMATION_WINDOW_SECONDS = 30

    def __init__(self):
        self._state: str = "NORMAL"
        self._event_level: Optional[str] = None
        self._cooldown_end: float = 0.0
        self._confirmation_end: float = 0.0
        self._prices_before: dict[str, list[float]] = {}
        self._prices_after: dict[str, list[float]] = {}
        self._confirmed_direction: dict[str, str] = {}
        self._current_event_title: str = ""
        self._transition_task: Optional[asyncio.Task] = None

    # ─── State queries ────────────────────────────────────────────────────

    def get_event_state(self) -> dict:
        """Return current state and timing information."""
        now = time.time()
        remaining = 0.0

        if self._state == "COOLDOWN" and self._cooldown_end > now:
            remaining = self._cooldown_end - now
        elif self._state == "CONFIRMING" and self._confirmation_end > now:
            remaining = self._confirmation_end - now
        elif self._state in ("COOLDOWN", "CONFIRMING"):
            # Timer expired but state hasn't transitioned yet
            remaining = 0.0

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

    # ─── State transitions ────────────────────────────────────────────────

    async def start_event_cooldown(
        self,
        event_level: str,
        title: str = "Manual trigger",
        pre_event_prices: Optional[dict[str, list[float]]] = None,
    ) -> dict:
        """
        Trigger event cooldown.

        Args:
            event_level: 'A', 'B', or 'C'
            title: Event description
            pre_event_prices: Dict mapping pair to list of recent closes before the event
        """
        if event_level not in self.COOLDOWN_SECONDS:
            return {"error": f"Invalid event level: {event_level}"}

        cooldown_secs = self.COOLDOWN_SECONDS[event_level]

        if cooldown_secs == 0:
            await insert_log("INFO", "event_engine", f"Level C event '{title}' - no cooldown required")
            return self.get_event_state()

        # Store pre-event prices
        if pre_event_prices:
            self._prices_before = pre_event_prices
        self._prices_after = {}
        self._confirmed_direction = {}

        self._event_level = event_level
        self._current_event_title = title
        self._state = "PRE_EVENT"

        await insert_log(
            "INFO", "event_engine",
            f"Event '{title}' (Level {event_level}) - entering cooldown for {cooldown_secs}s",
        )

        # Transition to COOLDOWN
        self._state = "COOLDOWN"
        self._cooldown_end = time.time() + cooldown_secs

        # Schedule automatic transition to CONFIRMING
        if self._transition_task and not self._transition_task.done():
            self._transition_task.cancel()

        self._transition_task = asyncio.create_task(
            self._auto_transition_to_confirming(cooldown_secs)
        )

        return self.get_event_state()

    async def _auto_transition_to_confirming(self, cooldown_secs: float) -> None:
        """Automatically transition from COOLDOWN to CONFIRMING after the cooldown expires."""
        try:
            await asyncio.sleep(cooldown_secs)
            if self._state == "COOLDOWN":
                self._state = "CONFIRMING"
                self._confirmation_end = time.time() + self.CONFIRMATION_WINDOW_SECONDS
                await insert_log(
                    "INFO", "event_engine",
                    f"Cooldown expired for '{self._current_event_title}' - entering confirmation window ({self.CONFIRMATION_WINDOW_SECONDS}s)",
                )

                # Schedule automatic transition to POST_EVENT if no manual confirm
                self._transition_task = asyncio.create_task(
                    self._auto_transition_to_post_event(self.CONFIRMATION_WINDOW_SECONDS)
                )
        except asyncio.CancelledError:
            pass

    async def _auto_transition_to_post_event(self, confirmation_secs: float) -> None:
        """Automatically transition from CONFIRMING to POST_EVENT after the window expires."""
        try:
            await asyncio.sleep(confirmation_secs)
            if self._state == "CONFIRMING":
                self._state = "POST_EVENT"
                await insert_log(
                    "INFO", "event_engine",
                    f"Confirmation window expired for '{self._current_event_title}' - auto-transitioning to POST_EVENT",
                )
                # After a brief period, return to NORMAL
                await asyncio.sleep(5)
                if self._state == "POST_EVENT":
                    self._state = "NORMAL"
                    self._event_level = None
                    self._current_event_title = ""
                    await insert_log("INFO", "event_engine", "Returned to NORMAL state")
        except asyncio.CancelledError:
            pass

    async def confirm_direction(
        self,
        pair: str,
        prices_before: list[float],
        prices_after: list[float],
    ) -> dict:
        """
        Manually confirm direction after the 30-second window.

        Checks:
        1. Price net change direction
        2. Spread recovery (prices_after variance decreasing = stability)
        3. Structure confirmation (new trend alignment with SMAs)
        """
        if not prices_before or not prices_after:
            return {
                "pair": pair,
                "direction": "NEUTRAL",
                "confidence": 0,
                "reason": "Insufficient price data for confirmation",
            }

        before_arr = np.array(prices_before, dtype=np.float64)
        after_arr = np.array(prices_after, dtype=np.float64)

        # 1. Net price change
        avg_before = np.mean(before_arr[-5:]) if len(before_arr) >= 5 else np.mean(before_arr)
        avg_after = np.mean(after_arr[-5:]) if len(after_arr) >= 5 else np.mean(after_arr)
        net_change = avg_after - avg_before
        net_change_pips = net_change * 10000

        # 2. Spread recovery (lower variance = recovered)
        if len(after_arr) >= 3:
            first_half_var = np.var(after_arr[:len(after_arr)//2])
            second_half_var = np.var(after_arr[len(after_arr)//2:])
            spread_recovered = second_half_var <= first_half_var * 1.5
        else:
            spread_recovered = True

        # 3. Structure confirmation
        if len(after_arr) >= 3:
            # Check if last 3 prices are trending in the same direction as net change
            diffs = np.diff(after_arr[-4:]) if len(after_arr) >= 4 else np.diff(after_arr)
            if net_change > 0:
                structure_ok = np.sum(diffs > 0) >= len(diffs) * 0.5
            else:
                structure_ok = np.sum(diffs < 0) >= len(diffs) * 0.5
        else:
            structure_ok = False

        # Determine direction and confidence
        direction = "NEUTRAL"
        confidence = 0.0

        if abs(net_change_pips) >= 3:  # Minimum 3 pip move to be meaningful
            direction = "BUY" if net_change > 0 else "SELL"
            base = min(abs(net_change_pips) * 3, 50)  # Scale with pip move
            if spread_recovered:
                base += 20
            if structure_ok:
                base += 20
            confidence = min(base, 95)

        reason = (
            f"Net change: {net_change_pips:+.1f} pips, "
            f"Spread recovered: {spread_recovered}, "
            f"Structure confirmed: {structure_ok}"
        )

        self._confirmed_direction[pair] = direction
        self._prices_after[pair] = prices_after

        # Transition to POST_EVENT then NORMAL
        if self._state == "CONFIRMING":
            self._state = "POST_EVENT"
            await insert_log(
                "INFO", "event_engine",
                f"Direction confirmed for {pair}: {direction} (confidence={confidence:.1f}%) - {reason}",
            )
            # Cancel any pending auto-transition
            if self._transition_task and not self._transition_task.done():
                self._transition_task.cancel()
            # Schedule return to NORMAL
            self._transition_task = asyncio.create_task(self._return_to_normal(5))

        return {
            "pair": pair,
            "direction": direction,
            "confidence": round(confidence, 1),
            "reason": reason,
            "net_change_pips": round(net_change_pips, 1),
            "spread_recovered": spread_recovered,
            "structure_confirmed": structure_ok,
        }

    async def _return_to_normal(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if self._state == "POST_EVENT":
                self._state = "NORMAL"
                self._event_level = None
                self._current_event_title = ""
                await insert_log("INFO", "event_engine", "Returned to NORMAL state")
        except asyncio.CancelledError:
            pass

    async def reset(self) -> None:
        """Force reset to NORMAL state."""
        if self._transition_task and not self._transition_task.done():
            self._transition_task.cancel()
        self._state = "NORMAL"
        self._event_level = None
        self._current_event_title = ""
        self._cooldown_end = 0.0
        self._confirmation_end = 0.0
        self._confirmed_direction = {}
        await insert_log("INFO", "event_engine", "Event engine force-reset to NORMAL")
