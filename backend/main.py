from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import logging
from datetime import datetime
import os
from config import config
from models import db, Trade, Signal, StrategyPerformance, MLModel
from data_handler import AlpacaDataHandler
from strategies import StrategyEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_name='development'):
    """Application factory"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    CORS(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Initialize data handler and strategy engine
    app.data_handler = AlpacaDataHandler()
    app.strategy_engine = StrategyEngine()
    
    # Register blueprints
    from api.routes import signals_bp, trades_bp, analytics_bp, health_bp
    app.register_blueprint(signals_bp, url_prefix='/api/signals')
    app.register_blueprint(trades_bp, url_prefix='/api/trades')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(health_bp, url_prefix='/api/health')
    
    return app

if __name__ == '__main__':
    app = create_app(os.getenv('FLASK_ENV', 'development'))
    app.run(debug=True, host='0.0.0.0', port=5000)
