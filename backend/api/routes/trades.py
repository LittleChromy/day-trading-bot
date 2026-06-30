from flask import Blueprint, jsonify, request, current_app
from datetime import datetime
from models import db, Trade, Signal
import logging

logger = logging.getLogger(__name__)

trades_bp = Blueprint('trades', __name__)

@trades_bp.route('/create', methods=['POST'])
def create_trade():
    """
    Create a new trade
    POST body: {
        "symbol": "AAPL",
        "trade_type": "BUY",
        "entry_price": 150.50,
        "quantity": 10,
        "signal_id": 1
    }
    """
    try:
        data = request.get_json()
        
        new_trade = Trade(
            symbol=data['symbol'],
            trade_type=data['trade_type'],  # BUY or SELL
            entry_price=float(data['entry_price']),
            quantity=int(data['quantity']),
            entry_time=datetime.utcnow(),
            status='OPEN'
        )
        
        db.session.add(new_trade)
        db.session.flush()  # Get the ID without committing
        
        # Link to signal if provided
        if 'signal_id' in data:
            signal = Signal.query.get(data['signal_id'])
            if signal:
                signal.trade_id = new_trade.id
                signal.acted_upon = True
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'trade_id': new_trade.id,
            'message': 'Trade created successfully'
        }), 201
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating trade: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@trades_bp.route('/close/<int:trade_id>', methods=['PUT'])
def close_trade(trade_id):
    """
    Close an open trade
    PUT body: {"exit_price": 151.75}
    """
    try:
        trade = Trade.query.get(trade_id)
        if not trade:
            return jsonify({'status': 'error', 'message': 'Trade not found'}), 404
        
        if trade.status != 'OPEN':
            return jsonify({'status': 'error', 'message': 'Trade is not open'}), 400
        
        data = request.get_json()
        trade.exit_price = float(data['exit_price'])
        trade.exit_time = datetime.utcnow()
        trade.status = 'CLOSED'
        trade.calculate_pnl()
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'trade_id': trade.id,
            'profit_loss': trade.profit_loss,
            'profit_loss_percent': trade.profit_loss_percent,
            'message': 'Trade closed successfully'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error closing trade: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@trades_bp.route('/all', methods=['GET'])
def get_all_trades():
    """
    Get all trades with optional filters
    Query params: status=OPEN, symbol=AAPL, limit=50
    """
    try:
        query = Trade.query
        
        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status)
        
        symbol = request.args.get('symbol')
        if symbol:
            query = query.filter_by(symbol=symbol)
        
        limit = request.args.get('limit', 50, type=int)
        trades = query.order_by(Trade.entry_time.desc()).limit(limit).all()
        
        trades_data = []
        for trade in trades:
            trades_data.append({
                'id': trade.id,
                'symbol': trade.symbol,
                'type': trade.trade_type,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'quantity': trade.quantity,
                'entry_time': trade.entry_time.isoformat(),
                'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
                'profit_loss': trade.profit_loss,
                'profit_loss_percent': trade.profit_loss_percent,
                'status': trade.status
            })
        
        return jsonify({
            'status': 'success',
            'trades': trades_data,
            'count': len(trades_data)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching trades: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@trades_bp.route('/<int:trade_id>', methods=['GET'])
def get_trade(trade_id):
    """
    Get a specific trade by ID
    """
    try:
        trade = Trade.query.get(trade_id)
        if not trade:
            return jsonify({'status': 'error', 'message': 'Trade not found'}), 404
        
        return jsonify({
            'status': 'success',
            'trade': {
                'id': trade.id,
                'symbol': trade.symbol,
                'type': trade.trade_type,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'quantity': trade.quantity,
                'entry_time': trade.entry_time.isoformat(),
                'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
                'profit_loss': trade.profit_loss,
                'profit_loss_percent': trade.profit_loss_percent,
                'status': trade.status,
                'notes': trade.notes
            }
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching trade: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
