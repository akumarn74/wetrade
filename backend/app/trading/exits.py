"""Pure helpers for exit logic (easy to unit test)."""


def emergency_tick_drop_triggered(prev_mark: float | None, mark: float, threshold_pct: float) -> bool:
    """
    If the option mark drops by >= threshold_pct in one monitor tick vs the previous mark,
    treat as a sudden move and force exit (strict stop behavior).
    """
    if prev_mark is None or prev_mark <= 0 or threshold_pct <= 0:
        return False
    return (mark - prev_mark) / prev_mark <= -threshold_pct
