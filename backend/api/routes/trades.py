from datetime import datetime
import logging

from flask import Blueprint, jsonify, request, current_app

from models import db, Trade, Signal
from signal_service import record_trade_outcome
from trading_engine import TradingError

logger = logging.getLogger(__name__)

trades_bp = Blueprint('trades', __name__)

VALID_TYPES = ('BUY', 'SELL')
VALID_STATUSES = ('OPEN', 'CLOSED', 'CANCELLED')


def _bad(message, code=400):
    return jsonify({'status': 'error', 'message': message}), code


@trades_bp.route('/create', methods=['POST'])
def create_trade():
    """
    Record a trade you placed yourself (journal entry, no order is sent).
    POST body: {"symbol": "AAPL", "trade_type": "BUY", "entry_price": 150.5,
                "quantity": 10, "signal_id": 1, "stop_loss": 148, "take_profit": 155, "notes": "..."}
    """
    data = request.get_json(silent=True) or {}
    try:
        symbol = str(data['symbol']).strip().upper()
        trade_type = str(data['trade_type']).strip().upper()
        entry_price = float(data['entry_price'])
        quantity = int(data['quantity'])
    except (KeyError, TypeError, ValueError):
        return _bad('symbol, trade_type, entry_price and quantity are required')
    if not symbol or len(symbol) > 10:
        return _bad('Invalid symbol')
    if trade_type not in VALID_TYPES:
        return _bad("trade_type must be 'BUY' or 'SELL'")
    if entry_price <= 0 or quantity <= 0:
        return _bad('entry_price and quantity must be positive')

    try:
        trade = Trade(
            symbol=symbol,
            trade_type=trade_type,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=datetime.utcnow(),
            status='OPEN',
            stop_loss=float(data['stop_loss']) if data.get('stop_loss') else None,
            take_profit=float(data['take_profit']) if data.get('take_profit') else None,
            source='MANUAL',
            execution_mode='manual',
            notes=data.get('notes'),
        )
        db.session.add(trade)
        db.session.flush()

        if data.get('signal_id'):
            signal = db.session.get(Signal, int(data['signal_id']))
            if signal and not signal.acted_upon:
                signal.trade_id = trade.id
                signal.acted_upon = True

        db.session.commit()
        return jsonify({'status': 'success', 'trade_id': trade.id, 'trade': trade.to_dict(),
                        'message': 'Trade created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating trade: {e}")
        return _bad(str(e), 500)


@trades_bp.route('/close/<int:trade_id>', methods=['PUT'])
def close_trade(trade_id):
    """
    Close an open trade.
    PUT body: {"exit_price": 151.75}  -- omit exit_price to close at the latest market price
    Bot trades in alpaca mode are flattened at the broker.
    """
    trade = db.session.get(Trade, trade_id)
    if not trade:
        return _bad('Trade not found', 404)
    if trade.status != 'OPEN':
        return _bad('Trade is not open')

    data = request.get_json(silent=True) or {}
    exit_price = data.get('exit_price')
    try:
        if exit_price is not None:
            exit_price = float(exit_price)
            if exit_price <= 0:
                return _bad('exit_price must be positive')

        if trade.execution_mode in ('simulated', 'alpaca'):
            current_app.trading_bot.close_trade(trade, exit_price, reason='MANUAL')
        else:
            if exit_price is None:
                return _bad('exit_price is required for manually recorded trades')
            trade.exit_price = exit_price
            trade.exit_time = datetime.utcnow()
            trade.status = 'CLOSED'
            trade.exit_reason = 'MANUAL'
            trade.calculate_pnl()
            record_trade_outcome(trade)
            db.session.commit()

        return jsonify({
            'status': 'success',
            'trade_id': trade.id,
            'profit_loss': trade.profit_loss,
            'profit_loss_percent': trade.profit_loss_percent,
            'trade': trade.to_dict(),
            'message': 'Trade closed successfully',
        }), 200
    except (TradingError, ValueError) as e:
        db.session.rollback()
        return _bad(str(e))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error closing trade: {e}")
        return _bad(str(e), 500)


@trades_bp.route('/cancel/<int:trade_id>', methods=['PUT'])
def cancel_trade(trade_id):
    """Mark an open journal trade as cancelled (e.g. entered by mistake)"""
    trade = db.session.get(Trade, trade_id)
    if not trade:
        return _bad('Trade not found', 404)
    if trade.status != 'OPEN':
        return _bad('Trade is not open')
    if trade.execution_mode == 'alpaca':
        return _bad('Broker trades must be closed, not cancelled')
    trade.status = 'CANCELLED'
    trade.exit_time = datetime.utcnow()
    trade.exit_reason = 'CANCELLED'
    db.session.commit()
    return jsonify({'status': 'success', 'trade': trade.to_dict()}), 200


@trades_bp.route('/all', methods=['GET'])
def get_all_trades():
    """Query params: status=OPEN, symbol=AAPL, limit=50. Open trades include live unrealized P&L."""
    try:
        query = Trade.query
        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status.upper())
        symbol = request.args.get('symbol')
        if symbol:
            query = query.filter_by(symbol=symbol.upper())
        limit = min(request.args.get('limit', 50, type=int), 500)
        trades = query.order_by(Trade.entry_time.desc()).limit(limit).all()

        include_live = request.args.get('live', 'true').lower() != 'false'
        data_handler = current_app.data_handler
        result = []
        for trade in trades:
            item = trade.to_dict()
            if include_live and trade.status == 'OPEN' and data_handler.configured:
                price = data_handler.get_latest_price(trade.symbol)
                item['current_price'] = price
                item['unrealized_pnl'] = trade.unrealized_pnl(price)
            result.append(item)

        return jsonify({'status': 'success', 'trades': result, 'count': len(result)}), 200
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return _bad(str(e), 500)


@trades_bp.route('/<int:trade_id>', methods=['GET'])
def get_trade(trade_id):
    trade = db.session.get(Trade, trade_id)
    if not trade:
        return _bad('Trade not found', 404)
    return jsonify({'status': 'success', 'trade': trade.to_dict()}), 200
