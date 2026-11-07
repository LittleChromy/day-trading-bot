from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from models import db, Trade, Signal, StrategyPerformance
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
    """Share of acted-upon signals whose trade closed in profit (open trades are excluded)"""
    try:
        rows = (db.session.query(Signal, Trade)
                .join(Trade, Signal.trade_id == Trade.id)
                .filter(Signal.acted_upon.is_(True), Trade.status == 'CLOSED')
                .all())
        total = len(rows)
        accurate = sum(1 for _, t in rows if (t.profit_loss or 0) > 0)
        by_type = {}
        for signal, trade in rows:
            bucket = by_type.setdefault(signal.signal_type, {'total': 0, 'accurate': 0})
            bucket['total'] += 1
            bucket['accurate'] += 1 if (trade.profit_loss or 0) > 0 else 0
        return jsonify({
            'status': 'success',
            'accuracy_metrics': {
                'total_signals': total,
                'accurate_signals': accurate,
                'accuracy_rate': round(accurate / total * 100, 2) if total else 0,
                'by_type': by_type,
                'total_generated': Signal.query.count(),
            }
        }), 200
    except Exception as e:
        logger.error(f"Error calculating signal accuracy: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@analytics_bp.route('/strategies', methods=['GET'])
def get_strategy_performance():
    """Win rate of each individual strategy, aggregated across symbols"""
    try:
        agg = {}
        for p in StrategyPerformance.query.all():
            a = agg.setdefault(p.strategy_name, {'wins': 0, 'losses': 0, 'profit': 0.0, 'loss': 0.0})
            a['wins'] += p.winning_signals or 0
            a['losses'] += p.losing_signals or 0
            a['profit'] += (p.avg_profit or 0) * (p.winning_signals or 0)
            a['loss'] += (p.avg_loss or 0) * (p.losing_signals or 0)
        result = []
        for name, a in agg.items():
            total = a['wins'] + a['losses']
            result.append({
                'strategy': name,
                'total_signals': total,
                'winning_signals': a['wins'],
                'losing_signals': a['losses'],
                'win_rate': round(a['wins'] / total * 100, 2) if total else 0,
                'net_pnl': round(a['profit'] + a['loss'], 2),
            })
        result.sort(key=lambda r: r['win_rate'], reverse=True)
        return jsonify({'status': 'success', 'strategies': result}), 200
    except Exception as e:
        logger.error(f"Error fetching strategy performance: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@analytics_bp.route('/equity-curve', methods=['GET'])
def get_equity_curve():
    """Cumulative realized P&L over time. Query params: days=30"""
    try:
        days = request.args.get('days', 30, type=int)
        cutoff = datetime.utcnow() - timedelta(days=days)
        trades = (Trade.query.filter(Trade.status == 'CLOSED', Trade.exit_time >= cutoff)
                  .order_by(Trade.exit_time.asc()).all())
        running = 0.0
        points = []
        for t in trades:
            running += t.profit_loss or 0
            points.append({'time': t.exit_time.isoformat(), 'cumulative_pnl': round(running, 2),
                           'trade_id': t.id, 'symbol': t.symbol})
        return jsonify({'status': 'success', 'points': points}), 200
    except Exception as e:
        logger.error(f"Error building equity curve: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
