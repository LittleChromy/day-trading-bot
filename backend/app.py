import logging
from flask import Flask
from config import config
from models import db
from data_handler import AlpacaDataHandler
from strategies import StrategyEngine
from scheduler import SignalScheduler
import threading
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_name='development'):
    """
    Application factory with scheduling support
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        logger.info("Database initialized")
    
    # Initialize components
    app.data_handler = AlpacaDataHandler()
    app.strategy_engine = StrategyEngine()
    
    # Register blueprints
    from api.routes.signals import signals_bp
    from api.routes.trades import trades_bp
    from api.routes.analytics import analytics_bp
    from api.routes.health import health_bp
    
    app.register_blueprint(signals_bp, url_prefix='/api/signals')
    app.register_blueprint(trades_bp, url_prefix='/api/trades')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(health_bp, url_prefix='/api/health')
    
    # Setup scheduler
    scheduler = SignalScheduler(app)
    scheduler.schedule_signal_generation(interval_seconds=300)  # 5 minutes
    scheduler.schedule_model_retraining(interval_hours=24)  # 24 hours
    
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=scheduler.run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Scheduler started in background")
    
    return app

if __name__ == '__main__':
    app = create_app(os.getenv('FLASK_ENV', 'development'))
    app.run(debug=True, host='0.0.0.0', port=5000)
