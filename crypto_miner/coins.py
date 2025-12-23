from __future__ import annotations

from typing import Any, Dict, List, Tuple


# Coin metadata + tuning knobs.
# Numbers are gameplay-oriented (not real-world accurate).
COINS: Dict[str, Dict[str, Any]] = {
    "SHIB": {
        "name": "Shiba Inu",
        "symbol": "$SHIB",
        "base_price": 0.00002,
        "base_difficulty": 0.35,
        "network_target": 120_000.0,
        "recommended_hashrate": 250.0,
        "reward_tiers": [
            (0.50, 5_000_000.0),
            (1.25, 2_500_000.0),
            (3.00, 1_000_000.0),
            (999999.0, 500_000.0),
        ],
    },
    "DOGE": {
        "name": "Dogecoin",
        "symbol": "$DOGE",
        "base_price": 0.12,
        "base_difficulty": 1.25,
        "network_target": 650_000.0,
        "recommended_hashrate": 2_500.0,
        "reward_tiers": [
            (1.25, 5.0),
            (3.00, 2.0),
            (6.00, 1.0),
            (999999.0, 0.5),
        ],
    },
    "XMR": {
        "name": "Monero",
        "symbol": "$XMR",
        "base_price": 180.0,
        "base_difficulty": 2.25,
        "network_target": 1_600_000.0,
        "recommended_hashrate": 8_000.0,
        "reward_tiers": [
            (2.00, 0.02),
            (4.00, 0.01),
            (8.00, 0.005),
            (999999.0, 0.002),
        ],
    },
    "ETH": {
        "name": "Ethereum",
        "symbol": "$ETH",
        "base_price": 3200.0,
        "base_difficulty": 3.25,
        "network_target": 2_500_000.0,
        "recommended_hashrate": 15_000.0,
        "reward_tiers": [
            (3.00, 0.01),
            (6.00, 0.005),
            (12.00, 0.002),
            (999999.0, 0.001),
        ],
    },
    "BTC": {
        "name": "Bitcoin",
        "symbol": "$BTC",
        "base_price": 60000.0,
        "base_difficulty": 5.0,
        "network_target": 4_000_000.0,
        "recommended_hashrate": 40_000.0,
        "reward_tiers": [
            (5.00, 0.0010),
            (10.0, 0.0005),
            (20.0, 0.0002),
            (999999.0, 0.0001),
        ],
    },
}


def normalize_coin(coin: str | None) -> str:
    return (coin or "").upper().strip()


def is_valid_coin(coin: str | None) -> bool:
    return normalize_coin(coin) in COINS


def reward_for_coin(coin: str, difficulty: float) -> float:
    coin = normalize_coin(coin)
    tiers: List[Tuple[float, float]] = COINS[coin]["reward_tiers"]
    for max_diff, reward in tiers:
        if difficulty <= float(max_diff):
            return float(reward)
    return float(tiers[-1][1])
