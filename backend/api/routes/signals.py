from datetime import datetime, timedelta
import logging

from flask import Blueprint, jsonify, request, current_app

from models import db, Signal
from signal_service import generate_signals
from trading_engine import TradingError

logger = logging.getLogger(__name__)

signals_bp = Blueprint('signals', __name__)


@signals_bp.route('/generate', methods=['POST'])
def generate():
    """
    Scan symbols and store new signals.
    POST body (optional): {"symbols": ["AAPL", "MSFT"]}
    """
    try:
        if not current_app.data_handler.configured:
            return jsonify({'status': 'error',
                            'message': 'Alpaca API keys are not configured; cannot fetch market data'}), 503
        data = request.get_json(silent=True) or {}
        symbols = data.get('symbols')  # omitted -> scanner picks / watchlist
        if isinstance(symbols, str):
            symbols = symbols.split(',')
        created = generate_signals(current_app, symbols)
        scan = getattr(current_app, 'last_scan', {})
        return jsonify({
            'status': 'success',
            'signals': [s.to_dict() for s in created],
            'count': len(created),
            'scanned': len(scan.get('symbols', [])),
            'no_data': scan.get('no_data', []),
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating signals: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@signals_bp.route('/recent', methods=['GET'])
def get_recent_signals():
    """Signals from the last N hours. Query params: hours=24"""
    try:
        hours = request.args.get('hours', 24, type=int)
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        signals = Signal.query.filter(Signal.timestamp >= cutoff).order_by(Signal.timestamp.desc()).all()
        return jsonify({
            'status': 'success',
            'signals': [s.to_dict() for s in signals],
            'count': len(signals),
        }), 200
    except Exception as e:
        logger.error(f"Error fetching recent signals: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@signals_bp.route('/by-symbol/<symbol>', methods=['GET'])
def get_signals_by_symbol(symbol):
    try:
        symbol = symbol.upper()
        signals = Signal.query.filter_by(symbol=symbol).order_by(Signal.timestamp.desc()).limit(200).all()
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'signals': [s.to_dict() for s in signals],
            'count': len(signals),
        }), 200
    except Exception as e:
        logger.error(f"Error fetching signals for {symbol}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@signals_bp.route('/<int:signal_id>/execute', methods=['POST'])
def execute_signal(signal_id):
    """
    Open a trade from a signal using the bot's risk rules and execution mode.
    POST body (optional): {"quantity": 10}  -- omit to use risk-based sizing
    """
    signal = db.session.get(Signal, signal_id)
    if signal is None:
        return jsonify({'status': 'error', 'message': 'Signal not found'}), 404
    data = request.get_json(silent=True) or {}
    quantity = data.get('quantity')
    try:
        if quantity is not None and int(quantity) <= 0:
            return jsonify({'status': 'error', 'message': 'quantity must be a positive integer'}), 400
        trade = current_app.trading_bot.execute_signal(
            signal, quantity=quantity, source='MANUAL',
            enforce_market_hours=current_app.trading_bot.mode == 'alpaca')
        return jsonify({'status': 'success', 'trade': trade.to_dict()}), 201
    except (TradingError, ValueError) as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error executing signal {signal_id}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
