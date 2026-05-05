from app.trading.types import OptionContract


class ContractSelector:
    def select(self, contracts: list[OptionContract], side: str) -> OptionContract | None:
        right = 'C' if side == 'CALL' else 'P'
        filtered = [
            c
            for c in contracts
            if c.right == right
            and 0.35 <= abs(c.delta) <= 0.55
            and c.volume >= 100
            and c.open_interest >= 100
            and c.spread_pct <= 0.10
        ]
        if not filtered:
            return None
        filtered.sort(key=lambda c: (c.spread_pct, -c.volume, -c.open_interest))
        return filtered[0]
