import json
import random
from dataclasses import dataclass, field
from typing import Dict
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

    SAVE_FILE = "savegame.json"

    def recalc_hashrate(self) -> float:
        """Recalculate total hashrate from owned miners."""
        total = 0.0
        for spec in AVAILABLE_MINERS:
            count = self.miners_owned.get(spec.key, 0)
            total += count * spec.hashrate
        self.hash_rate_cache = total
        return total

    def mining_tick(self) -> None:
        """Simulate a single mining tick.

        Mines crypto based on hashrate and difficulty, then updates market price
        slightly. This replaces the CLI "mine" action.
        """
        hashrate = self.recalc_hashrate()
        # Simple yield formula: yield = hashrate / (difficulty * 1000)
        generated = (hashrate / max(0.0001, self.difficulty)) * 0.01
        # small randomness
        generated *= random.uniform(0.9, 1.1)
        self.crypto += generated

        # Market price drifts a little (simple model)
        drift = random.uniform(-0.02, 0.02) * self.price
        self.price = max(0.1, self.price + drift)

        # Difficulty slowly adapts with overall hashrate
        self.difficulty = max(0.1, 1.0 + hashrate / 1000.0)

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
            )
            gs.recalc_hashrate()
            return gs
        except FileNotFoundError:
            return cls()
