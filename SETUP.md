# Day Trading Bot - Setup & Deployment Guide

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Alpaca API Keys (https://alpaca.markets)
- PostgreSQL 15+ (or use Docker)
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### 1. Environment Setup

Create a `.env` file in the root directory:

```bash
# Alpaca API Configuration
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # Use paper trading first!

# Database Configuration
DATABASE_URL=postgresql://trading_user:trading_password@postgres:5432/day_trading_bot

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your_secret_key_here

# Stock Symbols to Monitor
STOCK_SYMBOLS=AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,AMD,META,NFLX,UBER
CHECK_INTERVAL=60
```

### 2. Docker Deployment (Recommended)

```bash
# Clone and navigate to repository
git clone https://github.com/LittleChromy/day-trading-bot.git
cd day-trading-bot

# Copy .env file
cp .env.example .env
# Edit .env with your Alpaca API keys

# Build and start services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend
```

Access:
- **Frontend Dashboard**: http://localhost:3000
- **API Documentation**: http://localhost:5000/api/health/status
- **Database**: postgres://trading_user:trading_password@localhost:5432/day_trading_bot

### 3. Local Development Setup

#### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up database
cp .env.example .env
# Edit .env with your settings

# Create database tables
flask db upgrade

# Run Flask development server
python main.py
```

Backend runs at: http://localhost:5000

#### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Create .env file
echo "REACT_APP_API_URL=http://localhost:5000/api" > .env

# Start development server
npm start
```

Frontend runs at: http://localhost:3000

## API Endpoints

### Signals
- `POST /api/signals/generate` - Generate new trading signals
- `GET /api/signals/recent?hours=24` - Get recent signals
- `GET /api/signals/by-symbol/<symbol>` - Get signals for a specific symbol

### Trades
- `POST /api/trades/create` - Create a new trade
- `PUT /api/trades/close/<trade_id>` - Close an open trade
- `GET /api/trades/all` - Get all trades (with filters)
- `GET /api/trades/<trade_id>` - Get a specific trade

### Analytics
- `GET /api/analytics/performance?days=7` - Get performance metrics
- `GET /api/analytics/by-symbol` - Get performance by symbol
- `GET /api/analytics/signal-accuracy` - Get signal accuracy metrics

### Health
- `GET /api/health/status` - API health check

## Trading Strategies

The bot uses 7 technical analysis strategies:

1. **RSI (Relative Strength Index)**
   - Overbought > 70 (SELL signal)
   - Oversold < 30 (BUY signal)
   - Period: 14

2. **MACD (Moving Average Convergence Divergence)**
   - MACD > Signal Line (BUY)
   - MACD < Signal Line (SELL)
   - Fast EMA: 12, Slow EMA: 26, Signal: 9

3. **Bollinger Bands**
   - Price at lower band (BUY)
   - Price at upper band (SELL)
   - Period: 20, Std Dev: 2

4. **Moving Average Crossover**
   - Short MA > Long MA (BUY)
   - Short MA < Long MA (SELL)
   - Short Period: 20, Long Period: 50

5. **Stochastic Oscillator**
   - %K < 20 (BUY - Oversold)
   - %K > 80 (SELL - Overbought)
   - Period: 14

6. **Volume Analysis**
   - High volume on price increase (BUY signal strengthened)
   - High volume on price decrease (SELL signal strengthened)

7. **Momentum**
   - Positive momentum (BUY)
   - Negative momentum (SELL)
   - Period: 10

## Machine Learning

The bot includes self-learning capabilities:

- **Random Forest Classifier**: Learns from historical trades to predict profitable signals
- **Neural Network**: Deep learning model for signal quality prediction
- **Automatic Retraining**: Models retrain every 24 hours with new trade data
- **Confidence Score Adjustment**: ML predictions adjust signal confidence scores

### Model Training

Models are automatically trained on closed trades:

```bash
# Manual model retraining
from ml_trainer import MLTrainer
trainer = MLTrainer()
trainer.train_random_forest()
trainer.train_neural_network()
```

## Database Schema

### Trades Table
- `id` - Primary key
- `symbol` - Stock symbol
- `trade_type` - BUY or SELL
- `entry_price` - Trade entry price
- `exit_price` - Trade exit price
- `quantity` - Number of shares
- `entry_time` - Timestamp of trade entry
- `exit_time` - Timestamp of trade exit
- `profit_loss` - Calculated P&L
- `profit_loss_percent` - P&L percentage
- `status` - OPEN, CLOSED, CANCELLED

### Signals Table
- `id` - Primary key
- `symbol` - Stock symbol
- `signal_type` - BUY or SELL
- `confidence_score` - 0-1 confidence
- `current_price` - Price when signal generated
- `timestamp` - Signal timestamp
- `strategy_details` - JSON of contributing strategies
- `acted_upon` - Whether a trade was created
- `trade_id` - Link to associated trade

### Strategy Performance Table
- `id` - Primary key
- `strategy_name` - Name of strategy
- `symbol` - Stock symbol
- `total_signals` - Total signals generated
- `winning_signals` - Number of winning signals
- `losing_signals` - Number of losing signals
- `win_rate` - Percentage win rate
- `avg_profit` - Average profit per signal
- `avg_loss` - Average loss per signal

## Configuration

Edit `backend/config.py` to customize:

```python
# Strategy parameters
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

# Confidence threshold for generating signals
CONFIDENCE_THRESHOLD = 0.60

# Check interval (seconds)
CHECK_INTERVAL = 60
```

## Monitoring & Logging

All activities are logged to stdout. Set log level in `.env`:

```
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

View logs:

```bash
# Docker
docker-compose logs -f backend

# Local
tail -f logs/app.log
```

## Security Notes

⚠️ **IMPORTANT**:
1. Never commit `.env` file with real API keys
2. Use Paper Trading first (`https://paper-api.alpaca.markets`)
3. Always test with small positions
4. Implement proper risk management (stop-loss, position sizing)
5. This is a decision-support tool, not a guaranteed profit machine
6. No strategy has 100% success rate

## Troubleshooting

### Database Connection Error
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Reset database
docker-compose down -v
docker-compose up -d
```

### API Connection Error
```bash
# Check backend logs
docker-compose logs backend

# Verify API keys in .env
cat .env | grep ALPACA
```

### Frontend Not Loading
```bash
# Clear npm cache
cd frontend
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
npm start
```

## Performance Tips

1. **Reduce Symbol Count**: Monitor fewer symbols for better performance
2. **Increase Check Interval**: Reduce signal generation frequency
3. **Optimize Database**: Index frequently queried columns
4. **Use Paper Trading**: Test before using real money
5. **Monitor Resource Usage**: Check CPU/Memory during peak hours

## Deployment to Cloud

### AWS Deployment
```bash
# Using AWS ECS with Docker images
# 1. Push images to ECR
# 2. Create ECS task definitions
# 3. Deploy with RDS PostgreSQL
```

### Heroku Deployment
```bash
# Deploy backend
git push heroku main
```

### DigitalOcean App Platform
```bash
# Deploy using doctl CLI
doctl apps create --spec app.yaml
```

## Support & Contributing

For issues, questions, or contributions:
1. Check existing GitHub issues
2. Create detailed issue reports
3. Submit pull requests with improvements

## License

MIT License - See LICENSE file

## Disclaimer

This bot is for educational purposes. Trading stocks involves risk. Past performance does not guarantee future results. Always do your own research and consult with a financial advisor before trading with real money.
