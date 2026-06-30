# Day Trading Bot

An AI-powered day trading strategy analyzer with real-time alerts, performance tracking, and machine learning capabilities.

## Features

- **Real-time Market Data**: Integrates with Alpaca API for live stock prices
- **Multiple Trading Strategies**: Technical indicators (RSI, MACD, Bollinger Bands, Moving Averages, Stochastic, Volume-based, Momentum, Mean Reversion)
- **Strategy Scoring**: Combines signals from multiple strategies into a confidence score
- **Trade Tracking**: Monitor buy/sell signals and track actual trades
- **Performance Analytics**: Visualize strategy performance and win rates
- **Self-Learning ML Models**: Learns from your trading results over time
- **Paper Trading**: Test strategies with virtual money before risking real capital
- **Real-time Alerts**: Get notified when buy/sell signals are generated

## Tech Stack

- **Backend**: Python (Flask/FastAPI, Pandas, NumPy, scikit-learn, TensorFlow)
- **Frontend**: React
- **Database**: PostgreSQL (for trade history, performance data, ML model training)
- **Data Source**: Alpaca API (real-time market data)
- **Hosting**: AWS/Cloud (configurable)

## Project Structure

```
day-trading-bot/
├── backend/
│   ├── config/
│   ├── strategies/
│   ├── models/
│   ├── data/
│   ├── api/
│   ├── utils/
│   ├── requirements.txt
│   └── main.py
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── database/
│   └── migrations/
└── docker-compose.yml
```

## Getting Started

1. Clone the repository
2. Set up Alpaca API keys
3. Install dependencies
4. Configure database
5. Run backend and frontend servers
6. Access dashboard at `http://localhost:3000`

## Warning

This is a decision-support tool, not a guaranteed money printer. No trading strategy has a 100% success rate. Always use proper risk management and never trade with money you can't afford to lose.
