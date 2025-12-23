from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from miners import AVAILABLE_MINERS
from .coins import COINS, normalize_coin, reward_for_coin
from .formatting import format_hashrate


@dataclass
class GameState:
    """Core game state and mining/economy mechanics."""

    # -- Economy & Assets --
    money: float = 1000.0
    crypto: float = 0.0  # Legacy view (active coin)
    wallets: Dict[str, float] = field(default_factory=dict)
    miners_owned: Dict[str, int] = field(default_factory=dict)

    # -- Market State --
    price: float = 50.0  # Legacy view
    difficulty: float = 1.0  # Legacy view
    active_coin: str = "SHIB"
    coin_prices: Dict[str, float] = field(default_factory=dict)
    coin_difficulties: Dict[str, float] = field(default_factory=dict)
    coin_network_targets: Dict[str, float] = field(default_factory=dict)
    coin_competition: Dict[str, float] = field(default_factory=dict)  # Simulated network growth

    # -- Performance & Stats --
    hash_rate_cache: float = 0.0
    blocks_found: int = 0
    shares_accepted: int = 0
    shares_rejected: int = 0
    started_at: float = field(default_factory=lambda: time.time())
    last_mine_ts: float = field(default_factory=lambda: time.time())

    # -- Config & History --
    block_find_multiplier: float = 1.0
    reject_rate: float = 0.02
    terminal_logs: List[str] = field(default_factory=list)
    price_history: List[Tuple[float, float]] = field(default_factory=list)
    price_history_by_coin: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)

    # -- Constants --
    COINS: ClassVar[Dict[str, Dict[str, Any]]] = COINS
    SAVE_FILE: ClassVar[str] = "savegame.json"
    PRICE_HISTORY_SAMPLE_SEC: int = 60
    PRICE_HISTORY_MAX_POINTS: int = 720
    HASHRATE_JITTER_PCT: float = 0.01
    TARGET_BLOCK_TIME: ClassVar[float] = 10.0  # Seconds per block (gameplay speed)

    def __post_init__(self) -> None:
        """Initialize default values and migrate legacy save data."""
        self.active_coin = normalize_coin(self.active_coin)
        if self.active_coin not in self.COINS:
            self.active_coin = "SHIB"

        # Ensure all coins have entries
        for code, meta in self.COINS.items():
            self.wallets.setdefault(code, 0.0)
            self.coin_prices.setdefault(code, float(meta["base_price"]))
            self.coin_difficulties.setdefault(code, float(meta["base_difficulty"]))
            self.coin_network_targets.setdefault(code, float(meta["network_target"]))
            self.coin_competition.setdefault(code, 0.0)
            self.price_history_by_coin.setdefault(code, [])

        # Migration: Legacy single-coin save to multi-coin wallet
        if self.wallets.get(self.active_coin, 0.0) == 0.0 and self.crypto > 0:
            self.wallets[self.active_coin] = float(self.crypto)

        # Migration: Sync legacy price/diff if missing from dicts
        if self.active_coin not in self.coin_prices and self.price:
            self.coin_prices[self.active_coin] = float(self.price)
        if self.active_coin not in self.coin_difficulties and self.difficulty:
            self.coin_difficulties[self.active_coin] = float(self.difficulty)

        # Migration: Sync history
        if self.price_history and not self.price_history_by_coin.get(self.active_coin):
            self.price_history_by_coin[self.active_coin] = list(self.price_history)

        self._sync_active_view()

    def _sync_active_view(self) -> None:
        """Update legacy fields to reflect the currently active coin."""
        self.crypto = float(self.wallets.get(self.active_coin, 0.0))
        self.price = float(self.coin_prices.get(self.active_coin, self.price))
        self.difficulty = float(self.coin_difficulties.get(self.active_coin, self.difficulty))

    def _log(self, line: str) -> None:
        self.terminal_logs.append(line)
        if len(self.terminal_logs) > 400:
            self.terminal_logs = self.terminal_logs[-400:]

    def recalc_hashrate(self) -> float:
        """Calculate total hashrate from owned miners."""
        self.hash_rate_cache = sum(
            self.miners_owned.get(m.key, 0) * m.hashrate for m in AVAILABLE_MINERS
        )
        return self.hash_rate_cache

    def set_active_coin(self, coin: str | None) -> bool:
        coin = normalize_coin(coin)
        if coin not in self.COINS:
            return False
        self.active_coin = coin
        self._sync_active_view()
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

    def _calculate_reward(self, hashrate: float, dt: float) -> float:
        """
        Calculate reward based on hashrate (PPS - Pay Per Share model).
        
        Implements a 'Saturation' model where the network difficulty
        scales linearly with total hashrate (Base + User + Competition).
        This prevents infinite exponential rewards and simulates a real
        blockchain network adjusting to new hashpower.
        """
        if hashrate <= 0:
            return 0.0

        # 1. Determine Base Network Hashrate
        #    Derived from the coin's target hashes per block at difficulty 1.0
        #    and our target block time (10s).
        base_target_hashes = self.coin_network_targets.get(
            self.active_coin, self.COINS[self.active_coin]["network_target"]
        )
        base_network_hashrate = base_target_hashes / self.TARGET_BLOCK_TIME

        # 2. Calculate Total Network Hashrate
        #    Total = Base (Initial) + User (You) + Competition (Simulated Growth)
        competition = self.coin_competition.get(self.active_coin, 0.0)
        total_network_hashrate = base_network_hashrate + hashrate + competition

        # 3. Calculate User's Share of the Network
        #    This is the fraction of blocks the user is expected to find.
        #    As UserHashrate increases, this approaches 1.0 (100%), but never exceeds it.
        network_share = hashrate / max(1.0, total_network_hashrate)

        # 4. Calculate Expected Blocks Found in this tick (dt)
        #    Global Emission = 1 block / TARGET_BLOCK_TIME
        blocks_per_second = 1.0 / self.TARGET_BLOCK_TIME
        expected_blocks = blocks_per_second * network_share * dt * self.block_find_multiplier

        # 5. Update Difficulty for UI
        #    Difficulty is essentially the multiplier of the base network hashrate.
        #    If Total = 2 * Base, Difficulty = 2.0.
        real_difficulty = total_network_hashrate / max(1.0, base_network_hashrate)
        self.difficulty = real_difficulty
        self.coin_difficulties[self.active_coin] = float(self.difficulty)

        # 6. Calculate Reward
        #    Block reward may drop as difficulty increases (halving simulation)
        block_val = reward_for_coin(self.active_coin, self.difficulty)
        reward = expected_blocks * block_val

        # 7. Simulate "Block Found" event for UI stats (Bernoulli trial)
        #    Probability of finding at least one block in this tick.
        #    For high hashrates, this is just 1.0, but we track count.
        if random.random() < (expected_blocks / max(1.0, self.block_find_multiplier)):
             self.blocks_found += 1

        return reward

    def mine(self) -> float:
        """Perform one mining cycle."""
        now = time.time()
        dt = float(max(0.05, min(5.0, now - self.last_mine_ts)))
        self.last_mine_ts = now
        up_time = int(now - self.started_at)

        base_hashrate = self.recalc_hashrate()
        if base_hashrate <= 0:
            if random.random() < 0.05:  # Don't spam logs
                self._log(f"[{up_time:>6}s] no active miners. buy rigs in Shop")
            return 0.0

        # Add jitter to hashrate for realism
        jitter = 1.0 + random.uniform(-self.HASHRATE_JITTER_PCT, self.HASHRATE_JITTER_PCT)
        effective_hashrate = max(0.0, base_hashrate * jitter)

        # Check for rejected shares (simulated hardware errors/network issues)
        is_rejected = random.random() < self.reject_rate
        if is_rejected:
            self.shares_rejected += 1
            self._log(
                f"[{up_time:>6}s] rejected {self.active_coin} "
                f"speed {format_hashrate(effective_hashrate)} "
                f"diff {self.difficulty:.3f} a/r {self.shares_accepted}/{self.shares_rejected}"
            )
            return 0.0

        self.shares_accepted += 1
        reward = self._calculate_reward(effective_hashrate, dt)

        if reward > 0:
            current_bal = float(self.wallets.get(self.active_coin, 0.0))
            self.wallets[self.active_coin] = current_bal + reward
            self.crypto = self.wallets[self.active_coin]

            # Only log significant rewards or periodically to avoid spamming PPS dust
            if random.random() < 0.1:
                self._log(
                    f"[{up_time:>6}s] mining   {self.active_coin} "
                    f"speed {format_hashrate(effective_hashrate)} "
                    f"+{reward:.8f} (pool)"
                )

        return reward

    def _update_market_economics(self, hashrate: float) -> None:
        """Update coin prices and difficulty based on game loop."""
        # Price Drift
        drift = random.uniform(-0.02, 0.02) * self.price
        self.price = max(0.00000001, self.price + drift)
        self.coin_prices[self.active_coin] = float(self.price)

        # Difficulty is now updated in _calculate_reward based on real-time network stats.
        # Here we simulate "Competition Growth" (Difficulty increasing over time).
        
        # If the coin is profitable (price is high), competition enters.
        # Simple logic: Random small growth.
        growth_chance = 0.1
        if random.random() < growth_chance:
            # Growth is proportional to current difficulty to keep it relevant
            growth_amount = self.difficulty * 0.001 * self.COINS[self.active_coin]["network_target"] / self.TARGET_BLOCK_TIME
            self.coin_competition[self.active_coin] = self.coin_competition.get(self.active_coin, 0.0) + growth_amount

    def _record_price_history(self) -> None:
        """Sample current price into history buffers."""
        now = time.time()
        hist = self.price_history_by_coin.setdefault(self.active_coin, [])

        should_record = False
        if not hist:
            should_record = True
        elif now - float(hist[-1][0]) >= self.PRICE_HISTORY_SAMPLE_SEC:
            should_record = True

        if should_record:
            hist.append((now, self.price))
            if len(hist) > self.PRICE_HISTORY_MAX_POINTS:
                self.price_history_by_coin[self.active_coin] = hist[
                    -self.PRICE_HISTORY_MAX_POINTS :
                ]

            # Sync legacy view
            self.price_history = self.price_history_by_coin[self.active_coin]

    def mining_tick(self) -> float:
        """Main game loop tick: mine, update economy, record stats."""
        reward = self.mine()
        self._update_market_economics(self.hash_rate_cache)
        self._record_price_history()
        return reward

    def get_terminal_logs(self, last: int = 200) -> List[str]:
        return self.terminal_logs[-last:] if last > 0 else []

    def get_price_history(
        self, minutes: int = 60, *, coin: str | None = None
    ) -> List[Dict[str, float]]:
        coin_code = normalize_coin(coin) if coin else self.active_coin
        if coin_code not in self.COINS:
            coin_code = self.active_coin

        cutoff = time.time() - max(1, minutes) * 60
        hist = self.price_history_by_coin.get(coin_code, [])

        points = [
            {"t": float(ts), "price": float(p)} for ts, p in hist if float(ts) >= cutoff
        ]

        if not points:
            # Fallback to current state if history is empty/out of range
            now = time.time()
            current_p = float(
                self.coin_prices.get(coin_code, self.COINS[coin_code]["base_price"])
            )
            return [{"t": float(now), "price": current_p}]

        return points

    def buy_miner(self, miner_key: str) -> bool:
        spec = next((m for m in AVAILABLE_MINERS if m.key == miner_key), None)
        if not spec:
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
            # Permanent difficulty reduction for active coin
            # In new model, this could reduce 'competition' or increase 'block_find_multiplier'
            # Let's make it reduce competition slightly
            current_comp = self.coin_competition.get(self.active_coin, 0.0)
            self.coin_competition[self.active_coin] = max(0.0, current_comp * 0.9)
            return True
        return False

    def sell_crypto(self, amount: float) -> bool:
        bal = float(self.wallets.get(self.active_coin, 0.0))
        if amount <= 0 or amount > bal:
            return False

        self.wallets[self.active_coin] = bal - float(amount)
        self.crypto = self.wallets[self.active_coin]
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
            "price_history": self.price_history,
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
            "coin_competition": self.coin_competition,
            "price_history_by_coin": self.price_history_by_coin,
        }
        # Use a temp file or just write directly (simple game)
        with open(self.SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls) -> "GameState":
        try:
            with open(cls.SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Filter out keys that don't belong to the dataclass fields
            # to avoid TypeError on init if save file has stale keys
            valid_keys = cls.__dataclass_fields__.keys()
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}

            gs = cls(**filtered_data)
            gs.__post_init__()  # Re-run post init to ensure migrations/sync
            gs.recalc_hashrate()
            return gs
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()

    def reset(self) -> None:
        self.money = 10000.0
        self.active_coin = "SHIB"
        self.miners_owned.clear()
        self.hash_rate_cache = 0.0
        self.terminal_logs.clear()
        self.price_history.clear()
        self.blocks_found = 0
        self.shares_accepted = 0
        self.shares_rejected = 0
        self.started_at = time.time()
        self.block_find_multiplier = 1.0
        self.reject_rate = 0.02

        # Reset coin states
        for coin, meta in self.COINS.items():
            self.wallets[coin] = 0.0
            self.coin_prices[coin] = float(meta["base_price"])
            self.coin_difficulties[coin] = float(meta["base_difficulty"])
            self.coin_network_targets[coin] = float(meta["network_target"])
            self.coin_competition[coin] = 0.0
            self.price_history_by_coin[coin] = []

        self._sync_active_view()
