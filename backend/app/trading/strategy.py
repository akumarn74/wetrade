from app.trading.types import SignalContext, TradeSignal


class StrategyEngine:
    def evaluate(self, ctx: SignalContext) -> TradeSignal | None:
        volume_expanding = ctx.volume > (ctx.avg_volume * 1.2)

        call = (
            ctx.price > ctx.vwap
            and ctx.price > ctx.prev_high
            and ctx.ma5 > ctx.ma10 > ctx.ma20
            and volume_expanding
        )

        put = (
            ctx.price < ctx.vwap
            and ctx.price < ctx.prev_low
            and ctx.ma5 < ctx.ma10 < ctx.ma20
            and volume_expanding
        )

        if call:
            return TradeSignal(side='CALL', reason='rule_call_setup')
        if put:
            return TradeSignal(side='PUT', reason='rule_put_setup')
        return None
