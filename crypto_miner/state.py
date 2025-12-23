from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from miners import AVAILABLE_MINERS

from .coins import COINS, normalize_coin, reward_for_coin


@dataclass
class GameState:
    """Core game state and mining/economy mechanics."""

    # Back-compat single-coin view fields (reflect active coin)
    money: float = 1000.0
    crypto: float = 0.0
    price: float = 50.0
    difficulty: float = 1.0

    miners_owned: Dict[str, int] = field(default_factory=dict)
    hash_rate_cache: float = 0.0

    # Telemetry
    terminal_logs: List[str] = field(default_factory=list)
    price_history: List[Tuple[float, float]] = field(default_factory=list)  # legacy active-coin view
    blocks_found: int = 0
    shares_accepted: int = 0
    shares_rejected: int = 0
    started_at: float = field(default_factory=lambda: time.time())

    PRICE_HISTORY_SAMPLE_SEC: int = 60
    PRICE_HISTORY_MAX_POINTS: int = 720
    HASHRATE_JITTER_PCT: float = 0.01

    # Mining config
    block_find_multiplier: float = 1.0
    reject_rate: float = 0.02

    # Multi-coin mining
    COINS: ClassVar[Dict[str, Dict[str, Any]]] = COINS
    active_coin: str = "SHIB"
    wallets: Dict[str, float] = field(default_factory=dict)
    coin_prices: Dict[str, float] = field(default_factory=dict)
    coin_difficulties: Dict[str, float] = field(default_factory=dict)
    coin_network_targets: Dict[str, float] = field(default_factory=dict)
    price_history_by_coin: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)

    SAVE_FILE: ClassVar[str] = "savegame.json"

    def __post_init__(self) -> None:
        if self.active_coin not in self.COINS:
            self.active_coin = "SHIB"

        for code, meta in self.COINS.items():
            self.wallets.setdefault(code, 0.0)
            self.coin_prices.setdefault(code, float(meta["base_price"]))
            self.coin_difficulties.setdefault(code, float(meta["base_difficulty"]))
            self.coin_network_targets.setdefault(code, float(meta["network_target"]))
            self.price_history_by_coin.setdefault(code, [])

        # Back-compat migration: if old saves only had crypto/price/difficulty.
        if self.wallets.get(self.active_coin, 0.0) == 0.0 and self.crypto:
            self.wallets[self.active_coin] = float(self.crypto)

        if self.active_coin not in self.coin_prices and self.price:
            self.coin_prices[self.active_coin] = float(self.price)
        if self.active_coin not in self.coin_difficulties and self.difficulty:
            self.coin_difficulties[self.active_coin] = float(self.difficulty)

        if self.price_history and not self.price_history_by_coin.get(self.active_coin):
            self.price_history_by_coin[self.active_coin] = list(self.price_history)

        self._sync_active_view_from_coin_state()

    def _sync_active_view_from_coin_state(self) -> None:
        self.crypto = float(self.wallets.get(self.active_coin, 0.0))
        self.price = float(self.coin_prices.get(self.active_coin, self.price))
        self.difficulty = float(self.coin_difficulties.get(self.active_coin, self.difficulty))

    def _log(self, line: str) -> None:
        self.terminal_logs.append(line)
        if len(self.terminal_logs) > 400:
            self.terminal_logs = self.terminal_logs[-400:]

    def recalc_hashrate(self) -> float:
        total = 0.0
        for spec in AVAILABLE_MINERS:
            count = self.miners_owned.get(spec.key, 0)
            total += count * spec.hashrate
        self.hash_rate_cache = total
        return total

    def set_active_coin(self, coin: str | None) -> bool:
        coin = normalize_coin(coin)
        if coin not in self.COINS:
            return False
        self.active_coin = coin
        self._sync_active_view_from_coin_state()
        self._log(f"[config] active coin set to {coin} ({self.COINS[coin]['symbol']})")
        return True

    def set_mining_config(
        self,
        *,
        block_find_multiplier: Optional[float] = None,
        reject_rate: Optional[float] = None,
        network_target: Optional[float] = None,
    ) -> None:
        if block_find_multiplier is not None:
            self.block_find_multiplier = float(max(0.05, min(50.0, block_find_multiplier)))
        if reject_rate is not None:
            self.reject_rate = float(max(0.0, min(0.5, reject_rate)))
        if network_target is not None:
            nt = float(max(10_000.0, min(50_000_000.0, network_target)))
            self.coin_network_targets[self.active_coin] = nt

    def solve_block(self, hashrate: Optional[float] = None) -> float:
        if hashrate is None:
            hashrate = self.recalc_hashrate()
        if hashrate <= 0:
            return 0.0

        target = float(self.coin_network_targets.get(self.active_coin, self.COINS[self.active_coin]["network_target"]))
        effective_hashrate = hashrate * max(0.0001, self.block_find_multiplier)
        prob = min(1.0, effective_hashrate / (max(0.0001, self.difficulty) * max(1.0, target)))

        if random.random() >= prob:
            return 0.0

        self.blocks_found += 1
        return reward_for_coin(self.active_coin, self.difficulty)

    def mine(self) -> float:
        base_hashrate = self.recalc_hashrate()
        jitter = 1.0 + random.uniform(-self.HASHRATE_JITTER_PCT, self.HASHRATE_JITTER_PCT)
        hashrate = max(0.0, base_hashrate * jitter)
        up = int(time.time() - self.started_at)

        if base_hashrate <= 0:
            self._log(f"[{up:>6}s] no active miners. buy rigs in Shop")
            return 0.0

        rejected = random.random() < self.reject_rate
        if rejected:
            self.shares_rejected += 1
        else:
            self.shares_accepted += 1

        reward = 0.0
        if not rejected:
            reward = self.solve_block(hashrate=hashrate)

        if reward > 0:
            self.wallets[self.active_coin] = float(self.wallets.get(self.active_coin, 0.0)) + float(reward)
            self.crypto = float(self.wallets[self.active_coin])
            self._log(
                f"[{up:>6}s] accepted (1/1) {self.active_coin} diff {self.difficulty:.3f} +{reward:.6f} (blocks={self.blocks_found})"
            )
        else:
            status = "rejected" if rejected else "accepted"
            self._log(
                f"[{up:>6}s] {status:<8} {self.active_coin} speed 10s {hashrate:,.2f}H/s  diff {self.difficulty:.3f}  a/r {self.shares_accepted}/{self.shares_rejected}  boost x{self.block_find_multiplier:g}"
            )

        return reward

    def get_terminal_logs(self, last: int = 200) -> List[str]:
        if last <= 0:
            return []
        return self.terminal_logs[-last:]

    def get_price_history(self, minutes: int = 60, *, coin: str | None = None) -> List[Dict[str, float]]:
        coin_code = normalize_coin(coin) if coin else self.active_coin
        if coin_code not in self.COINS:
            coin_code = self.active_coin
        cutoff = time.time() - max(1, minutes) * 60
        hist = self.price_history_by_coin.get(coin_code, [])
        return [{"t": float(ts), "price": float(p)} for ts, p in hist if ts >= cutoff]

    def mining_tick(self) -> float:
        base_hashrate = self.recalc_hashrate()
        reward = self.mine()

        # price drift (active coin)
        drift = random.uniform(-0.02, 0.02) * self.price
        self.price = max(0.00000001, self.price + drift)
        self.coin_prices[self.active_coin] = float(self.price)

        # difficulty adapts for active coin
        base_diff = float(self.COINS[self.active_coin]["base_difficulty"])
        self.difficulty = max(0.1, base_diff + base_hashrate / 1000.0)
        self.coin_difficulties[self.active_coin] = float(self.difficulty)

        # sampled history per coin
        now = time.time()
        hist = self.price_history_by_coin.setdefault(self.active_coin, [])
        if not hist:
            hist.append((now, self.price))
        else:
            last_ts = float(hist[-1][0])
            if now - last_ts >= self.PRICE_HISTORY_SAMPLE_SEC:
                hist.append((now, self.price))

        if len(hist) > self.PRICE_HISTORY_MAX_POINTS:
            self.price_history_by_coin[self.active_coin] = hist[-self.PRICE_HISTORY_MAX_POINTS :]

        # keep legacy view in sync
        self.price_history = self.price_history_by_coin.get(self.active_coin, [])
        return reward

    def buy_miner(self, miner_key: str) -> bool:
        spec = next((m for m in AVAILABLE_MINERS if m.key == miner_key), None)
        if spec is None:
            return False
        if self.money >= spec.cost:
            self.money -= spec.cost
            self.miners_owned[miner_key] = self.miners_owned.get(miner_key, 0) + 1
            self.recalc_hashrate()
            return True
        return False

    def buy_upgrade(self, upgrade_id: str) -> bool:
        if upgrade_id == "efficiency_boost" and self.money >= 500:
            self.money -= 500
            self.difficulty = max(0.1, self.difficulty - 0.1)
            self.coin_difficulties[self.active_coin] = float(self.difficulty)
            return True
        return False

    def sell_crypto(self, amount: float) -> bool:
        bal = float(self.wallets.get(self.active_coin, 0.0))
        if amount <= 0 or amount > bal:
            return False
        self.wallets[self.active_coin] = bal - float(amount)
        self.crypto = float(self.wallets[self.active_coin])
        self.money += float(amount) * float(self.price)
        return True

    def save(self) -> None:
        data = {
            "money": self.money,
            "crypto": self.crypto,
            "price": self.price,
            "difficulty": self.difficulty,
            "miners_owned": self.miners_owned,
            "terminal_logs": self.terminal_logs,
            "price_history": self.price_history[-self.PRICE_HISTORY_MAX_POINTS :],
            "blocks_found": self.blocks_found,
            "shares_accepted": self.shares_accepted,
            "shares_rejected": self.shares_rejected,
            "started_at": self.started_at,
            "block_find_multiplier": self.block_find_multiplier,
            "reject_rate": self.reject_rate,
            "active_coin": self.active_coin,
            "wallets": self.wallets,
            "coin_prices": self.coin_prices,
            "coin_difficulties": self.coin_difficulties,
            "coin_network_targets": self.coin_network_targets,
            "price_history_by_coin": {
                k: v[-self.PRICE_HISTORY_MAX_POINTS :] for k, v in self.price_history_by_coin.items()
            },
        }
        with open(self.SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls) -> "GameState":
        try:
            with open(cls.SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            gs = cls(
                money=data.get("money", 1000.0),
                crypto=data.get("crypto", 0.0),
                price=data.get("price", 50.0),
                difficulty=data.get("difficulty", 1.0),
                miners_owned=data.get("miners_owned", {}),
                terminal_logs=data.get("terminal_logs", []),
                price_history=data.get("price_history", []),
                blocks_found=data.get("blocks_found", 0),
                shares_accepted=data.get("shares_accepted", 0),
                shares_rejected=data.get("shares_rejected", 0),
                started_at=data.get("started_at", time.time()),
                block_find_multiplier=data.get("block_find_multiplier", 1.0),
                reject_rate=data.get("reject_rate", 0.02),
                active_coin=data.get("active_coin", "SHIB"),
                wallets=data.get("wallets", {}),
                coin_prices=data.get("coin_prices", {}),
                coin_difficulties=data.get("coin_difficulties", {}),
                coin_network_targets=data.get("coin_network_targets", {}),
                price_history_by_coin=data.get("price_history_by_coin", {}),
            )

            # prune oversized histories
            for coin, hist in list(gs.price_history_by_coin.items()):
                if len(hist) > gs.PRICE_HISTORY_MAX_POINTS:
                    gs.price_history_by_coin[coin] = hist[-gs.PRICE_HISTORY_MAX_POINTS :]
            if len(gs.price_history) > gs.PRICE_HISTORY_MAX_POINTS:
                gs.price_history = gs.price_history[-gs.PRICE_HISTORY_MAX_POINTS :]

            gs._sync_active_view_from_coin_state()
            gs.recalc_hashrate()
            return gs
        except FileNotFoundError:
            return cls()

    def reset(self) -> None:
        self.money = 10000.0
        self.active_coin = "SHIB"
        for coin, meta in self.COINS.items():
            self.wallets[coin] = 0.0
            self.coin_prices[coin] = float(meta["base_price"])
            self.coin_difficulties[coin] = float(meta["base_difficulty"])
            self.coin_network_targets[coin] = float(meta["network_target"])
            self.price_history_by_coin[coin] = []

        self._sync_active_view_from_coin_state()
        self.miners_owned = {}
        self.hash_rate_cache = 0.0

        self.terminal_logs = []
        self.price_history = []
        self.blocks_found = 0
        self.shares_accepted = 0
        self.shares_rejected = 0
        self.started_at = time.time()

        self.block_find_multiplier = 1.0
        self.reject_rate = 0.02
