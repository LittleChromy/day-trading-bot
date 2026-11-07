import logging
import os

from flask import Flask, jsonify
from flask_cors import CORS

from config import config
from data_handler import AlpacaDataHandler
from models import db, ensure_schema
from strategies import StrategyEngine
from trading_engine import TradingBot

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'),
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)


def create_app(config_name=None, data_handler=None, start_scheduler=None):
    """
    Application factory.
    data_handler can be injected (tests use a fake market data source).
    start_scheduler defaults to the ENABLE_SCHEDULER setting.
    """
    config_name = config_name or os.getenv('FLASK_ENV', 'development')
    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    db.init_app(app)
    CORS(app)

    with app.app_context():
        ensure_schema()
        logger.info("Database initialized")

    app.data_handler = data_handler or AlpacaDataHandler()
    app.strategy_engine = StrategyEngine(min_agreeing=app.config['MIN_AGREEING_STRATEGIES'])
    app.trading_bot = TradingBot(app)

    if not app.data_handler.configured:
        logger.warning("Alpaca API keys are not set: market data, signals and Alpaca execution are unavailable")

    from api.routes import signals_bp, trades_bp, analytics_bp, health_bp, bot_bp, backtest_bp
    app.register_blueprint(signals_bp, url_prefix='/api/signals')
    app.register_blueprint(trades_bp, url_prefix='/api/trades')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(health_bp, url_prefix='/api/health')
    app.register_blueprint(bot_bp, url_prefix='/api/bot')
    app.register_blueprint(backtest_bp, url_prefix='/api/backtest')

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({'status': 'error', 'message': 'Not found'}), 404

    if start_scheduler is None:
        start_scheduler = app.config.get('ENABLE_SCHEDULER', True)
    if start_scheduler:
        from scheduler import SignalScheduler
        app.scheduler = SignalScheduler(app)
        app.scheduler.start()

    return app


# Production: gunicorn --workers 1 --threads 8 'app:create_app()'
# Keep a single worker so only one scheduler/bot instance runs.
if __name__ == '__main__':
    create_app().run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
