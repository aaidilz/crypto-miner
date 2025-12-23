from dataclasses import dataclass
from typing import List


@dataclass
class MinerSpec:
    key: str
    name: str
    cost: float
    hashrate: float  # H/s
    description: str = ""


# Hashrate values are approximate/"game-realistic" (not tied to a specific algorithm).
# Units are hashes per second (H/s).
AVAILABLE_MINERS: List[MinerSpec] = [
    MinerSpec(
        key="cpu_basic",
        name="CPU Rig (Basic)",
        cost=250.0,
        hashrate=75_000.0,  # 75 kH/s
        description="Entry rig. Low power, low hashrate.",
    ),
    MinerSpec(
        key="gpu_6gb",
        name="GPU Miner (6GB)",
        cost=1_500.0,
        hashrate=12_000_000.0,  # 12 MH/s
        description="Budget GPU. Good early upgrade.",
    ),
    MinerSpec(
        key="gpu_12gb",
        name="GPU Miner (12GB)",
        cost=4_500.0,
        hashrate=45_000_000.0,  # 45 MH/s
        description="Mid-range GPU. Solid efficiency.",
    ),
    MinerSpec(
        key="gpu_flagship",
        name="GPU Miner (Flagship)",
        cost=12_000.0,
        hashrate=140_000_000.0,  # 140 MH/s
        description="High-end GPU rig.",
    ),
    MinerSpec(
        key="asic_entry",
        name="ASIC (Entry)",
        cost=30_000.0,
        hashrate=8_000_000_000_000.0,  # 8 TH/s
        description="Entry ASIC. Big jump in speed.",
    ),
    MinerSpec(
        key="asic_pro",
        name="ASIC (Pro)",
        cost=85_000.0,
        hashrate=40_000_000_000_000.0,  # 40 TH/s
        description="Pro ASIC. Very fast.",
    ),
    MinerSpec(
        key="asic_farm",
        name="ASIC Farm (Rack)",
        cost=260_000.0,
        hashrate=180_000_000_000_000.0,  # 180 TH/s
        description="Rack of ASICs. Extreme hashrate.",
    ),
]
