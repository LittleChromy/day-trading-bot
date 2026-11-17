# Day Trading Bot - Changelog

## [1.4.0] - 2026-11-17

### Added
- Accounts: log in / sign up, with `admin` and `user` roles. Each account has its own simulated
  balance, trades, auto-trading switch (now saved across restarts), risk settings, analytics,
  activity log and Discord webhook. Signals are shared.
- Admin tab: every account's equity, P&L and win rate; create, promote, disable, delete accounts,
  reset passwords; open or close sign-up
- Settings tab: per-account trading rules, starting balance, Discord link, password change,
  account reset
- `manage.py` for password recovery from the command line

### Changed
- Replaces the view-only/`X-Admin-Token` sharing mode: every API call except the health check
  needs a login
- Normal accounts are always simulated; only admins trade through Alpaca
- Trades link to signals through `trades.signal_id` (old links are migrated automatically)

## [1.3.0] - 2026-11-14

### Added
- Shareable dashboard: optional Cloudflare tunnel (`docker compose --profile share up -d`)
- View-only access for visitors: state-changing API calls require `localhost` or `ADMIN_PASSWORD`
  (`auth.py`); the dashboard hides its controls and offers Unlock/Lock

### Changed
- The dashboard reaches the API through `/api` on its own address (nginx proxy) instead of a
  hard-coded `http://localhost:5000`, so it works from any address
- Ports 3000, 5000 and 5432 are bound to `127.0.0.1`

## [1.2.0] - 2026-11-12

### Added
- Stock scanner (`scanner.py`): analyzes the day's most active stocks and gainers from Alpaca's
  screener, filtered by price, size of today's move and tradability; falls back to the fixed
  watchlist when the screener is unavailable (`AUTO_SCAN`, `SCAN_*` settings)
- Discord notifications (`notifier.py`): new signals, entries, exits with P&L, problems, daily
  loss halt and an end-of-day summary (`DISCORD_WEBHOOK_URL`)
- `/api/bot/universe` and `/api/bot/notify-test`; Bot tab shows scanner picks and notification status

### Fixed
- "Scan Now" reported "no new signals" when Alpaca rejected the API keys; it now says that no
  market data came back

## [1.1.0] - 2026-11-07

### Added
- Trading engine (`trading_engine.py`): executes signals, attaches stop-loss/take-profit,
  monitors positions, flattens before the close, logs every action to `bot_events`
- Execution modes: `simulated` (local paper ledger) and `alpaca` (bracket orders); live
  accounts refused unless `ALLOW_LIVE_TRADING=true`
- Risk management (`risk_manager.py`): risk-based sizing, position cap, max open positions,
  one position per symbol, daily loss limit, long-only by default
- Walk-forward backtester and `/api/backtest/run`
- Bot API (`/api/bot/*`): status, account, auto-trade toggle, run cycle, flatten, events, retrain, models
- `POST /api/signals/<id>/execute`, `PUT /api/trades/cancel/<id>`
- Analytics: per-strategy scorecard and cumulative P&L curve
- Dashboard: Bot and Backtest tabs, working Execute Trade, trade logging form, live unrealized P&L
- Automatic schema upgrade for databases created by 1.0.0
- Offline pytest suite with a fake market-data source

### Fixed
- `gunicorn app:app` failed: `app.py` exposed no app object; now `app:create_app()`
- Scheduler imported the uninstalled `schedule` package; now uses APScheduler
- 4 gunicorn workers each started a scheduler; now one worker with threads
- Scheduler stored strategy details with `str()` instead of JSON, breaking every later read
- Alpaca bars were requested without a start date or data feed (empty outside market hours,
  SIP errors on free accounts)
- ML features shifted columns when a strategy didn't vote; now fixed-position features
- Signal accuracy counted still-open trades as failures
- A single agreeing strategy could produce a 100% confidence signal
- RSI divided by zero on flat data; stochastic ignored bar highs/lows
- `.env.example` missing at repo root (`start.sh` copies it); frontend API URL not passed at build time

### Changed
- TensorFlow is optional (`requirements-ml.txt`, `INSTALL_ML=true`)
- Local runs default to SQLite when `DATABASE_URL` is unset

## [1.0.0] - 2026-06-30

### Added
- Initial release
- 7 technical analysis strategies (RSI, MACD, Bollinger Bands, MA Crossover, Stochastic, Volume, Momentum)
- Strategy Engine combining multiple signals with weighted confidence scores
- Trading signal generation and management
- Trade tracking and P&L calculation
- Real-time performance analytics
- Signal accuracy metrics
- Machine Learning models (Random Forest & Neural Network)
- Automatic model retraining every 24 hours
- Self-learning capabilities that improve over time
- Flask REST API with comprehensive endpoints
- React dashboard with real-time updates
- Docker Compose deployment configuration
- PostgreSQL database for data persistence
- Alpaca API integration for real-time market data
- Paper trading support
- Comprehensive documentation and setup guide

### Features
- Real-time market data integration
- Customizable trading parameters
- Historical trade tracking
- Performance metrics by symbol
- Strategy performance monitoring
- API health checks
- Automated signal scheduling
- Support for multiple stock symbols

### Technical Stack
- Backend: Python, Flask, SQLAlchemy, scikit-learn, TensorFlow
- Frontend: React, Chart.js, Tailwind CSS
- Database: PostgreSQL
- Data Source: Alpaca Markets API
- Deployment: Docker, Docker Compose

### Security
- Environment variable configuration for API keys
- CORS protection
- Database connection pooling
- Input validation on all endpoints

### Documentation
- Complete setup guide
- API endpoint documentation
- Strategy explanation
- Troubleshooting guide
- Contributing guidelines

### Known Limitations
- Paper trading only (no real money trading in v1)
- Single symbol performance degradation with >100 symbols
- ML models require minimum 20 trades to train
- Intraday data only (no after-hours)

### Future Roadmap
- Real money trading integration
- Advanced risk management (stop-loss, take-profit)
- Portfolio optimization
- Backtesting framework
- Custom strategy builder
- Discord/Telegram alerts
- Mobile app
- Cloud deployment templates
