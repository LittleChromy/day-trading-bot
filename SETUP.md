# Day Trading Bot - Setup & Operations Guide

## Prerequisites

- Alpaca account and API keys (free paper account: https://alpaca.markets)
- Docker + Docker Compose **or** Python 3.11+ and Node 18+

## 1. Configure

```bash
cp .env.example .env
```

Edit `.env` and set at least `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. Every option is
documented in `.env.example`. The defaults are deliberately safe:

| Setting | Default | Meaning |
|---|---|---|
| `AUTO_TRADE` | `false` | The bot only generates signals; you decide what to trade |
| `EXECUTION_MODE` | `simulated` | Trades are recorded in a local paper ledger at live prices; no orders leave the app |
| `ALPACA_BASE_URL` | paper URL | Alpaca paper account |
| `ALLOW_LIVE_TRADING` | `false` | Orders to a non-paper Alpaca URL are refused |
| `ALLOW_SHORTING` | `false` | SELL signals are shown but not traded |

## 2. Run

### Docker (recommended)

```bash
./start.sh            # or: docker compose up -d --build
```

- Dashboard: http://localhost:3000
- API: http://localhost:5000/api/health/status

Set `INSTALL_ML=true` in `.env` before building to include TensorFlow (adds the neural-network
model, ~600 MB). The Random Forest model works without it.

### Local development

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt        # + requirements-ml.txt for TensorFlow
cp .env.example .env                        # or rely on the root .env
python main.py                              # http://localhost:5000, SQLite by default
```

```bash
cd frontend
npm install
npm start                                   # http://localhost:3000
```

Tables are created (and new columns added to older databases) automatically on startup.

### Tests

```bash
cd backend
pytest
```

The tests use a fake market-data source, so they run offline without API keys.

## 3. How the bot works

Every `SIGNAL_INTERVAL` seconds (default 5 min) the scheduler runs one **bot cycle**:

1. **Monitor positions** – open trades are checked against their stop-loss / take-profit
   (also every `CHECK_INTERVAL` seconds). In `alpaca` mode the bracket order's legs are
   synced from the broker instead.
2. **Flatten before the close** – within `FLATTEN_MINUTES_BEFORE_CLOSE` of the bell, all
   positions are closed (day trading: nothing is held overnight).
3. **Scan** – each symbol in `STOCK_SYMBOLS` gets fresh bars (`BAR_TIMEFRAME`, default 5Min)
   and the seven strategies vote. A signal is stored when at least
   `MIN_AGREEING_STRATEGIES` agree and the confidence clears `CONFIDENCE_THRESHOLD`.
   Repeat signals for the same symbol are suppressed for `SIGNAL_COOLDOWN_MINUTES`.
4. **Trade** (only when auto-trading is on and the market is open) – each new signal passes
   the risk checks below, is sized, and opened with a stop and target attached.

Every 24 h (`RETRAIN_INTERVAL_HOURS`) the ML models are retrained on closed trades.

### Confidence score

```
agreement     = weight of the winning side / weight of all strategies that voted
participation = weight of all strategies that voted / total weight
confidence    = agreement × (0.5 + 0.5 × participation)
```

Once trained, the ML models' win probability is averaged with this score.

### Risk management

- **Position size**: the number of shares that loses `RISK_PER_TRADE_PCT` of equity if the stop
  is hit, capped at `MAX_POSITION_PCT` of equity and at available buying power.
- **Stop / target**: `STOP_LOSS_PCT` / `TAKE_PROFIT_PCT` from the entry price.
- **Limits**: one position per symbol, at most `MAX_OPEN_POSITIONS`, and no new trades after
  today's P&L drops below `-MAX_DAILY_LOSS_PCT` of equity.

### Execution modes

| | `simulated` | `alpaca` |
|---|---|---|
| Orders sent | none | market entry + bracket (stop & take-profit legs) |
| Fills | latest trade price | broker fills |
| Equity | `STARTING_CAPITAL` + realized + unrealized P&L | Alpaca account |
| Market hours | Alpaca clock (or regular-hours estimate) | Alpaca clock |

Recommended path: run `simulated` for a while → backtest and tune → `alpaca` against the
**paper** account → only then consider live trading.

## 4. Dashboard

- **Bot** – status, equity, today's P&L, start/stop auto-trading, run a cycle now, flatten
  everything, ML model versions and the activity log.
- **Signals** – recent signals with each strategy's vote; *Execute Trade* opens a position
  using the risk rules (leave quantity blank for automatic sizing).
- **Trades** – open trades with live unrealized P&L, close/cancel, and a form to log trades
  you placed elsewhere.
- **Analytics** – win rate, P&L, cumulative P&L, P&L by symbol and a per-strategy scorecard.
- **Backtest** – replay the strategy on historical Alpaca bars with your own stop/target/threshold.

## 5. API reference

All responses are JSON with a `status` field.

### Bot
- `GET  /api/bot/status` – mode, market state, open positions, risk settings
- `GET  /api/bot/account` – equity, buying power, today's P&L
- `POST /api/bot/auto-trade` `{"enabled": true}` – toggle auto-trading (until restart)
- `POST /api/bot/run` – run one cycle now
- `POST /api/bot/flatten` – close all open positions
- `GET  /api/bot/events?limit=50` – activity log
- `POST /api/bot/retrain` – retrain ML models now
- `GET  /api/bot/models` – trained model versions

### Signals
- `POST /api/signals/generate` `{"symbols": ["AAPL"]}` – scan now (symbols optional)
- `GET  /api/signals/recent?hours=24`
- `GET  /api/signals/by-symbol/<symbol>`
- `POST /api/signals/<id>/execute` `{"quantity": 10}` – open a trade from a signal (quantity optional)

### Trades
- `POST /api/trades/create` – log a trade placed elsewhere
  `{"symbol","trade_type":"BUY|SELL","entry_price","quantity","stop_loss?","take_profit?","signal_id?","notes?"}`
- `PUT  /api/trades/close/<id>` `{"exit_price": 151.75}` – exit price optional for bot-managed trades
- `PUT  /api/trades/cancel/<id>`
- `GET  /api/trades/all?status=OPEN&symbol=AAPL&limit=50`
- `GET  /api/trades/<id>`

### Analytics
- `GET /api/analytics/performance?days=7`
- `GET /api/analytics/by-symbol`
- `GET /api/analytics/signal-accuracy`
- `GET /api/analytics/strategies`
- `GET /api/analytics/equity-curve?days=30`

### Backtest
- `POST /api/backtest/run`
  `{"symbol": "AAPL", "days": 30, "timeframe": "5Min", "overrides": {"STOP_LOSS_PCT": 1, "TAKE_PROFIT_PCT": 2, "CONFIDENCE_THRESHOLD": 0.65}}`

### Health
- `GET /api/health/status`

## 6. Strategies

| Strategy | BUY when | SELL when | Weight |
|---|---|---|---|
| RSI (14, Wilder) | < 30 | > 70 | 0.15 |
| MACD (12/26/9) | histogram > 0 | histogram < 0 | 0.20 |
| Bollinger Bands (20, 2σ) | price ≤ lower band | price ≥ upper band | 0.15 |
| Moving averages (20/50) | short > long | short < long | 0.20 |
| Stochastic (14, high/low) | %K < 20 | %K > 80 | 0.10 |
| Volume (20) | volume > 1.5× avg on an up bar | … on a down bar | 0.10 |
| Momentum (10-bar ROC) | > 0 | < 0 | 0.10 |

## 7. Machine learning

Each signal that becomes a closed trade is a training example (features: confidence, side,
RSI, MACD histogram, Bollinger %B, MA spread, stochastic %K, volume ratio, momentum,
number of agreeing strategies; label: profitable or not). Training needs at least 10 such
trades with both wins and losses (30 for the neural network). Models are versioned in the
`ml_models` table and stored in `MODEL_PATH`.

## 8. Operations

```bash
docker compose logs -f backend     # bot activity, errors
docker compose ps
docker compose down                # stop (data persists in volumes)
docker compose down -v             # stop and DELETE all data
```

Run gunicorn with **one worker** (the default in the Dockerfile): each worker would otherwise
start its own scheduler and trade the same signals.

## 9. Security

- Never commit `.env`. If API keys were ever committed, regenerate them in the Alpaca dashboard.
- The API has no authentication. Keep port 5000 on localhost or behind a VPN/reverse proxy
  with auth — anyone who can reach it can toggle auto-trading and close positions.
- Change `POSTGRES_PASSWORD` and `SECRET_KEY` for anything beyond local use.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| "Alpaca API keys are not configured" | Set both keys in `.env`, then `docker compose up -d --build backend` |
| No signals ever appear | Market closed / not enough bars; try `CONFIDENCE_THRESHOLD=0.55` or `MIN_AGREEING_STRATEGIES=2`; check `docker compose logs backend` |
| `subscription does not permit querying recent SIP data` | Set `ALPACA_DATA_FEED=iex` |
| Bot skips signals | See the reason in `POST /api/bot/run` → `skipped`, or the Bot tab activity log |
| Dashboard can't reach the API | `REACT_APP_API_URL` is baked in at build time; rebuild the frontend after changing it |

## Disclaimer

This is a decision-support and paper-trading tool, not financial advice. No strategy wins
every trade, and past/backtested performance does not predict future results. Never trade
money you can't afford to lose.
