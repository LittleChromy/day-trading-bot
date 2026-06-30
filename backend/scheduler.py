import schedule
import time
import logging
from datetime import datetime
from ml_trainer import MLTrainer
from config import Config
from flask import current_app

logger = logging.getLogger(__name__)

class SignalScheduler:
    """
    Scheduler for continuous signal generation and model retraining
    """
    
    def __init__(self, app=None):
        self.app = app
        self.trainer = MLTrainer()
    
    def schedule_signal_generation(self, interval_seconds=300):
        """
        Schedule periodic signal generation
        Default: every 5 minutes
        """
        schedule.every(interval_seconds).seconds.do(
            self.generate_signals_job
        )
        logger.info(f"Scheduled signal generation every {interval_seconds} seconds")
    
    def schedule_model_retraining(self, interval_hours=24):
        """
        Schedule periodic model retraining
        Default: every 24 hours
        """
        schedule.every(interval_hours).hours.do(
            self.retrain_models_job
        )
        logger.info(f"Scheduled model retraining every {interval_hours} hours")
    
    def generate_signals_job(self):
        """
        Generate trading signals for all configured symbols
        """
        try:
            with self.app.app_context():
                logger.info("Generating trading signals...")
                
                symbols = Config.STOCK_SYMBOLS
                generated_count = 0
                
                for symbol in symbols:
                    bars = self.app.data_handler.get_bars(symbol, timeframe='5min', limit=100)
                    
                    if bars is None or bars.empty:
                        continue
                    
                    signal_type, confidence, strategy_details = self.app.strategy_engine.analyze(symbol, bars)
                    
                    if signal_type and confidence >= Config.CONFIDENCE_THRESHOLD:
                        from models import Signal
                        current_price = bars['close'].iloc[-1]
                        
                        new_signal = Signal(
                            symbol=symbol,
                            signal_type=signal_type,
                            confidence_score=confidence,
                            current_price=current_price,
                            timestamp=datetime.utcnow(),
                            strategy_details=str(strategy_details)
                        )
                        from models import db
                        db.session.add(new_signal)
                        generated_count += 1
                
                from models import db
                db.session.commit()
                logger.info(f"Generated {generated_count} signals")
        
        except Exception as e:
            logger.error(f"Error in signal generation job: {str(e)}")
    
    def retrain_models_job(self):
        """
        Retrain ML models with new trading data
        """
        try:
            logger.info("Starting model retraining...")
            
            with self.app.app_context():
                # Train both models
                rf_model = self.trainer.train_random_forest()
                if rf_model:
                    logger.info("Random Forest model retrained successfully")
                
                nn_model = self.trainer.train_neural_network()
                if nn_model:
                    logger.info("Neural Network model retrained successfully")
        
        except Exception as e:
            logger.error(f"Error in model retraining job: {str(e)}")
    
    def run_scheduler(self):
        """
        Run the scheduler in a loop
        Should be run in a separate thread
        """
        logger.info("Starting scheduler")
        while True:
            schedule.run_pending()
            time.sleep(10)  # Check schedule every 10 seconds
