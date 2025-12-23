import json
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from miners import AVAILABLE_MINERS


@dataclass
class GameState:
    """Holds the core game logic independent of the UI.

    This module contains mining tick logic, economy updates, buy/save/load.
    Keep methods small so Flask can call them for presentation.
    """
    money: float = 1000.0
    crypto: float = 0.0
    price: float = 50.0  # USD per coin
    difficulty: float = 1.0
    miners_owned: Dict[str, int] = field(default_factory=dict)
    hash_rate_cache: float = 0.0

    # XMRig-like telemetry / UI support
    terminal_logs: List[str] = field(default_factory=list)
    price_history: List[Tuple[float, float]] = field(default_factory=list)  # (ts, price)
    blocks_found: int = 0
    shares_accepted: int = 0
    shares_rejected: int = 0
    started_at: float = field(default_factory=lambda: time.time())

    # Store chart points at most once per minute to avoid save bloat.
    PRICE_HISTORY_SAMPLE_SEC: int = 60
    PRICE_HISTORY_MAX_POINTS: int = 720  # 12 hours @ 1 point/min

    # Simulated rig hashrate jitter per tick (+/- 1%)
    HASHRATE_JITTER_PCT: float = 0.01

    # Mining configuration (tunable from UI/API)
    network_target: float = 1_000_000.0
    block_find_multiplier: float = 1.0
    reject_rate: float = 0.02

    SAVE_FILE = "savegame.json"

    def _log(self, line: str) -> None:
        self.terminal_logs.append(line)
        # keep logs bounded
        if len(self.terminal_logs) > 400:
            self.terminal_logs = self.terminal_logs[-400:]

    def recalc_hashrate(self) -> float:
        """Recalculate total hashrate from owned miners."""
        total = 0.0
        for spec in AVAILABLE_MINERS:
            count = self.miners_owned.get(spec.key, 0)
            total += count * spec.hashrate
        self.hash_rate_cache = total
        return total

    def _block_reward_for_difficulty(self, difficulty: float) -> float:
        """Reward per block based on difficulty.

        Feel free to tune these tiers for gameplay balance.
        """
        tiers = [
            (0.75, 2.0),
            (1.50, 1.0),
            (3.00, 0.50),
            (6.00, 0.25),
            (999999.0, 0.10),
        ]
        for max_diff, reward in tiers:
            if difficulty <= max_diff:
                return reward
        return 0.10

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
            self.network_target = float(max(10_000.0, min(50_000_000.0, network_target)))

    def solve_block(self, hashrate: Optional[float] = None) -> float:
        """Try to solve a block; return reward (0 if none)."""
        if hashrate is None:
            hashrate = self.recalc_hashrate()
        if hashrate <= 0:
            return 0.0

        # Abstract probability model: higher diff lowers chance.
        effective_hashrate = hashrate * max(0.0001, self.block_find_multiplier)
        prob = min(
            1.0,
            effective_hashrate / (max(0.0001, self.difficulty) * max(1.0, self.network_target)),
        )

        if random.random() >= prob:
            return 0.0

        self.blocks_found += 1
        self.shares_accepted += 1
        return self._block_reward_for_difficulty(self.difficulty)

    def mine(self) -> float:
        """One mine step: mine -> solve_block -> reward -> save to wallet.

        Returns reward earned in this step.
        """
        base_hashrate = self.recalc_hashrate()
        # Simulate small fluctuations like real miners (fan/temp/latency)
        jitter = 1.0 + random.uniform(-self.HASHRATE_JITTER_PCT, self.HASHRATE_JITTER_PCT)
        hashrate = max(0.0, base_hashrate * jitter)
        up = int(time.time() - self.started_at)

        if base_hashrate <= 0:
            self._log(f"[{up:>6}s] no active miners. buy rigs in Shop")
            return 0.0

        # Simulate share submission each tick.
        rejected = random.random() < self.reject_rate
        if rejected:
            self.shares_rejected += 1
        else:
            self.shares_accepted += 1

        reward = 0.0
        # Only an accepted share can become a block in this simplified model.
        if not rejected:
            reward = self.solve_block(hashrate=hashrate)

        if reward > 0:
            # reward -> save to wallet
            self.crypto += reward
            self._log(
                f"[{up:>6}s] accepted (1/1) diff {self.difficulty:.3f} +{reward:.6f} coins (blocks={self.blocks_found})"
            )
        else:
            status = "rejected" if rejected else "accepted"
            self._log(
                f"[{up:>6}s] {status:<8} speed 10s {hashrate:,.2f}H/s  diff {self.difficulty:.3f}  a/r {self.shares_accepted}/{self.shares_rejected}  boost x{self.block_find_multiplier:g}"
            )

        return reward

    def get_terminal_logs(self, last: int = 200) -> List[str]:
        if last <= 0:
            return []
        return self.terminal_logs[-last:]

    def get_price_history(self, minutes: int = 60) -> List[Dict[str, float]]:
        cutoff = time.time() - max(1, minutes) * 60
        return [{"t": float(ts), "price": float(p)} for ts, p in self.price_history if ts >= cutoff]

    def mining_tick(self) -> None:
        """Simulate a single mining tick.

        Mines crypto based on hashrate and difficulty, then updates market price
        slightly. This replaces the CLI "mine" action.
        """
        # Core mining step (xmrig-like): mine -> solve_block -> reward -> wallet
        hashrate = self.recalc_hashrate()
        self.mine()

        # Market price drifts a little (simple model)
        drift = random.uniform(-0.02, 0.02) * self.price
        self.price = max(0.1, self.price + drift)

        # Difficulty slowly adapts with overall hashrate
        self.difficulty = max(0.1, 1.0 + hashrate / 1000.0)

        # record price history (timestamp, price) but sampled to avoid save bloat
        now = time.time()
        if not self.price_history:
            self.price_history.append((now, self.price))
        else:
            last_ts = float(self.price_history[-1][0])
            if now - last_ts >= self.PRICE_HISTORY_SAMPLE_SEC:
                self.price_history.append((now, self.price))

        if len(self.price_history) > self.PRICE_HISTORY_MAX_POINTS:
            self.price_history = self.price_history[-self.PRICE_HISTORY_MAX_POINTS:]

    def buy_miner(self, miner_key: str) -> bool:
        """Attempt to buy one miner by key. Returns True on success."""
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
        """Stub for upgrades. Keep simple: one upgrade reduces difficulty growth.

        In a real port this would read existing CLI upgrade logic; here we keep
        a lightweight, compatible mechanic.
        """
        if upgrade_id == "efficiency_boost" and self.money >= 500:
            self.money -= 500
            # Permanently reduce difficulty by a flat amount (simple)
            self.difficulty = max(0.1, self.difficulty - 0.1)
            return True
        return False

    def sell_crypto(self, amount: float) -> bool:
        """Sell some crypto for money at current price."""
        if amount <= 0 or amount > self.crypto:
            return False
        self.crypto -= amount
        self.money += amount * self.price
        return True

    def save(self) -> None:
        """Save game state to JSON file."""
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
            "network_target": self.network_target,
            "block_find_multiplier": self.block_find_multiplier,
            "reject_rate": self.reject_rate,
        }
        with open(self.SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls) -> "GameState":
        """Load game state from JSON, or return default if none exists."""
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
                network_target=data.get("network_target", 1_000_000.0),
                block_find_multiplier=data.get("block_find_multiplier", 1.0),
                reject_rate=data.get("reject_rate", 0.02),
            )
            # prune oversized history from older saves
            if len(gs.price_history) > gs.PRICE_HISTORY_MAX_POINTS:
                gs.price_history = gs.price_history[-gs.PRICE_HISTORY_MAX_POINTS :]
            gs.recalc_hashrate()
            return gs
        except FileNotFoundError:
            return cls()
