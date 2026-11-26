"""Admin command line (run on the server).

  python -m app.cli create-admin <username>      first admin, prompts for password
  python -m app.cli reset-mfa <username>         lost phone: user sets MFA up again at next login
  python -m app.cli unlock <username>
"""
import argparse
import getpass
import sys

from sqlalchemy import delete, select

from .config import get_settings
from .db import Base, get_engine, new_session
from .models import User, WebSession
from .security import hash_password, password_problem


def _user(db, username: str) -> User:
    u = db.scalar(select(User).where(User.username == username.lower()))
    if u is None:
        sys.exit(f"No such user: {username}")
    return u


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin")
    c.add_argument("username")
    c.add_argument("--display-name", default="")
    c.add_argument("--password-stdin", action="store_true", help="read password from stdin")
    sub.add_parser("reset-mfa").add_argument("username")
    sub.add_parser("unlock").add_argument("username")
    args = p.parse_args(argv)

    if get_settings().is_sqlite:
        Base.metadata.create_all(get_engine())

    with new_session() as db:
        if args.cmd == "create-admin":
            if db.scalar(select(User).where(User.username == args.username.lower())):
                sys.exit("User already exists")
            if args.password_stdin:
                pw = sys.stdin.readline().rstrip("\n")
            else:
                pw = getpass.getpass("Password: ")
                if pw != getpass.getpass("Repeat:   "):
                    sys.exit("Passwords do not match")
            problem = password_problem(pw)
            if problem:
                sys.exit(problem)
            db.add(
                User(
                    username=args.username.lower(),
                    display_name=args.display_name or args.username,
                    role="admin",
                    password_hash=hash_password(pw),
                )
            )
            db.commit()
            print(f"Admin '{args.username}' created. Set up MFA at first login.")
        elif args.cmd == "reset-mfa":
            u = _user(db, args.username)
            u.totp_secret_enc, u.totp_confirmed, u.totp_last_step = None, False, 0
            db.execute(delete(WebSession).where(WebSession.user_id == u.id))
            db.commit()
            print(f"MFA reset for '{u.username}'.")
        elif args.cmd == "unlock":
            u = _user(db, args.username)
            u.locked_until, u.failed_logins = None, 0
            db.commit()
            print(f"'{u.username}' unlocked.")


if __name__ == "__main__":
    main()
