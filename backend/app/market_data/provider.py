from datetime import datetime, timedelta

from app.config import settings
from app.integrations.webull_client import WebullAPIClient
from app.trading.types import Candle, OptionContract, SignalContext


class MockMarketDataProvider:
    def latest_signal_context(self, symbol: str = 'SPY') -> SignalContext:
        return SignalContext(
            symbol=symbol,
            price=520.5,
            vwap=519.7,
            prev_high=520.0,
            prev_low=518.8,
            ma5=520.2,
            ma10=519.9,
            ma20=519.1,
            volume=1_800_000,
            avg_volume=1_200_000,
            day_high=521.0,
            day_low=516.5,
        )

    def recent_candles(self, symbol: str = 'SPY') -> list[Candle]:
        now = datetime.utcnow()
        candles = []
        price = 518.0
        for i in range(12):
            close = price + 0.2
            candles.append(Candle(ts=now - timedelta(minutes=(12 - i) * 5), open=price, high=close + 0.1, low=price - 0.1, close=close, volume=1000 + i * 20))
            price = close
        return candles

    def option_chain(self, symbol: str = 'SPY') -> list[OptionContract]:
        return [
            OptionContract('SPY-0DTE-520-C', '0DTE', 520, 'C', 0.44, 2.00, 2.15, 400, 1200),
            OptionContract('SPY-0DTE-519-P', '0DTE', 519, 'P', -0.46, 2.10, 2.30, 350, 950),
            OptionContract('SPY-1DTE-521-C', '1DTE', 521, 'C', 0.32, 1.65, 1.95, 80, 210),
        ]


class WebullMarketDataProvider(MockMarketDataProvider):
    """
    Webull-backed market data provider for WEBULL_PAPER/WEBULL_LIVE modes.
    """

    @staticmethod
    def _webull_symbol_for_us_stock_bars(symbol: str) -> str:
        """Webull US_STOCK history excludes cash indices (e.g. SPX); SPY is the usual S&P 500 proxy."""
        s = (symbol or '').strip().upper()
        if s == 'SPX':
            return 'SPY'
        return s

    @staticmethod
    def _webull_category_for_equity_bars(bar_symbol: str) -> str:
        """Webull splits stocks vs ETFs (Data API); SPY must use US_ETF, not US_STOCK."""
        if (bar_symbol or '').strip().upper() == 'SPY':
            return 'US_ETF'
        return 'US_STOCK'

    def __init__(self, mode: str):
        self.mode = mode
        self.client = WebullAPIClient().api
        self.watchlist = [x.strip() for x in settings.option_watchlist.split(',') if x.strip()]
        if not self.watchlist:
            raise RuntimeError('OPTION_WATCHLIST must include at least one option symbol for Webull modes')

    def latest_signal_context(self, symbol: str = 'SPY') -> SignalContext:
        bar_symbol = self._webull_symbol_for_us_stock_bars(symbol)
        bar_cat = self._webull_category_for_equity_bars(bar_symbol)
        bars_resp = self.client.market_data.get_history_bar(bar_symbol, category=bar_cat, timespan='M5', count='30')
        bars = bars_resp.json()
        if not isinstance(bars, list) or len(bars) < 21:
            raise RuntimeError('Webull history bars response does not contain enough data')

        closes = [float(item.get('close', 0.0)) for item in bars]
        highs = [float(item.get('high', 0.0)) for item in bars]
        lows = [float(item.get('low', 0.0)) for item in bars]
        volumes = [float(item.get('volume', 0.0)) for item in bars]
        current = bars[-1]
        typical_prices = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
        vwap_den = sum(volumes[-20:]) or 1.0
        vwap_num = sum(typical_prices[-20 + i] * volumes[-20 + i] for i in range(20))
        vwap = vwap_num / vwap_den

        return SignalContext(
            symbol=symbol,
            price=closes[-1],
            vwap=vwap,
            prev_high=highs[-2],
            prev_low=lows[-2],
            ma5=sum(closes[-5:]) / 5,
            ma10=sum(closes[-10:]) / 10,
            ma20=sum(closes[-20:]) / 20,
            volume=volumes[-1],
            avg_volume=(sum(volumes[-20:]) / 20),
            day_high=max(highs),
            day_low=min(lows),
        )

    def option_chain(self, symbol: str = 'SPY') -> list[OptionContract]:
        snapshots_resp = self.client.market_data.get_snapshot(','.join(self.watchlist), category='US_OPTION')
        snapshots = snapshots_resp.json()
        if not isinstance(snapshots, list):
            raise RuntimeError('Webull option snapshot response is invalid')

        contracts: list[OptionContract] = []
        for snap in snapshots:
            option_symbol = str(snap.get('symbol') or '')
            if not option_symbol:
                continue
            bid = float(snap.get('bid_price') or snap.get('bid') or 0.0)
            ask = float(snap.get('ask_price') or snap.get('ask') or 0.0)
            delta = snap.get('delta')
            if delta is None:
                delta = snap.get('greeks_delta')
            if delta is None:
                raise RuntimeError(f'Missing delta/greeks_delta for {option_symbol}; cannot enforce delta gate')
            option_type = str(snap.get('option_type') or '')
            right = 'C' if option_type.upper().startswith('C') else 'P'
            contracts.append(
                OptionContract(
                    option_symbol=option_symbol,
                    expiry=str(snap.get('expiration_date') or ''),
                    strike=float(snap.get('strike_price') or 0.0),
                    right=right,
                    delta=float(delta),
                    bid=bid,
                    ask=ask,
                    volume=int(float(snap.get('volume') or 0)),
                    open_interest=int(float(snap.get('open_interest') or 0)),
                )
            )
        return contracts

    def option_mark(self, option_symbol: str) -> float:
        snapshot = self.client.market_data.get_snapshot(option_symbol, category='US_OPTION').json()
        if not snapshot or not isinstance(snapshot, list):
            raise RuntimeError(f'No option snapshot returned for {option_symbol}')
        row = snapshot[0]
        bid = float(row.get('bid_price') or row.get('bid') or 0.0)
        ask = float(row.get('ask_price') or row.get('ask') or 0.0)
        last = float(row.get('close') or row.get('last_price') or 0.0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        if last > 0:
            return last
        raise RuntimeError(f'Unable to compute mark price for {option_symbol}')
