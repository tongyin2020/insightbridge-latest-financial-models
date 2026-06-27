from __future__ import annotations

from .schema import DecisionAction, EventGrade


def risk_fraction(confidence: float, grade: EventGrade, max_account_risk: float = 0.02) -> tuple[DecisionAction, float]:
    """Convert confidence to action and risk budget.

    This is risk fraction of account equity, not portfolio notional. Heavy position
    still requires stop distance and liquidity checks in the execution bot.
    """
    if confidence < 0.70:
        return DecisionAction.WATCH, 0.0
    if confidence < 0.80:
        return DecisionAction.ENTER_SMALL, max_account_risk * 0.25
    if confidence < 0.88:
        return DecisionAction.ENTER_NORMAL, max_account_risk * 0.55
    if grade in {EventGrade.HIGH_CONVICTION, EventGrade.EXTREME}:
        return DecisionAction.ENTER_HEAVY, max_account_risk * 0.85
    return DecisionAction.ENTER_NORMAL, max_account_risk * 0.55
