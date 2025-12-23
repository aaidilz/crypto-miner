from __future__ import annotations


def format_hashrate(hashrate_hs: float, *, precision: int = 2) -> str:
    """Format hashrate in H/s using SI units.

    Examples:
      950 -> "950.00 H/s"
      12_300 -> "12.30 kH/s"
      8_200_000 -> "8.20 MH/s"
    """

    try:
        value = float(hashrate_hs)
    except (TypeError, ValueError):
        value = 0.0

    value = max(0.0, value)
    units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s"]

    unit_index = 0
    while value >= 1000.0 and unit_index < len(units) - 1:
        value /= 1000.0
        unit_index += 1

    return f"{value:.{precision}f} {units[unit_index]}"
