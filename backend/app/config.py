from pydantic_settings import BaseSettings, SettingsConfigDict
import sys


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_mode: str = 'SIM'
    database_url: str = 'sqlite:///./wetrade.db'
    trading_enabled: bool = False

    claude_api_key: str = ''
    claude_model: str = 'claude-3-5-sonnet-latest'
    webull_app_key: str = ''
    webull_app_secret: str = ''
    webull_account_id: str = ''
    webull_openapi_domain: str = 'api.webull.com'
    webull_region_id: str = 'us'
    option_watchlist: str = ''
    trade_symbol: str = 'SPX'

    signal_loop_seconds: int = 60
    monitor_loop_seconds: int = 10
    order_timeout_seconds: int = 20

    market_open_time: str = '09:30'
    market_close_time: str = '16:00'
    no_trade_first_minutes: int = 10
    no_trade_last_minutes: int = 20

    max_trades_per_day: int = 3
    max_daily_loss: float = 150.0
    max_daily_profit: float = 100.0
    max_loss_per_trade_pct: float = 0.25
    take_profit_pct: float = 0.40
    trail_activation_pct: float = 0.20
    max_consecutive_losses: int = 2

    # Agent / LLM gates (do not bypass hard risk; they only skip questionable entries)
    min_entry_confidence: float = 0.0
    chop_blocks_entry: bool = True

    # Sudden option mark drop vs previous tick → immediate flat (0 disables)
    sudden_option_drop_pct: float = 0.12

    # API hardening: set REQUIRE_API_KEY=true in any deploy reachable beyond your laptop
    require_api_key: bool = False
    api_admin_key: str = ''


settings = Settings()


def validate_startup_config() -> None:
    valid_modes = {'SIM', 'WEBULL_PAPER', 'WEBULL_LIVE'}
    if settings.app_mode not in valid_modes:
        raise RuntimeError(f'APP_MODE must be one of {sorted(valid_modes)}')

    if settings.app_mode in {'WEBULL_PAPER', 'WEBULL_LIVE'}:
        if sys.version_info >= (3, 13):
            raise RuntimeError('Webull SDK dependencies are not compatible with Python 3.13 yet; use Python 3.11 or 3.12')
        required = {
            'WEBULL_APP_KEY': settings.webull_app_key,
            'WEBULL_APP_SECRET': settings.webull_app_secret,
            'WEBULL_ACCOUNT_ID': settings.webull_account_id,
            'OPTION_WATCHLIST': settings.option_watchlist,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(f'Missing required Webull config keys for {settings.app_mode}: {", ".join(missing)}')

    # Ensure option watchlist aligns with selected trade symbol.
    if settings.option_watchlist:
        watchlist = [x.strip().upper() for x in settings.option_watchlist.split(',') if x.strip()]
        mismatched = [sym for sym in watchlist if not sym.startswith(settings.trade_symbol.upper())]
        if mismatched:
            raise RuntimeError(
                f'OPTION_WATCHLIST symbols must start with TRADE_SYMBOL={settings.trade_symbol.upper()}. '
                f'Mismatched: {", ".join(mismatched[:5])}'
            )

    if settings.require_api_key and not (settings.api_admin_key or '').strip():
        raise RuntimeError('REQUIRE_API_KEY is true but API_ADMIN_KEY is missing or empty')
