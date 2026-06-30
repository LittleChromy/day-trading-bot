from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from models import Trade, Signal, StrategyPerformance
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/performance', methods=['GET'])
def get_performance():
    """
    Get overall trading performance metrics
    Query params: days=7 (default)
    """
    try:
        days = request.args.get('days', 7, type=int)
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        closed_trades = Trade.query.filter(
            Trade.status == 'CLOSED',
            Trade.exit_time >= cutoff_time
        ).all()
        
        if not closed_trades:
            return jsonify({
                'status': 'success',
                'metrics': {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0,
                    'total_profit_loss': 0,
                    'avg_profit': 0,
                    'avg_loss': 0,
                    'max_profit': 0,
                    'max_loss': 0
                }
            }), 200
        
        total_trades = len(closed_trades)
        winning_trades = sum(1 for t in closed_trades if t.profit_loss and t.profit_loss > 0)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = sum(t.profit_loss for t in closed_trades if t.profit_loss)
        
        profits = [t.profit_loss for t in closed_trades if t.profit_loss and t.profit_loss > 0]
        losses = [t.profit_loss for t in closed_trades if t.profit_loss and t.profit_loss < 0]
        
        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        max_profit = max(profits) if profits else 0
        max_loss = min(losses) if losses else 0
        
        return jsonify({
            'status': 'success',
            'metrics': {
                'period_days': days,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
                'total_profit_loss': round(total_pnl, 2),
                'avg_profit': round(avg_profit, 2),
                'avg_loss': round(avg_loss, 2),
                'max_profit': round(max_profit, 2),
                'max_loss': round(max_loss, 2)
            }
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching performance metrics: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@analytics_bp.route('/by-symbol', methods=['GET'])
def get_performance_by_symbol():
    """
    Get performance metrics by symbol
    """
    try:
        closed_trades = Trade.query.filter(Trade.status == 'CLOSED').all()
        
        symbol_stats = {}
        for trade in closed_trades:
            if trade.symbol not in symbol_stats:
                symbol_stats[trade.symbol] = {
                    'total': 0,
                    'wins': 0,
                    'losses': 0,
                    'pnl': 0
                }
            
            symbol_stats[trade.symbol]['total'] += 1
            symbol_stats[trade.symbol]['pnl'] += trade.profit_loss if trade.profit_loss else 0
            
            if trade.profit_loss and trade.profit_loss > 0:
                symbol_stats[trade.symbol]['wins'] += 1
            else:
                symbol_stats[trade.symbol]['losses'] += 1
        
        result = []
        for symbol, stats in symbol_stats.items():
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            result.append({
                'symbol': symbol,
                'total_trades': stats['total'],
                'winning_trades': stats['wins'],
                'losing_trades': stats['losses'],
                'win_rate': round(win_rate, 2),
                'total_pnl': round(stats['pnl'], 2)
            })
        
        result.sort(key=lambda x: x['total_pnl'], reverse=True)
        
        return jsonify({
            'status': 'success',
            'by_symbol': result
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching symbol performance: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@analytics_bp.route('/signal-accuracy', methods=['GET'])
def get_signal_accuracy():
    """
    Get signal accuracy metrics
    """
    try:
        acted_signals = Signal.query.filter(Signal.acted_upon == True).all()
        
        if not acted_signals:
            return jsonify({
                'status': 'success',
                'accuracy_metrics': {
                    'total_signals': 0,
                    'accurate_signals': 0,
                    'accuracy_rate': 0
                }
            }), 200
        
        total_signals = len(acted_signals)
        accurate_signals = 0
        
        for signal in acted_signals:
            if signal.trade_id:
                trade = Trade.query.get(signal.trade_id)
                if trade and trade.status == 'CLOSED' and trade.profit_loss and trade.profit_loss > 0:
                    accurate_signals += 1
        
        accuracy_rate = (accurate_signals / total_signals * 100) if total_signals > 0 else 0
        
        return jsonify({
            'status': 'success',
            'accuracy_metrics': {
                'total_signals': total_signals,
                'accurate_signals': accurate_signals,
                'accuracy_rate': round(accuracy_rate, 2)
            }
        }), 200
    
    except Exception as e:
        logger.error(f"Error calculating signal accuracy: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
