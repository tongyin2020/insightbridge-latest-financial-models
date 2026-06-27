"""
News classifier for IB TWS news feed.

Classifies incoming headlines and article bodies into impact levels
(A/B/C) and determines which currency pairs are affected.
"""

import re
from typing import Tuple

# ---------------------------------------------------------------------------
# Keyword dictionaries
# ---------------------------------------------------------------------------

# A-level: high-impact central bank decisions, major macro releases
A_LEVEL_KEYWORDS: list[str] = [
    "RBA",
    "RBNZ",
    "Fed ",
    "Federal Reserve",
    "FOMC",
    "CPI",
    "NFP",
    "Non-Farm",
    "Non Farm",
    "Nonfarm",
    "employment change",
    "unemployment rate",
    "GDP",
    "interest rate decision",
    "rate decision",
    "rate cut",
    "rate hike",
    "rate hold",
    "monetary policy",
    "quantitative easing",
    "QE",
    "quantitative tightening",
    "QT",
    "inflation",
    "consumer price",
    "core inflation",
    "wage price index",
    "labor market",
    "labour market",
    "ECB",
    "Bank of England",
    "BOJ",
    "PBOC",
]

# B-level: secondary releases and commodity proxies
B_LEVEL_KEYWORDS: list[str] = [
    "speech",
    "remarks",
    "testimony",
    "PMI",
    "purchasing managers",
    "retail sales",
    "trade balance",
    "current account",
    "iron ore",
    "dairy",
    "dairy auction",
    "GDT auction",
    "building permits",
    "housing",
    "home sales",
    "consumer confidence",
    "business confidence",
    "manufacturing",
    "services",
    "industrial production",
    "capacity utilization",
    "durable goods",
    "wholesale",
    "import prices",
    "export prices",
    "PPI",
    "producer price",
    "ISM",
    "ADP",
    "jobless claims",
    "treasury",
    "bond auction",
    "copper",
    "gold",
    "commodity",
    "Lowe",       # RBA governor (example)
    "Orr",        # RBNZ governor (example)
    "Powell",     # Fed chair
    "Bullock",    # RBA governor
]

# ---------------------------------------------------------------------------
# Pair-affected detection patterns
# ---------------------------------------------------------------------------

AUD_PATTERNS: list[str] = [
    "Australia",
    "Australian",
    "AUD",
    "RBA",
    "Aussie",
    "iron ore",
    "ASX",
    "Bullock",
    "Sydney",
    "Melbourne",
    "Commonwealth Bank",
    "Westpac",
    "ANZ",
    "NAB",
]

NZD_PATTERNS: list[str] = [
    "New Zealand",
    "NZD",
    "RBNZ",
    "Kiwi",
    "dairy",
    "GDT auction",
    "Fonterra",
    "Auckland",
    "Wellington",
    "Orr",
]

USD_PATTERNS: list[str] = [
    "United States",
    "U.S.",
    "US ",
    "USD",
    "Fed ",
    "Federal Reserve",
    "FOMC",
    "Treasury",
    "NFP",
    "Non-Farm",
    "Nonfarm",
    "CPI",
    "GDP",
    "Powell",
    "Wall Street",
    "Washington",
    "dollar",
    "Dollar",
]

# ---------------------------------------------------------------------------
# Category labels
# ---------------------------------------------------------------------------

CATEGORY_MAP: dict[str, list[str]] = {
    "central_bank": [
        "RBA", "RBNZ", "Fed ", "Federal Reserve", "FOMC", "ECB", "BOJ",
        "PBOC", "Bank of England", "interest rate", "rate decision",
        "rate cut", "rate hike", "rate hold", "monetary policy",
        "quantitative easing", "QE", "quantitative tightening", "QT",
        "speech", "remarks", "testimony", "Bullock", "Orr", "Powell", "Lowe",
    ],
    "employment": [
        "NFP", "Non-Farm", "Non Farm", "Nonfarm", "employment",
        "unemployment", "jobless claims", "ADP", "labor market",
        "labour market", "wage",
    ],
    "inflation": [
        "CPI", "consumer price", "inflation", "core inflation",
        "PPI", "producer price", "import prices", "export prices",
        "wage price index",
    ],
    "growth": [
        "GDP", "retail sales", "PMI", "purchasing managers",
        "manufacturing", "services", "industrial production",
        "durable goods", "ISM", "consumer confidence",
        "business confidence", "capacity utilization",
    ],
    "trade": [
        "trade balance", "current account", "iron ore", "dairy",
        "GDT auction", "copper", "gold", "commodity", "Fonterra",
    ],
    "housing": [
        "housing", "home sales", "building permits",
    ],
}


def _text_contains(text: str, keywords: list[str]) -> bool:
    """Return True if *text* contains any of the *keywords* (case-insensitive)."""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def _find_matching_keywords(text: str, keywords: list[str]) -> list[str]:
    """Return which keywords from the list appear in *text*."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def classify_event(
    headline: str,
    body: str = "",
) -> Tuple[str, list[str], str]:
    """Classify a news event.

    Args:
        headline: The news headline text.
        body: Optional article body / summary text.

    Returns:
        A tuple of:
            - impact_level: 'A' (high), 'B' (medium), or 'C' (low)
            - pairs_affected: list of pair strings, e.g. ['AUD/USD', 'NZD/USD']
            - category: one of the CATEGORY_MAP keys or 'general'
    """
    combined = f"{headline} {body}"

    # --- Impact level ---
    if _text_contains(combined, A_LEVEL_KEYWORDS):
        impact_level = "A"
    elif _text_contains(combined, B_LEVEL_KEYWORDS):
        impact_level = "B"
    else:
        impact_level = "C"

    # --- Pairs affected ---
    pairs_affected: list[str] = []

    mentions_aud = _text_contains(combined, AUD_PATTERNS)
    mentions_nzd = _text_contains(combined, NZD_PATTERNS)
    mentions_usd = _text_contains(combined, USD_PATTERNS)

    if mentions_aud:
        pairs_affected.append("AUD/USD")
    if mentions_nzd:
        pairs_affected.append("NZD/USD")

    # If only USD is mentioned (no AUD/NZD), it affects both pairs
    if mentions_usd and not mentions_aud and not mentions_nzd:
        pairs_affected = ["AUD/USD", "NZD/USD"]

    # If nothing specific is detected but impact is A or B, assume both pairs
    if not pairs_affected and impact_level in ("A", "B"):
        pairs_affected = ["AUD/USD", "NZD/USD"]

    # --- Category ---
    category = "general"
    for cat_name, cat_keywords in CATEGORY_MAP.items():
        if _text_contains(combined, cat_keywords):
            category = cat_name
            break

    return impact_level, pairs_affected, category


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        ("RBA holds interest rate steady at 4.35%", ""),
        ("RBNZ surprises with 50bp rate cut", ""),
        ("US Non-Farm Payrolls surge to 353K, smashing expectations", ""),
        ("Australia retail sales rise 0.3% in December", ""),
        ("Iron ore prices fall 5% on China demand concerns", ""),
        ("New Zealand GDT dairy auction prices drop 2.1%", ""),
        ("Fed Chair Powell delivers hawkish remarks on inflation", ""),
        ("European stocks rise on tech earnings", ""),
        ("Australia CPI comes in hotter than expected at 4.1%", ""),
        ("Minor earthquake reported in regional area", ""),
    ]

    print(f"{'Headline':<60} {'Impact':>6} {'Pairs':<25} {'Category'}")
    print("-" * 120)
    for headline, body in test_cases:
        level, pairs, cat = classify_event(headline, body)
        print(f"{headline:<60} {level:>6} {str(pairs):<25} {cat}")
