from dataclasses import dataclass
from typing import List


@dataclass
class MinerSpec:
    key: str
    name: str
    cost: float
    hashrate: float  # abstract units
    description: str = ""


# A small list of miner types. Keep it simple and readable.
AVAILABLE_MINERS: List[MinerSpec] = [
    MinerSpec(key="asic_small", name="ASIC Small", cost=200.0, hashrate=5.0, description="Entry-level ASIC."),
    MinerSpec(key="asic_medium", name="ASIC Medium", cost=800.0, hashrate=25.0, description="Balanced miner."),
    MinerSpec(key="asic_large", name="ASIC Large", cost=3000.0, hashrate=120.0, description="High-end miner."),
]
