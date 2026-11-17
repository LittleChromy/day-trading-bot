# Day Trading Bot

A day trading bot for US stocks: it scans a watchlist with seven technical strategies,
scores each opportunity, and can trade automatically with built-in risk management —
in a local simulated ledger or through an Alpaca paper account.

## Features

- **Signals** – RSI, MACD, Bollinger Bands, moving-average trend, stochastic, volume and
  momentum vote on every symbol; weighted agreement becomes a confidence score.
- **Stock scanner** – picks the day's most active stocks and movers on its own, filtered
  for price, size of the move and tradability, alongside your fixed watchlist.
- **Discord notifications** – signals, entries, exits with P&L, problems and a daily summary.
- **Automated trading** – opt-in. Opens positions from high-confidence signals, attaches
  stop-loss / take-profit, and closes everything before the market closes.
- **Risk management** – risk-based position sizing, max position size, max open positions,
  one position per symbol, daily loss limit, long-only by default.
- **Two execution modes** – `simulated` (no orders leave the app) or `alpaca` (bracket
  orders to Alpaca; live accounts refused unless explicitly allowed).
- **Backtesting** – replay the strategy on historical bars with your own parameters.
- **Self-learning** – a Random Forest (and optional neural network) learns which signals
  turned into winners and adjusts future confidence scores.
- **Accounts** – an admin plus normal users, each with their own simulated bot, trades,
  settings and analytics. One command gives you a public link to share.
- **Dashboard** – bot control, signals, trades with live P&L, analytics, backtests.

## Quick start

```bash
cp .env.example .env      # add your Alpaca paper API keys
./start.sh                # docker compose up
```

Open http://localhost:3000. See [SETUP.md](SETUP.md) for local development, configuration,
how the bot decides and the full API reference.

## Tech stack

- **Backend**: Python 3.11, Flask, SQLAlchemy, pandas, scikit-learn, APScheduler (TensorFlow optional)
- **Frontend**: React 18, Chart.js
- **Database**: PostgreSQL (Docker) or SQLite (local)
- **Market data & brokerage**: Alpaca

## Project structure

```
backend/
  app.py                 application factory (gunicorn 'app:create_app()')
  config.py              all settings, overridable from .env
  data_handler.py        Alpaca market data, account and orders
  strategies/            indicators + StrategyEngine (signal scoring)
  scanner.py             picks which stocks to analyze (Alpaca screener + filters)
  notifier.py            Discord notifications
  auth.py                logins, sessions, admin/user roles
  manage.py              command-line password reset / admin tools
  signal_service.py      scan symbols, store signals, credit strategies after trades
  risk_manager.py        position sizing and pre-trade checks
  trading_engine.py      the bot: entries, exits, monitoring, end-of-day flatten
  backtester.py          walk-forward backtester
  ml_trainer.py          model training and confidence adjustment
  scheduler.py           background jobs
  api/routes/            REST endpoints
  tests/                 pytest suite (runs offline)
frontend/
  src/components/        Bot, Signals, Trades, Analytics, Backtest panels
docker-compose.yml
```

## Warning

This is a decision-support tool, not a guaranteed money printer. No trading strategy has a
100% success rate. Start in simulated mode, then Alpaca paper trading, and never trade money
you can't afford to lose.
