"""
Accounts and login.

* Every API call except the health check, login and sign-up needs a logged-in
  user (``Authorization: Bearer <token>``).
* Two roles: ``admin`` manages users and the shared bot (scanner, retraining,
  forced cycles); ``user`` trades their own simulated account.
* Tokens are signed with a key stored in the database, carry the user's
  ``token_version`` (bumped on password change / disable) and expire after
  TOKEN_DAYS.

The first admin comes from ADMIN_USERNAME / ADMIN_PASSWORD in .env. Without
those, the first account created from the bot's own computer becomes admin.
"""
import logging
import re
import threading
import time
from datetime import datetime
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from models import db, AppSetting, User, assign_legacy_data

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

TOKEN_DAYS = 30
MIN_PASSWORD_LENGTH = 8
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,30}$')
PUBLIC_ENDPOINTS = {'health.health_status', 'auth.login', 'auth.register', 'auth.config', 'static'}
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}

# Login throttling: (client, username) -> recent failure timestamps
_FAILURES = {}
_FAILURE_LOCK = threading.Lock()
MAX_FAILURES = 8
FAILURE_WINDOW = 15 * 60


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- helpers
def _bad(message, status=400, code=None):
    body = {'status': 'error', 'message': message}
    if code:
        body['code'] = code
    return jsonify(body), status


def _serializer():
    return URLSafeTimedSerializer(current_app.config['AUTH_SECRET'], salt='dtb-auth')


def issue_token(user):
    return _serializer().dumps({'u': user.id, 'v': user.token_version or 0})


def _user_from_token(token):
    try:
        data = _serializer().loads(token, max_age=TOKEN_DAYS * 86400)
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get('u'))
    if user is None or not user.is_active or (user.token_version or 0) != data.get('v'):
        return None
    return user


def _client_id():
    # Behind the Cloudflare tunnel every request arrives from the same container,
    # so prefer the visitor address Cloudflare reports.
    return (request.headers.get('CF-Connecting-IP') or request.headers.get('X-Real-IP')
            or request.remote_addr or '?')


def is_local_request():
    """Request made on the bot's own computer (not through a tunnel or proxy hostname)"""
    if request.headers.get('CF-Connecting-IP') or request.headers.get('CF-Ray'):
        return False
    host = (request.host or '').rsplit(':', 1)[0].strip('[]').lower()
    forwarded = (request.headers.get('X-Forwarded-Host') or '').split(',')[0].strip()
    forwarded = forwarded.rsplit(':', 1)[0].strip('[]').lower()
    return host in LOCAL_HOSTS and (not forwarded or forwarded in LOCAL_HOSTS)


def validate_username(username):
    username = (username or '').strip()
    if not USERNAME_RE.match(username):
        raise AuthError('Username must be 3-30 characters: letters, numbers, dot, dash or underscore')
    return username


def validate_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters')
    if len(password) > 200:
        raise AuthError('Password is too long')
    return password


def find_user(username):
    return User.query.filter(db.func.lower(User.username) == (username or '').strip().lower()).first()


def create_user(username, password, role='user', starting_capital=None):
    username = validate_username(username)
    validate_password(password)
    if role not in ('admin', 'user'):
        raise AuthError("role must be 'admin' or 'user'")
    if find_user(username):
        raise AuthError('That username is taken', 409)
    cfg = current_app.config
    user = User(username=username, role=role, is_active=True,
                starting_capital=float(starting_capital or cfg.get('STARTING_CAPITAL', 100000.0)),
                auto_trade=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    if role == 'admin' and User.query.filter_by(role='admin').count() == 1:
        assign_legacy_data(user)
    return user


def admin_count():
    return User.query.filter_by(role='admin', is_active=True).count()


def signup_allowed():
    value = AppSetting.get('allow_signup')
    if value is None:
        return bool(current_app.config.get('ALLOW_SIGNUP', True))
    return value == '1'


def needs_admin_setup():
    return User.query.filter_by(role='admin').count() == 0


def current_user():
    return getattr(g, 'user', None)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None or not user.is_admin:
            return _bad('Admins only', 403, 'admin_only')
        return fn(*args, **kwargs)
    return wrapper


# ------------------------------------------------------------- middleware
def require_login():
    """before_request: attach g.user, reject anonymous calls to private endpoints"""
    g.user = None
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        g.user = _user_from_token(header[7:].strip())
    if request.method == 'OPTIONS' or request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    if g.user is None:
        return _bad('Please log in', 401, 'login_required')
    return None


# ----------------------------------------------------------- throttling
def _throttled(key):
    now = time.time()
    with _FAILURE_LOCK:
        recent = [t for t in _FAILURES.get(key, []) if now - t < FAILURE_WINDOW]
        _FAILURES[key] = recent
        return len(recent) >= MAX_FAILURES


def _record_failure(key):
    with _FAILURE_LOCK:
        _FAILURES.setdefault(key, []).append(time.time())


def _clear_failures(key):
    with _FAILURE_LOCK:
        _FAILURES.pop(key, None)


# ----------------------------------------------------------------- routes
@auth_bp.route('/config', methods=['GET'])
def config():
    """What the login page should offer"""
    setup = needs_admin_setup()
    return jsonify({
        'status': 'success',
        'signup_allowed': signup_allowed() or (setup and is_local_request()),
        'needs_admin_setup': setup,
        'can_create_admin': setup and is_local_request(),
    }), 200


@auth_bp.route('/register', methods=['POST'])
def register():
    """POST {"username", "password"} -> {"token", "user"}"""
    data = request.get_json(silent=True) or {}
    first_admin = needs_admin_setup() and is_local_request()
    if not first_admin and not signup_allowed():
        return _bad('Sign-up is closed. Ask the admin for an account.', 403, 'signup_closed')
    try:
        user = create_user(data.get('username'), data.get('password'), role='admin' if first_admin else 'user')
    except AuthError as e:
        return _bad(str(e), e.status)
    user.last_login = datetime.utcnow()
    db.session.commit()
    logger.info(f"New {'admin' if user.is_admin else 'user'} account: {user.username}")
    return jsonify({'status': 'success', 'token': issue_token(user), 'user': user.to_dict()}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """POST {"username", "password"} -> {"token", "user"}"""
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()
    key = (_client_id(), username.lower())
    if _throttled(key):
        return _bad('Too many failed attempts. Wait 15 minutes and try again.', 429, 'throttled')
    user = find_user(username)
    if user is None or not user.check_password(data.get('password')):
        _record_failure(key)
        time.sleep(0.5)
        return _bad('Wrong username or password', 401, 'bad_credentials')
    if not user.is_active:
        return _bad('This account has been disabled', 403, 'disabled')
    _clear_failures(key)
    user.last_login = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'success', 'token': issue_token(user), 'user': user.to_dict()}), 200


@auth_bp.route('/me', methods=['GET'])
def me():
    return jsonify({'status': 'success', 'user': current_user().to_dict()}), 200


@auth_bp.route('/password', methods=['PUT'])
def change_password():
    """PUT {"current_password", "new_password"} -> new token (other devices are logged out)"""
    user = current_user()
    data = request.get_json(silent=True) or {}
    if not user.check_password(data.get('current_password')):
        return _bad('Current password is wrong', 401, 'bad_credentials')
    try:
        user.set_password(validate_password(data.get('new_password')))
    except AuthError as e:
        return _bad(str(e), e.status)
    db.session.commit()
    return jsonify({'status': 'success', 'token': issue_token(user)}), 200


# ---------------------------------------------------------------- startup
def bootstrap_admin(app):
    """Create the admin from ADMIN_USERNAME / ADMIN_PASSWORD when no admin exists yet"""
    username = (app.config.get('ADMIN_USERNAME') or 'admin').strip()
    password = app.config.get('ADMIN_PASSWORD') or ''
    if not needs_admin_setup():
        return
    if not password:
        logger.warning("No admin account yet. Set ADMIN_PASSWORD in .env, or open http://localhost:3000 on this "
                       "computer and create the first account (it becomes the admin).")
        return
    try:
        user = create_user(username, password, role='admin')
        user.auto_trade = bool(app.config.get('AUTO_TRADE', False))
        db.session.commit()
        logger.info(f"Created admin account '{user.username}' from ADMIN_USERNAME/ADMIN_PASSWORD")
    except AuthError as e:
        db.session.rollback()
        logger.error(f"Could not create the admin account from .env: {e}")


def init_auth(app):
    with app.app_context():
        configured = app.config.get('SECRET_KEY')
        if not configured or configured in ('dev-secret-key-change-in-production', 'change_me',
                                            'your_secret_key_here'):
            app.config['AUTH_SECRET'] = AppSetting.secret_key()
        else:
            app.config['AUTH_SECRET'] = configured
        bootstrap_admin(app)
    app.before_request(require_login)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
