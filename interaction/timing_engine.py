import random


def bounded_delay(
    base_seconds: float,
    spread_seconds: float,
    minimum: float,
    maximum: float,
) -> float:
    sampled = random.gauss(base_seconds, spread_seconds)
    return max(minimum, min(maximum, sampled))
