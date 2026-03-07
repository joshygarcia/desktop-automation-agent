import random


def apply_variance(value: float, maximum_offset: float = 0.0) -> float:
    if maximum_offset <= 0:
        return value
    return value + random.uniform(-maximum_offset, maximum_offset)
