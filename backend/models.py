from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from datetime import datetime
import json
import logging
import secrets

from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

db = SQLAlchemy()


def _iso(value):
    return value.isoformat() if value else None


# Per-user risk settings: key -> (min, max). Values outside the range are rejected.
USER_SETTING_LIMITS = {
    'CONFIDENCE_THRESHOLD': (0.5, 0.95),
    'RISK_PER_TRADE_PCT': (0.1, 5.0),
    'MAX_POSITION_PCT': (1.0, 100.0),
    'STOP_LOSS_PCT': (0.2, 10.0),
    'TAKE_PROFIT_PCT': (0.2, 20.0),
    'MAX_OPEN_POSITIONS': (1, 20),
    'MAX_DAILY_LOSS_PCT': (0.5, 20.0),
}
USER_FLAGS = ('NOTIFY_SIGNALS', 'NOTIFY_TRADES')


class User(db.Model):
    """A login. Each user has their own simulated account, trades and settings."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), nullable=False, default='user')  # 'admin' or 'user'
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    token_version = db.Column(db.Integer, nullable=False, default=0)  # bump to log out everywhere
    auto_trade = db.Column(db.Boolean, nullable=False, default=False)
    starting_capital = db.Column(db.Float, nullable=False, default=100000.0)
    settings_json = db.Column(db.Text, nullable=True)        # overrides of USER_SETTING_LIMITS keys
    discord_webhook_url = db.Column(db.Text, nullable=True)

    @property
    def is_admin(self):
        return self.role == 'admin'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.token_version = (self.token_version or 0) + 1

    def check_password(self, password):
        return bool(password) and check_password_hash(self.password_hash, password)

    def overrides(self):
        try:
            data = json.loads(self.settings_json or '{}')
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def settings(self, cfg):
        """Effective settings: the server defaults with this user's overrides on top"""
        merged = {k: cfg.get(k) for k in list(USER_SETTING_LIMITS) + list(USER_FLAGS)}
        merged.update({k: v for k, v in self.overrides().items() if k in merged})
        for key in ('ALLOW_SHORTING', 'FLATTEN_AT_CLOSE', 'FLATTEN_MINUTES_BEFORE_CLOSE'):
            merged[key] = cfg.get(key)  # server-wide only
        merged['STARTING_CAPITAL'] = self.starting_capital
        return merged

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'is_active': bool(self.is_active),
            'created_at': _iso(self.created_at),
            'last_login': _iso(self.last_login),
            'auto_trade': bool(self.auto_trade),
            'starting_capital': self.starting_capital,
            'discord_configured': bool(self.discord_webhook_url),
        }


class AppSetting(db.Model):
    """Small key/value store for server state that must survive restarts"""
    __tablename__ = 'app_settings'

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text, nullable=True)

    @staticmethod
    def get(key, default=None):
        row = db.session.get(AppSetting, key)
        return row.value if row is not None else default

    @staticmethod
    def put(key, value):
        row = db.session.get(AppSetting, key)
        if row is None:
            db.session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
        db.session.commit()

    @staticmethod
    def secret_key():
        """A random signing key generated once and kept in the database"""
        value = AppSetting.get('secret_key')
        if not value:
            value = secrets.token_hex(32)
            AppSetting.put('secret_key', value)
        return value


class Trade(db.Model):
    """Records of trades (manual, simulated or sent to the broker)"""
    __tablename__ = 'trades'

    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    trade_type = db.Column(db.String(10), nullable=False)  # 'BUY' (long) or 'SELL' (short)
    entry_price = db.Column(db.Float, nullable=False)
    exit_price = db.Column(db.Float, nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    entry_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    exit_time = db.Column(db.DateTime, nullable=True)
    profit_loss = db.Column(db.Float, nullable=True)
    profit_loss_percent = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='OPEN')  # OPEN, CLOSED, CANCELLED
    notes = db.Column(db.Text, nullable=True)
    # Risk management / execution metadata
    stop_loss = db.Column(db.Float, nullable=True)
    take_profit = db.Column(db.Float, nullable=True)
    source = db.Column(db.String(20), nullable=True, default='MANUAL')  # MANUAL, BOT
    execution_mode = db.Column(db.String(20), nullable=True)  # simulated, alpaca, manual
    broker_order_id = db.Column(db.String(64), nullable=True)
    exit_reason = db.Column(db.String(30), nullable=True)  # STOP_LOSS, TAKE_PROFIT, EOD, MANUAL, SIGNAL
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    signal_id = db.Column(db.Integer, nullable=True, index=True)  # signals.id (no FK: signals.trade_id points back)

    def calculate_pnl(self):
        """Calculate profit/loss for closed trades"""
        if self.exit_price is not None and self.status == 'CLOSED':
            if self.trade_type == 'BUY':
                diff = self.exit_price - self.entry_price
            else:
                diff = self.entry_price - self.exit_price
            self.profit_loss = round(diff * self.quantity, 2)
            self.profit_loss_percent = round(diff / self.entry_price * 100, 4) if self.entry_price else 0.0

    def unrealized_pnl(self, current_price):
        if current_price is None:
            return None
        diff = (current_price - self.entry_price) if self.trade_type == 'BUY' else (self.entry_price - current_price)
        return round(diff * self.quantity, 2)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'type': self.trade_type,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'quantity': self.quantity,
            'entry_time': _iso(self.entry_time),
            'exit_time': _iso(self.exit_time),
            'profit_loss': self.profit_loss,
            'profit_loss_percent': self.profit_loss_percent,
            'status': self.status,
            'notes': self.notes,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'source': self.source,
            'execution_mode': self.execution_mode,
            'broker_order_id': self.broker_order_id,
            'exit_reason': self.exit_reason,
            'user_id': self.user_id,
            'signal_id': self.signal_id,
        }


class Signal(db.Model):
    """Trading signals generated by strategies"""
    __tablename__ = 'signals'

    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), nullable=False, index=True)
    signal_type = db.Column(db.String(10), nullable=False)  # 'BUY' or 'SELL'
    confidence_score = db.Column(db.Float, nullable=False)  # 0-1 (after ML adjustment)
    base_confidence = db.Column(db.Float, nullable=True)    # 0-1 (strategy agreement only)
    current_price = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    strategy_details = db.Column(db.Text, nullable=True)  # JSON string of contributing strategies
    acted_upon = db.Column(db.Boolean, default=False)
    trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'), nullable=True)

    def get_strategy_details(self):
        """Parse strategy details JSON (tolerates legacy non-JSON rows)"""
        if not self.strategy_details:
            return {}
        try:
            return json.loads(self.strategy_details)
        except (ValueError, TypeError):
            return {}

    def to_dict(self, trade_id=None):
        """trade_id: the viewing user's trade opened from this signal, if any"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'signal': self.signal_type,
            'confidence': self.confidence_score,
            'base_confidence': self.base_confidence,
            'price': self.current_price,
            'timestamp': _iso(self.timestamp),
            'acted_upon': trade_id is not None,
            'trade_id': trade_id,
            'strategies': self.get_strategy_details(),
        }


class StrategyPerformance(db.Model):
    """Tracks performance of individual strategies"""
    __tablename__ = 'strategy_performance'

    id = db.Column(db.Integer, primary_key=True)
    strategy_name = db.Column(db.String(50), nullable=False, index=True)
    symbol = db.Column(db.String(10), nullable=False)
    total_signals = db.Column(db.Integer, default=0)
    winning_signals = db.Column(db.Integer, default=0)
    losing_signals = db.Column(db.Integer, default=0)
    win_rate = db.Column(db.Float, default=0.0)  # percentage
    avg_profit = db.Column(db.Float, default=0.0)
    avg_loss = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def calculate_win_rate(self):
        total = (self.winning_signals or 0) + (self.losing_signals or 0)
        self.win_rate = (self.winning_signals / total) * 100 if total > 0 else 0.0


class MLModel(db.Model):
    """Stores ML model metadata and versions"""
    __tablename__ = 'ml_models'

    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(100), nullable=False)
    model_type = db.Column(db.String(50), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    accuracy = db.Column(db.Float, nullable=True)
    training_samples = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_retrained = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    model_path = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'model_name': self.model_name,
            'model_type': self.model_type,
            'version': self.version,
            'accuracy': self.accuracy,
            'training_samples': self.training_samples,
            'created_at': _iso(self.created_at),
            'is_active': bool(self.is_active),
        }


class BotEvent(db.Model):
    """Audit log of everything the automated bot does"""
    __tablename__ = 'bot_events'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    level = db.Column(db.String(10), nullable=False, default='INFO')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)  # None = system
    event_type = db.Column(db.String(30), nullable=False)
    symbol = db.Column(db.String(10), nullable=True)
    message = db.Column(db.Text, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': _iso(self.timestamp),
            'level': self.level,
            'event_type': self.event_type,
            'symbol': self.symbol,
            'message': self.message,
            'user_id': self.user_id,
        }


def ensure_schema():
    """
    Create tables and add any columns introduced after a database was first created.
    db.create_all() never alters existing tables, so older Postgres volumes would
    otherwise be missing the new nullable columns.
    """
    db.create_all()
    inspector = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col['name'] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing or not column.nullable:
                continue
            col_type = column.type.compile(dialect=db.engine.dialect)
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}'))
            logger.info(f"Added missing column {table.name}.{column.name}")


def assign_legacy_data(admin):
    """
    Data created before accounts existed belongs to the first admin.
    Also links old trades to their signal (signals.trade_id was the pre-account link).
    """
    db.session.execute(text('UPDATE trades SET signal_id = (SELECT s.id FROM signals s WHERE s.trade_id = trades.id) '
                            'WHERE signal_id IS NULL AND EXISTS (SELECT 1 FROM signals s WHERE s.trade_id = trades.id)'))
    Trade.query.filter(Trade.user_id.is_(None)).update({'user_id': admin.id}, synchronize_session=False)
    BotEvent.query.filter(BotEvent.user_id.is_(None), BotEvent.event_type.in_(('ENTRY', 'EXIT', 'CANCELLED'))) \
        .update({'user_id': admin.id}, synchronize_session=False)
    db.session.commit()
