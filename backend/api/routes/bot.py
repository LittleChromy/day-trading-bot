import logging

from flask import Blueprint, jsonify, request, current_app

from models import db, BotEvent, MLModel
from trading_engine import TradingError

logger = logging.getLogger(__name__)

bot_bp = Blueprint('bot', __name__)


@bot_bp.route('/status', methods=['GET'])
def status():
    try:
        return jsonify({'status': 'success', 'bot': current_app.trading_bot.status()}), 200
    except Exception as e:
        logger.error(f"Error fetching bot status: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/account', methods=['GET'])
def account():
    try:
        return jsonify({'status': 'success', 'account': current_app.trading_bot.account_snapshot()}), 200
    except Exception as e:
        logger.error(f"Error fetching account: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/auto-trade', methods=['POST'])
def set_auto_trade():
    """
    Turn automated trading on/off at runtime.
    POST body: {"enabled": true}
    The setting resets to AUTO_TRADE from the environment when the server restarts.
    """
    data = request.get_json(silent=True) or {}
    if 'enabled' not in data:
        return jsonify({'status': 'error', 'message': "Body must include 'enabled'"}), 400
    bot = current_app.trading_bot
    enabled = bool(data['enabled'])
    if enabled:
        try:
            bot.validate_mode()
        except TradingError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
    bot.auto_trade = enabled
    bot.log_event('CONFIG', f"Auto-trading {'enabled' if enabled else 'disabled'} via API")
    return jsonify({'status': 'success', 'auto_trade': bot.auto_trade}), 200


@bot_bp.route('/run', methods=['POST'])
def run_cycle():
    """Run one bot cycle now (monitor positions, scan, auto-trade if enabled)"""
    try:
        summary = current_app.trading_bot.run_cycle(generate=current_app.data_handler.configured)
        return jsonify({'status': 'success', 'summary': summary}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error running bot cycle: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/flatten', methods=['POST'])
def flatten():
    """Close every open bot-managed position immediately"""
    try:
        closed = current_app.trading_bot.flatten_all(reason='MANUAL_FLATTEN')
        return jsonify({'status': 'success', 'closed': [t.to_dict() for t in closed]}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/events', methods=['GET'])
def events():
    limit = min(request.args.get('limit', 50, type=int), 500)
    rows = BotEvent.query.order_by(BotEvent.timestamp.desc(), BotEvent.id.desc()).limit(limit).all()
    return jsonify({'status': 'success', 'events': [e.to_dict() for e in rows]}), 200


@bot_bp.route('/retrain', methods=['POST'])
def retrain():
    """Retrain the ML models from closed trades now"""
    try:
        from ml_trainer import MLTrainer
        result = MLTrainer(current_app.config.get('MODEL_PATH')).train_all()
        predictor = getattr(current_app, 'signal_predictor', None)
        if predictor is not None:
            predictor.reload()
        return jsonify({'status': 'success', 'trained': result}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Retraining failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/models', methods=['GET'])
def models():
    rows = MLModel.query.order_by(MLModel.created_at.desc()).limit(20).all()
    return jsonify({'status': 'success', 'models': [m.to_dict() for m in rows]}), 200
