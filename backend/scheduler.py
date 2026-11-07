"""
Background jobs: the bot cycle (positions + signals + auto-trading), a faster
position monitor, and periodic ML retraining.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


class SignalScheduler:
    def __init__(self, app):
        self.app = app
        self.scheduler = BackgroundScheduler(daemon=True, job_defaults={'coalesce': True, 'max_instances': 1})

    def _bot_cycle(self):
        with self.app.app_context():
            summary = self.app.trading_bot.run_cycle(generate=True)
            logger.info(f"Bot cycle: {summary}")

    def _monitor(self):
        with self.app.app_context():
            self.app.trading_bot.run_cycle(generate=False)

    def _retrain(self):
        with self.app.app_context():
            from ml_trainer import MLTrainer
            logger.info("Retraining ML models...")
            result = MLTrainer(self.app.config.get('MODEL_PATH')).train_all()
            logger.info(f"Retraining result: {result}")
            predictor = getattr(self.app, 'signal_predictor', None)
            if predictor is not None:
                predictor.reload()

    def start(self):
        cfg = self.app.config
        self.scheduler.add_job(self._bot_cycle, 'interval', seconds=cfg['SIGNAL_INTERVAL'], id='bot_cycle')
        if cfg['CHECK_INTERVAL'] < cfg['SIGNAL_INTERVAL']:
            self.scheduler.add_job(self._monitor, 'interval', seconds=cfg['CHECK_INTERVAL'], id='monitor')
        self.scheduler.add_job(self._retrain, 'interval', hours=cfg['RETRAIN_INTERVAL_HOURS'], id='retrain')
        self.scheduler.start()
        logger.info(f"Scheduler started: bot cycle every {cfg['SIGNAL_INTERVAL']}s, "
                    f"position checks every {cfg['CHECK_INTERVAL']}s, "
                    f"retraining every {cfg['RETRAIN_INTERVAL_HOURS']}h")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
