from interaction.variance_injector import apply_variance


def build_mouse_path(
    start: tuple[int, int],
    end: tuple[int, int],
    steps: int = 6,
    jitter: float = 0.0,
) -> list[tuple[int, int]]:
    if start == end:
        return [end]
    if steps < 2:
        return [end]

    path: list[tuple[int, int]] = []
    for index in range(steps):
        t = index / (steps - 1)
        x = start[0] + (end[0] - start[0]) * t
        y = start[1] + (end[1] - start[1]) * t
        if 0 < index < steps - 1 and jitter > 0:
            x = apply_variance(x, jitter)
            y = apply_variance(y, jitter)
        path.append((round(x), round(y)))
    return path
