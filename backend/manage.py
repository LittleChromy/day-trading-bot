"""
Account maintenance from the command line, on the computer running the bot.

  docker compose exec backend python manage.py list-users
  docker compose exec backend python manage.py set-password <username>
  docker compose exec backend python manage.py make-admin <username>
"""
import getpass
import os
import sys

os.environ['ENABLE_SCHEDULER'] = 'false'  # don't start a second bot

from app import create_app  # noqa: E402
from auth import AuthError, create_user, find_user, validate_password  # noqa: E402
from models import db, User  # noqa: E402


def _ask_password():
    first = getpass.getpass('New password: ')
    if first != getpass.getpass('Repeat it: '):
        sys.exit('Passwords do not match')
    return first


def main(argv):
    if len(argv) < 2 or argv[1] not in ('list-users', 'set-password', 'make-admin', 'create-admin'):
        sys.exit(__doc__ + '  docker compose exec backend python manage.py create-admin <username>\n')
    app = create_app(start_scheduler=False)
    with app.app_context():
        command = argv[1]
        if command == 'list-users':
            for u in User.query.order_by(User.id).all():
                print(f"{u.id:>4}  {u.username:<30} {u.role:<6} {'active' if u.is_active else 'disabled'}")
            return
        if len(argv) < 3:
            sys.exit('Give a username')
        username = argv[2]
        try:
            if command == 'create-admin':
                user = create_user(username, _ask_password(), role='admin')
                print(f"Created admin {user.username}")
                return
            user = find_user(username)
            if user is None:
                sys.exit(f'No user called {username}')
            if command == 'set-password':
                user.set_password(validate_password(_ask_password()))
                user.is_active = True
            else:
                user.role = 'admin'
                user.is_active = True
            db.session.commit()
            print(f"Done: {user.username} ({user.role})")
        except AuthError as e:
            sys.exit(str(e))


if __name__ == '__main__':
    main(sys.argv)
