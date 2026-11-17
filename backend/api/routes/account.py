"""Your own settings: risk limits, starting capital, Discord, account reset"""
import json
import logging
import re

from flask import Blueprint, jsonify, request, current_app

from auth import current_user
from models import db, Trade, BotEvent, USER_SETTING_LIMITS, USER_FLAGS

logger = logging.getLogger(__name__)

account_bp = Blueprint('account', __name__)

# Only real Discord webhooks: the server POSTs to this URL, so it must not be
# usable to make the server call arbitrary addresses.
DISCORD_WEBHOOK_RE = re.compile(
    r'^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$')
MIN_CAPITAL, MAX_CAPITAL = 1_000, 10_000_000


def _bad(message, status=400):
    return jsonify({'status': 'error', 'message': message}), status


def _settings_payload(user):
    cfg = current_app.config
    effective = user.settings(cfg)
    limits = {k: list(v) for k, v in USER_SETTING_LIMITS.items()}
    # Signals below the server-wide threshold are never stored, so a user can only be stricter
    limits['CONFIDENCE_THRESHOLD'][0] = max(limits['CONFIDENCE_THRESHOLD'][0], cfg['CONFIDENCE_THRESHOLD'])
    return {
        'settings': {k: effective[k] for k in list(USER_SETTING_LIMITS) + list(USER_FLAGS)},
        'defaults': {k: cfg.get(k) for k in list(USER_SETTING_LIMITS) + list(USER_FLAGS)},
        'limits': limits,
        'starting_capital': user.starting_capital,
        'capital_limits': [MIN_CAPITAL, MAX_CAPITAL],
        'discord_configured': bool(user.discord_webhook_url),
        'server_wide': {k: cfg.get(k) for k in ('ALLOW_SHORTING', 'FLATTEN_AT_CLOSE')},
        'alpaca_account': current_app.trading_bot.mode_for(user) == 'alpaca',
    }


@account_bp.route('/settings', methods=['GET'])
def get_settings():
    return jsonify({'status': 'success', **_settings_payload(current_user())}), 200


@account_bp.route('/settings', methods=['PUT'])
def update_settings():
    """
    PUT any of: {"settings": {"STOP_LOSS_PCT": 1.0, ...}, "starting_capital": 50000,
                 "discord_webhook_url": "https://discord.com/api/webhooks/..." | ""}
    Send null for a setting to go back to the server default.
    """
    user = current_user()
    data = request.get_json(silent=True) or {}
    payload = _settings_payload(user)
    overrides = user.overrides()

    for key, value in (data.get('settings') or {}).items():
        if key in USER_FLAGS:
            if value is None:
                overrides.pop(key, None)
            else:
                overrides[key] = bool(value)
            continue
        if key not in USER_SETTING_LIMITS:
            return _bad(f'Unknown setting {key}')
        if value is None:
            overrides.pop(key, None)
            continue
        low, high = payload['limits'][key]
        try:
            number = int(value) if key == 'MAX_OPEN_POSITIONS' else float(value)
        except (TypeError, ValueError):
            return _bad(f'{key} must be a number')
        if not low <= number <= high:
            return _bad(f'{key} must be between {low} and {high}')
        overrides[key] = number

    if 'starting_capital' in data:
        try:
            capital = float(data['starting_capital'])
        except (TypeError, ValueError):
            return _bad('starting_capital must be a number')
        if not MIN_CAPITAL <= capital <= MAX_CAPITAL:
            return _bad(f'starting_capital must be between {MIN_CAPITAL:,} and {MAX_CAPITAL:,}')
        if user.is_admin and current_app.trading_bot.mode_for(user) == 'alpaca':
            return _bad('Your equity comes from Alpaca; starting capital only applies to simulated accounts')
        user.starting_capital = capital

    if 'discord_webhook_url' in data:
        url = (data['discord_webhook_url'] or '').strip()
        if url and not DISCORD_WEBHOOK_RE.match(url):
            return _bad('That is not a Discord webhook link (it should start with https://discord.com/api/webhooks/)')
        user.discord_webhook_url = url or None

    user.settings_json = json.dumps(overrides)
    db.session.commit()
    return jsonify({'status': 'success', **_settings_payload(user)}), 200


@account_bp.route('/reset', methods=['POST'])
def reset_account():
    """
    Start your simulated account over: deletes your trades and activity log.
    POST {"confirm": "RESET"}. Not available for accounts trading through Alpaca.
    """
    user = current_user()
    data = request.get_json(silent=True) or {}
    if data.get('confirm') != 'RESET':
        return _bad('Send {"confirm": "RESET"} to confirm')
    if current_app.trading_bot.mode_for(user) == 'alpaca':
        return _bad('This account trades through Alpaca; it cannot be reset here')
    if Trade.query.filter_by(user_id=user.id, status='OPEN').count():
        return _bad('Close your open positions first (Bot tab → Flatten all)')
    deleted = Trade.query.filter_by(user_id=user.id).delete()
    BotEvent.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    logger.info(f"{user.username} reset their account ({deleted} trades removed)")
    return jsonify({'status': 'success', 'deleted_trades': deleted}), 200
