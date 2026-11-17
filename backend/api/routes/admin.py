"""Admin only: manage accounts and see how everyone's bot is doing"""
import logging

from flask import Blueprint, jsonify, request, current_app

from auth import (AuthError, admin_count, admin_required, create_user, current_user,
                  signup_allowed, validate_password)
from models import db, AppSetting, BotEvent, Trade, User

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


def _bad(message, status=400):
    return jsonify({'status': 'error', 'message': message}), status


def _user_summary(user, prices):
    bot = current_app.trading_bot
    closed = Trade.query.filter_by(user_id=user.id, status='CLOSED').all()
    wins = sum(1 for t in closed if (t.profit_loss or 0) > 0)
    try:
        account = bot.account_snapshot(user, prices)
    except Exception as e:  # an Alpaca hiccup must not break the whole list
        logger.warning(f"Account snapshot failed for {user.username}: {e}")
        account = {}
    return {
        **user.to_dict(),
        'execution_mode': bot.mode_for(user),
        'equity': account.get('equity'),
        'daily_pnl': account.get('daily_pnl'),
        'total_pnl': round(sum(t.profit_loss or 0 for t in closed), 2),
        'closed_trades': len(closed),
        'win_rate': round(wins / len(closed) * 100, 1) if closed else None,
        'open_positions': Trade.query.filter_by(user_id=user.id, status='OPEN').count(),
    }


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    prices = {}  # share price lookups across accounts
    users = User.query.order_by(User.role.asc(), User.created_at.asc()).all()
    return jsonify({
        'status': 'success',
        'users': [_user_summary(u, prices) for u in users],
        'signup_allowed': signup_allowed(),
    }), 200


@admin_bp.route('/users', methods=['POST'])
@admin_required
def add_user():
    """POST {"username", "password", "role": "user"|"admin"}"""
    data = request.get_json(silent=True) or {}
    try:
        user = create_user(data.get('username'), data.get('password'), role=data.get('role') or 'user')
    except AuthError as e:
        return _bad(str(e), e.status)
    logger.info(f"{current_user().username} created account {user.username} ({user.role})")
    return jsonify({'status': 'success', 'user': user.to_dict()}), 201


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """
    PUT any of: {"role": "admin"|"user", "is_active": bool, "password": "new password", "auto_trade": bool}
    Changing the password or disabling logs that user out everywhere.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return _bad('User not found', 404)
    data = request.get_json(silent=True) or {}
    me = current_user()
    bot = current_app.trading_bot

    if 'role' in data:
        role = data['role']
        if role not in ('admin', 'user'):
            return _bad("role must be 'admin' or 'user'")
        if user.is_admin and role == 'user' and admin_count() <= 1:
            return _bad('There must always be at least one admin')
        if role == 'user' and user.is_admin and Trade.query.filter_by(user_id=user.id, status='OPEN',
                                                                          execution_mode='alpaca').count():
            return _bad('Close this account\'s Alpaca positions before removing admin')
        user.role = role
    if 'is_active' in data:
        active = bool(data['is_active'])
        if not active and user.id == me.id:
            return _bad('You cannot disable your own account')
        if not active and user.is_admin and admin_count() <= 1:
            return _bad('There must always be at least one admin')
        if not active:
            user.auto_trade = False
            user.token_version = (user.token_version or 0) + 1
        user.is_active = active
    if data.get('password'):
        try:
            user.set_password(validate_password(data['password']))
        except AuthError as e:
            return _bad(str(e), e.status)
    if 'auto_trade' in data:
        if data['auto_trade'] and not user.is_active:
            return _bad('Enable the account first')
        user.auto_trade = bool(data['auto_trade'])
    db.session.commit()
    bot.log_event('CONFIG', f"Account {user.username} updated by {me.username}: "
                            + ', '.join(k for k in ('role', 'is_active', 'password', 'auto_trade') if k in data))
    return jsonify({'status': 'success', 'user': _user_summary(user, {})}), 200


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete an account together with its trades and activity log"""
    user = db.session.get(User, user_id)
    if user is None:
        return _bad('User not found', 404)
    if user.id == current_user().id:
        return _bad('You cannot delete your own account')
    if user.is_admin and admin_count() <= 1:
        return _bad('There must always be at least one admin')
    if Trade.query.filter_by(user_id=user.id, status='OPEN', execution_mode='alpaca').count():
        return _bad('This account has open Alpaca positions; close them first')
    Trade.query.filter_by(user_id=user.id).delete()
    BotEvent.query.filter_by(user_id=user.id).delete()
    username = user.username
    db.session.delete(user)
    db.session.commit()
    logger.info(f"{current_user().username} deleted account {username}")
    return jsonify({'status': 'success'}), 200


@admin_bp.route('/signup', methods=['PUT'])
@admin_required
def set_signup():
    """PUT {"allowed": bool} - whether anyone with the link can create an account"""
    data = request.get_json(silent=True) or {}
    if 'allowed' not in data:
        return _bad("Body must include 'allowed'")
    AppSetting.put('allow_signup', '1' if data['allowed'] else '0')
    return jsonify({'status': 'success', 'signup_allowed': signup_allowed()}), 200
