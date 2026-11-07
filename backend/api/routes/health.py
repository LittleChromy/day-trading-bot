from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
import logging

from models import db

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__)


@health_bp.route('/status', methods=['GET'])
def health_status():
    """Health check: API, database and Alpaca configuration"""
    db_ok = True
    try:
        db.session.execute(text('SELECT 1'))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_ok = False
    return jsonify({
        'status': 'healthy' if db_ok else 'degraded',
        'service': 'day-trading-bot-api',
        'version': '1.1.0',
        'database': 'ok' if db_ok else 'error',
        'alpaca_configured': current_app.data_handler.configured,
        'execution_mode': current_app.config.get('EXECUTION_MODE'),
        'auto_trade': current_app.trading_bot.auto_trade,
    }), 200 if db_ok else 503
