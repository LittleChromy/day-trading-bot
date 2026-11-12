import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_float(name, default):
    value = os.getenv(name)
    try:
        return float(value) if value not in (None, '') else default
    except ValueError:
        return default


def _env_int(name, default):
    value = os.getenv(name)
    try:
        return int(value) if value not in (None, '') else default
    except ValueError:
        return default


class Config:
    """Base configuration. Every value can be overridden with an environment variable."""
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')

    # Database (falls back to a local SQLite file so the app runs without Postgres)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///day_trading_bot.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Alpaca API
    ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
    ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
    ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    # 'iex' works with free Alpaca accounts; 'sip' requires a paid data plan
    ALPACA_DATA_FEED = os.getenv('ALPACA_DATA_FEED', 'iex')

    # Market data / scanning
    STOCK_SYMBOLS = [s.strip().upper() for s in
                     os.getenv('STOCK_SYMBOLS', 'AAPL,MSFT,GOOGL,AMZN,NVDA').split(',') if s.strip()]
    BAR_TIMEFRAME = os.getenv('BAR_TIMEFRAME', '5Min')
    BAR_LIMIT = _env_int('BAR_LIMIT', 200)
    CHECK_INTERVAL = _env_int('CHECK_INTERVAL', 60)            # seconds between position checks
    SIGNAL_INTERVAL = _env_int('SIGNAL_INTERVAL', 300)         # seconds between signal scans
    RETRAIN_INTERVAL_HOURS = _env_int('RETRAIN_INTERVAL_HOURS', 24)
    ENABLE_SCHEDULER = _env_bool('ENABLE_SCHEDULER', True)

    # Strategy configuration
    CONFIDENCE_THRESHOLD = _env_float('CONFIDENCE_THRESHOLD', 0.60)
    MIN_AGREEING_STRATEGIES = _env_int('MIN_AGREEING_STRATEGIES', 3)
    RSI_PERIOD = 14
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    BB_PERIOD = 20
    BB_STD_DEV = 2
    MA_SHORT = 20
    MA_LONG = 50

    # Automated trading / risk management
    AUTO_TRADE = _env_bool('AUTO_TRADE', False)                # bot places trades on its own
    # 'simulated' = internal paper ledger using live prices, 'alpaca' = orders sent to Alpaca
    EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'simulated').lower()
    ALLOW_LIVE_TRADING = _env_bool('ALLOW_LIVE_TRADING', False)  # must be true to use a non-paper URL
    ALLOW_SHORTING = _env_bool('ALLOW_SHORTING', False)
    STARTING_CAPITAL = _env_float('STARTING_CAPITAL', 100000.0)  # used by simulated mode/backtests
    RISK_PER_TRADE_PCT = _env_float('RISK_PER_TRADE_PCT', 1.0)   # % of equity risked per trade
    MAX_POSITION_PCT = _env_float('MAX_POSITION_PCT', 10.0)      # max % of equity in one position
    STOP_LOSS_PCT = _env_float('STOP_LOSS_PCT', 1.5)
    TAKE_PROFIT_PCT = _env_float('TAKE_PROFIT_PCT', 3.0)
    MAX_OPEN_POSITIONS = _env_int('MAX_OPEN_POSITIONS', 5)
    MAX_DAILY_LOSS_PCT = _env_float('MAX_DAILY_LOSS_PCT', 3.0)   # halt new trades after this daily loss
    FLATTEN_AT_CLOSE = _env_bool('FLATTEN_AT_CLOSE', True)       # close everything before the bell
    FLATTEN_MINUTES_BEFORE_CLOSE = _env_int('FLATTEN_MINUTES_BEFORE_CLOSE', 10)
    SIGNAL_COOLDOWN_MINUTES = _env_int('SIGNAL_COOLDOWN_MINUTES', 30)

    # Stock scanner: pick today's most active stocks and movers automatically
    AUTO_SCAN = _env_bool('AUTO_SCAN', True)
    SCAN_INCLUDE_WATCHLIST = _env_bool('SCAN_INCLUDE_WATCHLIST', True)  # also analyze STOCK_SYMBOLS
    SCAN_MAX_SYMBOLS = _env_int('SCAN_MAX_SYMBOLS', 15)
    SCAN_CANDIDATES = _env_int('SCAN_CANDIDATES', 50)
    SCAN_MIN_PRICE = _env_float('SCAN_MIN_PRICE', 5.0)
    SCAN_MAX_PRICE = _env_float('SCAN_MAX_PRICE', 1000.0)
    SCAN_MAX_MOVE_PCT = _env_float('SCAN_MAX_MOVE_PCT', 25.0)       # skip stocks already up/down more than this today
    SCAN_REFRESH_MINUTES = _env_int('SCAN_REFRESH_MINUTES', 15)

    # Notifications
    DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
    NOTIFY_SIGNALS = _env_bool('NOTIFY_SIGNALS', True)
    NOTIFY_TRADES = _env_bool('NOTIFY_TRADES', True)

    # Machine learning
    MODEL_PATH = os.getenv('MODEL_PATH', 'model_files/')
    USE_ML_ADJUSTMENT = _env_bool('USE_ML_ADJUSTMENT', True)

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    ENABLE_SCHEDULER = False
    USE_ML_ADJUSTMENT = False
    AUTO_SCAN = False
    DISCORD_WEBHOOK_URL = ''


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
