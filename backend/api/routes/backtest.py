from datetime import datetime, timedelta, timezone
import logging

from flask import Blueprint, jsonify, request, current_app

from backtester import run_backtest
from strategies import StrategyEngine

logger = logging.getLogger(__name__)

backtest_bp = Blueprint('backtest', __name__)

RISK_KEYS = ('STARTING_CAPITAL', 'CONFIDENCE_THRESHOLD', 'ALLOW_SHORTING', 'STOP_LOSS_PCT',
             'TAKE_PROFIT_PCT', 'RISK_PER_TRADE_PCT', 'MAX_POSITION_PCT')


@backtest_bp.route('/run', methods=['POST'])
def run():
    """
    Backtest the strategy engine on historical Alpaca bars.
    POST body: {
      "symbol": "AAPL", "days": 30, "timeframe": "5Min",
      "overrides": {"STOP_LOSS_PCT": 1.0, "TAKE_PROFIT_PCT": 2.0, "CONFIDENCE_THRESHOLD": 0.65}
    }
    """
    data = request.get_json(silent=True) or {}
    symbol = str(data.get('symbol') or '').strip().upper()
    if not symbol:
        return jsonify({'status': 'error', 'message': 'symbol is required'}), 400
    days = max(1, min(int(data.get('days', 30)), 365))
    timeframe = data.get('timeframe') or current_app.config['BAR_TIMEFRAME']

    if not current_app.data_handler.configured:
        return jsonify({'status': 'error', 'message': 'Alpaca API keys are not configured'}), 503

    settings = {k: current_app.config.get(k) for k in RISK_KEYS}
    for key, value in (data.get('overrides') or {}).items():
        key = key.upper()
        if key in RISK_KEYS:
            settings[key] = value

    end = datetime.now(timezone.utc) - timedelta(minutes=16)  # free data plans lag 15 minutes
    bars = current_app.data_handler.get_historical_bars(symbol, timeframe, end - timedelta(days=days), end)
    if bars is None or bars.empty:
        return jsonify({'status': 'error', 'message': f'No historical data for {symbol}'}), 404

    try:
        engine = StrategyEngine(min_agreeing=current_app.config['MIN_AGREEING_STRATEGIES'])
        result = run_backtest(bars, settings, engine=engine, symbol=symbol)
        result['settings'] = settings
        result['timeframe'] = timeframe
        return jsonify({'status': 'success', 'backtest': result}), 200
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"Backtest failed for {symbol}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
