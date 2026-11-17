import logging

from flask import Blueprint, jsonify, request, current_app

from auth import admin_required, current_user
from models import db, BotEvent, MLModel, User
from trading_engine import TradingError

logger = logging.getLogger(__name__)

bot_bp = Blueprint('bot', __name__)


@bot_bp.route('/status', methods=['GET'])
def status():
    """Your bot: auto-trading switch, mode, open positions, your risk settings"""
    try:
        return jsonify({'status': 'success', 'bot': current_app.trading_bot.status(current_user())}), 200
    except Exception as e:
        logger.error(f"Error fetching bot status: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/account', methods=['GET'])
def account():
    """Your account: equity, buying power, today's P&L"""
    try:
        return jsonify({'status': 'success',
                        'account': current_app.trading_bot.account_snapshot(current_user())}), 200
    except Exception as e:
        logger.error(f"Error fetching account: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/auto-trade', methods=['POST'])
def set_auto_trade():
    """
    Turn automated trading on/off for your account. POST body: {"enabled": true}
    Saved in the database, so it survives restarts.
    """
    data = request.get_json(silent=True) or {}
    if 'enabled' not in data:
        return jsonify({'status': 'error', 'message': "Body must include 'enabled'"}), 400
    bot = current_app.trading_bot
    user = current_user()
    enabled = bool(data['enabled'])
    if enabled:
        try:
            bot.validate_mode(user)
        except TradingError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
    user.auto_trade = enabled
    db.session.commit()
    bot.log_event('CONFIG', f"Auto-trading {'enabled' if enabled else 'disabled'}", user=user)
    notifier = bot.notifier_for(user)
    if notifier is not None:
        notifier.info(f"Auto-trading **{'enabled' if enabled else 'disabled'}** for {user.username} "
                      f"({bot.mode_for(user)} mode)")
    return jsonify({'status': 'success', 'auto_trade': user.auto_trade}), 200


@bot_bp.route('/run', methods=['POST'])
@admin_required
def run_cycle():
    """Run one bot cycle now for everyone (monitor positions, scan, auto-trade)"""
    try:
        summary = current_app.trading_bot.run_cycle(generate=current_app.data_handler.configured)
        return jsonify({'status': 'success', 'summary': summary}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error running bot cycle: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/flatten', methods=['POST'])
def flatten():
    """Close every open position in your account immediately"""
    try:
        closed = current_app.trading_bot.flatten_all(reason='MANUAL_FLATTEN', user=current_user())
        return jsonify({'status': 'success', 'closed': [t.to_dict() for t in closed]}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_bp.route('/events', methods=['GET'])
def events():
    """Your activity log. Admins also see system events and can pass ?all=1 for everyone's."""
    user = current_user()
    limit = min(request.args.get('limit', 50, type=int), 500)
    query = BotEvent.query
    if user.is_admin:
        if request.args.get('all') != '1':
            query = query.filter((BotEvent.user_id == user.id) | BotEvent.user_id.is_(None))
    else:
        query = query.filter(BotEvent.user_id == user.id)
    rows = query.order_by(BotEvent.timestamp.desc(), BotEvent.id.desc()).limit(limit).all()
    names = {u.id: u.username for u in User.query.all()} if user.is_admin else {}
    result = []
    for event in rows:
        item = event.to_dict()
        if user.is_admin:
            item['username'] = names.get(event.user_id)
        result.append(item)
    return jsonify({'status': 'success', 'events': result}), 200


@bot_bp.route('/retrain', methods=['POST'])
@admin_required
def retrain():
    """Retrain the ML models from everyone's closed trades now"""
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


@bot_bp.route('/universe', methods=['GET'])
def universe():
    """Symbols the bot is analyzing"""
    scanner = current_app.scanner
    return jsonify({'status': 'success', 'symbols': scanner.symbols(), 'scanner': scanner.status()}), 200


@bot_bp.route('/universe', methods=['POST'])
@admin_required
def rescan():
    """Re-run the stock scanner now"""
    scanner = current_app.scanner
    return jsonify({'status': 'success', 'symbols': scanner.symbols(force=True), 'scanner': scanner.status()}), 200


@bot_bp.route('/notify-test', methods=['POST'])
def notify_test():
    """Send a test message to your Discord webhook (or the server's, for the admin)"""
    notifier = current_app.trading_bot.notifier_for(current_user())
    if notifier is None or not notifier.enabled:
        return jsonify({'status': 'error',
                        'message': 'No Discord webhook set. Add one in the Settings tab.'}), 400
    ok = notifier.send_now('🔔 **Test notification** from your Day Trading Bot. Notifications are working.')
    if ok:
        return jsonify({'status': 'success', 'message': 'Test message sent to Discord'}), 200
    return jsonify({'status': 'error', 'message': notifier.last_error or 'Notification failed'}), 400
