"""
Access control for a shared dashboard.

Reading (GET) is open so the page can be shared as view-only. Anything that
changes state - toggling auto-trading, opening/closing trades, scanning,
retraining - needs control access:

  * ADMIN_PASSWORD set   -> the request must carry it in the X-Admin-Token header
  * ADMIN_PASSWORD unset -> only requests made to localhost are allowed, so a
                            visitor arriving through a shared link can look but
                            not touch
"""
import hmac
import logging
import time

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}
# Non-GET endpoints that change nothing and are safe for viewers
OPEN_ENDPOINTS = {'backtest.run', 'auth.unlock'}
MIN_PASSWORD_LENGTH = 8


def _password():
    return (current_app.config.get('ADMIN_PASSWORD') or '').strip()


def _is_local_request():
    host = (request.host or '').rsplit(':', 1)[0].strip('[]').lower()
    # Tunnels and reverse proxies announce the public name they were reached by
    forwarded = (request.headers.get('X-Forwarded-Host') or '').split(',')[0].strip()
    forwarded = forwarded.rsplit(':', 1)[0].strip('[]').lower()
    return host in LOCAL_HOSTS and (not forwarded or forwarded in LOCAL_HOSTS)


def _token_valid(token):
    password = _password()
    return bool(password) and hmac.compare_digest(str(token or '').encode(), password.encode())


def has_control():
    """True when this request may change things"""
    if _password():
        return _token_valid(request.headers.get('X-Admin-Token'))
    return _is_local_request()


def require_control():
    """before_request hook: block state-changing calls from viewers"""
    if request.method in ('GET', 'HEAD', 'OPTIONS') or request.endpoint in OPEN_ENDPOINTS:
        return None
    if has_control():
        return None
    if _password():
        return jsonify({'status': 'error', 'code': 'locked',
                        'message': 'View-only. Unlock with the admin password to make changes.'}), 401
    return jsonify({'status': 'error', 'code': 'view_only',
                    'message': 'This shared view is read-only. Controls work only on the computer running the bot '
                               '(or set ADMIN_PASSWORD to unlock them remotely).'}), 403


@auth_bp.route('/status', methods=['GET'])
def status():
    """Whether a password is configured and whether this request has control access"""
    return jsonify({'status': 'success', 'password_set': bool(_password()), 'control': has_control()}), 200


@auth_bp.route('/unlock', methods=['POST'])
def unlock():
    """Check a password. POST body: {"password": "..."}"""
    if not _password():
        return jsonify({'status': 'error', 'message': 'No ADMIN_PASSWORD is configured on the server'}), 400
    data = request.get_json(silent=True) or {}
    if _token_valid(data.get('password')):
        return jsonify({'status': 'success'}), 200
    time.sleep(1)  # slow down guessing
    logger.warning("Failed admin unlock attempt")
    return jsonify({'status': 'error', 'message': 'Wrong password'}), 401


def init_auth(app):
    app.before_request(require_control)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    password = (app.config.get('ADMIN_PASSWORD') or '').strip()
    if password and len(password) < MIN_PASSWORD_LENGTH:
        logger.warning(f"ADMIN_PASSWORD is shorter than {MIN_PASSWORD_LENGTH} characters; use a longer one "
                       "before sharing the dashboard")
    elif not password:
        logger.info("No ADMIN_PASSWORD set: controls work only from this computer; shared links are view-only")
