from flask import Blueprint, jsonify, request, current_app
from datetime import datetime, timedelta
from models import db, Signal, Trade, StrategyPerformance
import logging
import json

logger = logging.getLogger(__name__)

signals_bp = Blueprint('signals', __name__)

@signals_bp.route('/generate', methods=['POST'])
def generate_signals():
    """
    Generate trading signals for specified symbols
    POST body: {"symbols": ["AAPL", "MSFT"]}
    """
    try:
        data = request.get_json()
        symbols = data.get('symbols', current_app.config['STOCK_SYMBOLS'])
        
        signals_generated = []
        
        for symbol in symbols:
            # Get latest bars data
            bars = current_app.data_handler.get_bars(symbol, timeframe='5min', limit=100)
            
            if bars is None or bars.empty:
                logger.warning(f"No data for {symbol}")
                continue
            
            # Analyze with strategy engine
            signal_type, confidence, strategy_details = current_app.strategy_engine.analyze(symbol, bars)
            
            if signal_type and confidence >= current_app.config['CONFIDENCE_THRESHOLD']:
                current_price = bars['close'].iloc[-1]
                
                # Save signal to database
                new_signal = Signal(
                    symbol=symbol,
                    signal_type=signal_type,
                    confidence_score=confidence,
                    current_price=current_price,
                    timestamp=datetime.utcnow(),
                    strategy_details=json.dumps(strategy_details)
                )
                db.session.add(new_signal)
                
                signals_generated.append({
                    'symbol': symbol,
                    'signal': signal_type,
                    'confidence': round(confidence, 3),
                    'price': current_price,
                    'timestamp': new_signal.timestamp.isoformat(),
                    'strategies': strategy_details
                })
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'signals': signals_generated,
            'count': len(signals_generated)
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating signals: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@signals_bp.route('/recent', methods=['GET'])
def get_recent_signals():
    """
    Get recent signals from the last N hours
    Query params: hours=24 (default)
    """
    try:
        hours = request.args.get('hours', 24, type=int)
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        signals = Signal.query.filter(
            Signal.timestamp >= cutoff_time
        ).order_by(Signal.timestamp.desc()).all()
        
        signals_data = []
        for signal in signals:
            signals_data.append({
                'id': signal.id,
                'symbol': signal.symbol,
                'signal': signal.signal_type,
                'confidence': signal.confidence_score,
                'price': signal.current_price,
                'timestamp': signal.timestamp.isoformat(),
                'acted_upon': signal.acted_upon,
                'strategies': signal.get_strategy_details()
            })
        
        return jsonify({
            'status': 'success',
            'signals': signals_data,
            'count': len(signals_data)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching recent signals: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@signals_bp.route('/by-symbol/<symbol>', methods=['GET'])
def get_signals_by_symbol(symbol):
    """
    Get all signals for a specific symbol
    """
    try:
        signals = Signal.query.filter_by(symbol=symbol).order_by(Signal.timestamp.desc()).all()
        
        signals_data = []
        for signal in signals:
            signals_data.append({
                'id': signal.id,
                'signal': signal.signal_type,
                'confidence': signal.confidence_score,
                'price': signal.current_price,
                'timestamp': signal.timestamp.isoformat(),
                'acted_upon': signal.acted_upon
            })
        
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'signals': signals_data,
            'count': len(signals_data)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching signals for {symbol}: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
