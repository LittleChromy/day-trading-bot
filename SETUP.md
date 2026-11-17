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
- API: http://localhost:3000/api/health/status (also on port 5000)

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
3. **Scan** – each stock on the list (see *Stock scanner* below) gets fresh bars (`BAR_TIMEFRAME`, default 5Min)
   and the seven strategies vote. A signal is stored when at least
   `MIN_AGREEING_STRATEGIES` agree and the confidence clears `CONFIDENCE_THRESHOLD`.
   Repeat signals for the same symbol are suppressed for `SIGNAL_COOLDOWN_MINUTES`.
4. **Trade** (only when auto-trading is on and the market is open) – each new signal passes
   the risk checks below, is sized, and opened with a stop and target attached.

Every 24 h (`RETRAIN_INTERVAL_HOURS`) the ML models are retrained on closed trades.

### Stock scanner

With `AUTO_SCAN=true` (the default) the bot builds its own list every `SCAN_REFRESH_MINUTES`:

1. Candidates: Alpaca's screener for today's **most active** stocks and biggest **gainers**
   (and losers, only when `ALLOW_SHORTING=true`).
2. Filters: price between `SCAN_MIN_PRICE` and `SCAN_MAX_PRICE`, today's move no larger than
   `SCAN_MAX_MOVE_PCT`, plain common-stock symbols only, tradable on a major exchange.
3. The top `SCAN_MAX_SYMBOLS` are analyzed, plus `STOCK_SYMBOLS` when `SCAN_INCLUDE_WATCHLIST=true`.

"Best" means *active and liquid right now*: a way to find stocks worth analyzing, not a prediction
of which will rise. If the screener can't be reached the bot falls back to `STOCK_SYMBOLS`.
The Bot tab shows the current picks.

### Discord notifications

1. In Discord, create a server or pick a private channel → **Edit Channel** (gear icon) →
   **Integrations** → **Webhooks** → **New Webhook** → **Copy Webhook URL**.
2. Put it in `.env`: `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`
3. Restart the backend: `docker compose up -d --force-recreate backend`
4. Bot tab → **Send test**.

You get a message for each new signal, trade opened, trade closed (with P&L and the reason),
problems (no market data, rejected orders, daily loss limit hit) and a summary at the close.
`NOTIFY_SIGNALS=false` keeps only trade messages. The webhook URL is a secret: anyone who has it
can post to your channel.

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

## 5. Accounts and sharing

Everyone logs in. There are two kinds of account:

| | Admin | Normal user |
|---|---|---|
| Own bot (auto-trading switch, trades, analytics, settings) | yes | yes |
| Money | simulated, or Alpaca when `EXECUTION_MODE=alpaca` | always simulated |
| Sees other people's accounts | yes (Admin tab) | no |
| Manage users, open/close sign-up | yes | no |
| Scan now, rescan stocks, retrain models, run a cycle for everyone | yes | no |

Signals are shared: the market is scanned once and every account sees the same signals.
Each account decides what to trade with its own rules (Settings tab): minimum confidence, risk per
trade, stop loss, take profit, max positions, daily loss limit and starting balance. A user's
minimum confidence can only be stricter than the server's `CONFIDENCE_THRESHOLD`.

**The admin account.** Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` before starting, or
leave the password empty and open `http://localhost:3000` on the bot's computer: the first
account created there becomes the admin. (An account created through a shared link never becomes
admin.) Trades made before accounts existed are moved into the first admin account.

**Forgot a password?** On the bot's computer:

```bash
docker compose exec backend python manage.py list-users
docker compose exec backend python manage.py set-password <username>
docker compose exec backend python manage.py make-admin <username>
```

**Sharing a link.** The dashboard and API are only reachable from the bot's computer
(`127.0.0.1`). To give other people a link:

```bash
docker compose --profile share up -d
docker compose logs tunnel
```

The log prints an address like `https://random-words.trycloudflare.com`. It changes every time
the tunnel restarts; stop sharing with `docker compose stop tunnel`. Visitors see the login
page; with sign-up open (`ALLOW_SIGNUP`, or the checkbox in the Admin tab) they can create their
own account, otherwise the admin creates accounts for them.

Logins are kept for 30 days per browser. Changing a password, or an admin disabling an account,
logs that account out everywhere. Repeated wrong passwords are blocked for 15 minutes.

## 6. API reference

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
- `GET  /api/bot/universe` – stocks being analyzed (`POST` re-runs the scanner)
- `POST /api/bot/notify-test` – send a test Discord message

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

### Auth and accounts
All endpoints except `/api/health/status`, `/api/auth/config`, `/api/auth/login` and
`/api/auth/register` need `Authorization: Bearer <token>`. Everything is scoped to the logged-in
user; admins can pass `?user_id=<id>` to trades and analytics endpoints to look at someone else's.

- `GET  /api/auth/config` – whether sign-up is open / an admin still needs creating
- `POST /api/auth/register` `{"username", "password"}` → `{token, user}`
- `POST /api/auth/login` `{"username", "password"}` → `{token, user}`
- `GET  /api/auth/me`
- `PUT  /api/auth/password` `{"current_password", "new_password"}` → new token
- `GET|PUT /api/account/settings` – your risk rules, starting balance, Discord webhook
- `POST /api/account/reset` `{"confirm": "RESET"}` – start your simulated account over

### Admin (admins only)
- `GET  /api/admin/users` – every account with equity, P&L, win rate
- `POST /api/admin/users` `{"username", "password", "role"}`
- `PUT  /api/admin/users/<id>` `{"role"?, "is_active"?, "password"?, "auto_trade"?}`
- `DELETE /api/admin/users/<id>` – removes the account and its trades
- `PUT  /api/admin/signup` `{"allowed": bool}`
- Also admin-only: `POST /api/signals/generate`, `/api/bot/run`, `/api/bot/retrain`, `POST /api/bot/universe`

### Health
- `GET /api/health/status`

## 7. Strategies

| Strategy | BUY when | SELL when | Weight |
|---|---|---|---|
| RSI (14, Wilder) | < 30 | > 70 | 0.15 |
| MACD (12/26/9) | histogram > 0 | histogram < 0 | 0.20 |
| Bollinger Bands (20, 2σ) | price ≤ lower band | price ≥ upper band | 0.15 |
| Moving averages (20/50) | short > long | short < long | 0.20 |
| Stochastic (14, high/low) | %K < 20 | %K > 80 | 0.10 |
| Volume (20) | volume > 1.5× avg on an up bar | … on a down bar | 0.10 |
| Momentum (10-bar ROC) | > 0 | < 0 | 0.10 |

## 8. Machine learning

Each signal that becomes a closed trade is a training example (features: confidence, side,
RSI, MACD histogram, Bollinger %B, MA spread, stochastic %K, volume ratio, momentum,
number of agreeing strategies; label: profitable or not). Training needs at least 10 such
trades with both wins and losses (30 for the neural network). Models are versioned in the
`ml_models` table and stored in `MODEL_PATH`.

## 9. Operations

```bash
docker compose logs -f backend     # bot activity, errors
docker compose ps
docker compose down                # stop (data persists in volumes)
docker compose down -v             # stop and DELETE all data
```

Run gunicorn with **one worker** (the default in the Dockerfile): each worker would otherwise
start its own scheduler and trade the same signals.

## 10. Security

- Never commit `.env`. If API keys were ever committed, regenerate them in the Alpaca dashboard.
- Ports 3000 and 5000 are bound to `127.0.0.1`. Share the dashboard through the tunnel
  (section 5) rather than opening those ports.
- Every API call except the health check needs a login. Passwords are stored hashed.
- Anyone you give the link to can create an account while sign-up is open. Close it in the Admin
  tab once everyone you invited has signed up.
- Other users never touch your Alpaca account: their trades are simulated.
- Change `POSTGRES_PASSWORD` and `SECRET_KEY` for anything beyond local use.

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| "Alpaca API keys are not configured" | Set both keys in `.env`, then `docker compose up -d --build backend` |
| No signals ever appear | Market closed / not enough bars; try `CONFIDENCE_THRESHOLD=0.55` or `MIN_AGREEING_STRATEGIES=2`; check `docker compose logs backend` |
| `subscription does not permit querying recent SIP data` | Set `ALPACA_DATA_FEED=iex` |
| No Discord messages | Bot tab → **Send test** shows the reason; check `DISCORD_WEBHOOK_URL` and restart the backend |
| "Scanner unavailable" on the Bot tab | The bot is using `STOCK_SYMBOLS` instead; see the backend log for the screener error |
| Bot skips signals | See the reason in `POST /api/bot/run` → `skipped`, or the Bot tab activity log |
| Dashboard says "API offline" | `docker compose ps` – the backend may still be starting; `docker compose logs backend` |
| Can't log in as admin | `docker compose exec backend python manage.py set-password admin` (see section 5) |
| Some buttons are missing | Scan Now, Run cycle, Rescan and Retrain are admin-only; normal accounts don't see them |

## Disclaimer

This is a decision-support and paper-trading tool, not financial advice. No strategy wins
every trade, and past/backtested performance does not predict future results. Never trade
money you can't afford to lose.
