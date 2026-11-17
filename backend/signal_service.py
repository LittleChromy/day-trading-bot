"""
Signal generation shared by the API, the scheduler and the trading bot.
"""
import json
import logging
from datetime import datetime, timedelta

from models import db, Signal, StrategyPerformance, User

logger = logging.getLogger(__name__)


def _predictor(app):
    if not app.config.get('USE_ML_ADJUSTMENT', True):
        return None
    predictor = getattr(app, 'signal_predictor', None)
    if predictor is None:
        try:
            from ml_trainer import SignalPredictor
            predictor = SignalPredictor(app.config.get('MODEL_PATH'))
        except Exception as e:
            logger.warning(f"ML predictor unavailable: {e}")
            return None
        app.signal_predictor = predictor
    return predictor if predictor.has_models else None


def generate_signals(app, symbols=None):
    """
    Analyze each symbol and persist a Signal when confidence clears the threshold.
    With no symbols given, uses the scanner's picks (or the fixed watchlist).
    A symbol that already produced the same signal within SIGNAL_COOLDOWN_MINUTES
    is skipped so the scheduler does not spam duplicates.
    Must be called inside an app context. Returns the list of new Signal rows.
    """
    cfg = app.config
    if not symbols:
        scanner = getattr(app, 'scanner', None)
        symbols = scanner.symbols() if scanner is not None else cfg['STOCK_SYMBOLS']
    symbols = [s.strip().upper() for s in symbols if s and s.strip()]
    threshold = cfg['CONFIDENCE_THRESHOLD']
    cooldown = timedelta(minutes=cfg.get('SIGNAL_COOLDOWN_MINUTES', 30))
    predictor = _predictor(app)
    created = []
    no_data = []

    for symbol in symbols:
        bars = app.data_handler.get_bars(symbol, cfg.get('BAR_TIMEFRAME'), cfg.get('BAR_LIMIT'))
        if bars is None or bars.empty:
            logger.info(f"No bar data for {symbol}")
            no_data.append(symbol)
            continue

        signal_type, base_conf, details = app.strategy_engine.analyze(symbol, bars)
        if not signal_type:
            continue

        price = float(bars['close'].iloc[-1])
        confidence = base_conf
        if predictor is not None:
            confidence = predictor.predict_signal_quality(details, base_conf, signal_type, price)

        if confidence < threshold:
            continue

        recent = Signal.query.filter(
            Signal.symbol == symbol,
            Signal.signal_type == signal_type,
            Signal.timestamp >= datetime.utcnow() - cooldown,
        ).first()
        if recent:
            continue

        signal = Signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence_score=round(float(confidence), 4),
            base_confidence=round(float(base_conf), 4),
            current_price=price,
            timestamp=datetime.utcnow(),
            strategy_details=json.dumps(details),
        )
        db.session.add(signal)
        created.append(signal)

    db.session.commit()
    app.last_scan = {'symbols': symbols, 'no_data': no_data, 'time': datetime.utcnow().isoformat()}
    if symbols and len(no_data) == len(symbols):
        logger.warning("No market data for any symbol - check the Alpaca API keys and the backend log")
    if created:
        logger.info(f"Generated {len(created)} signal(s): "
                    + ', '.join(f"{s.signal_type} {s.symbol} ({s.confidence_score:.0%})" for s in created))
        _notify_signals(app, created)
    return created


def _notify_signals(app, signals):
    """Post new signals to the server-wide Discord channel and to every user's own webhook"""
    notifiers = []
    seen = set()
    server = getattr(app, 'notifier', None)
    if server is not None and server.enabled:
        notifiers.append(server)
        seen.add(server.webhook_url)
    bot = getattr(app, 'trading_bot', None)
    if bot is not None:
        for user in User.query.filter(User.is_active.is_(True), User.discord_webhook_url.isnot(None)).all():
            notifier = bot.notifier_for(user)
            if notifier is not None and notifier.enabled and notifier.webhook_url not in seen:
                seen.add(notifier.webhook_url)
                notifiers.append(notifier)
    for notifier in notifiers:
        for signal in signals:
            try:
                notifier.signal(signal)
            except Exception as e:
                logger.warning(f"Signal notification failed: {e}")


def trades_by_signal(signal_ids, user):
    """{signal_id: trade_id} for the signals this user has traded"""
    from models import Trade
    if not signal_ids:
        return {}
    rows = Trade.query.with_entities(Trade.signal_id, Trade.id) \
        .filter(Trade.user_id == user.id, Trade.signal_id.in_(list(signal_ids))).all()
    return {signal_id: trade_id for signal_id, trade_id in rows}


def record_trade_outcome(trade):
    """
    After a trade closes, credit/debit every strategy that voted with the signal
    that opened it. Feeds the per-strategy analytics.
    """
    signal = db.session.get(Signal, trade.signal_id) if trade.signal_id else None
    if not signal or trade.profit_loss is None:
        return
    won = trade.profit_loss > 0
    for name, info in signal.get_strategy_details().items():
        if not isinstance(info, dict) or info.get('signal') != signal.signal_type:
            continue
        perf = StrategyPerformance.query.filter_by(strategy_name=name, symbol=trade.symbol).first()
        if perf is None:
            perf = StrategyPerformance(strategy_name=name, symbol=trade.symbol, total_signals=0,
                                       winning_signals=0, losing_signals=0, avg_profit=0.0, avg_loss=0.0)
            db.session.add(perf)
        perf.total_signals = (perf.total_signals or 0) + 1
        if won:
            n = perf.winning_signals or 0
            perf.avg_profit = ((perf.avg_profit or 0) * n + trade.profit_loss) / (n + 1)
            perf.winning_signals = n + 1
        else:
            n = perf.losing_signals or 0
            perf.avg_loss = ((perf.avg_loss or 0) * n + trade.profit_loss) / (n + 1)
            perf.losing_signals = n + 1
        perf.calculate_win_rate()
        perf.last_updated = datetime.utcnow()
