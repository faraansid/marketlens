"""Create or update a user from the command line (requires server access).

    python -m scripts.create_user --username farhan --owner

`--owner` makes this account the single owner (the only user who can add or
remove users in the app); any previous owner loses that role.
The password is read interactively (or from the MARKETLENS_PASSWORD env var for
automation) and is never passed on the command line or printed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, update  # noqa: E402

from app.auth.security import hash_password, password_problems  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Create or update a MarketLens user")
    p.add_argument("--username", required=True)
    p.add_argument("--name")
    p.add_argument("--owner", action="store_true", help="make this the single owner account")
    args = p.parse_args()

    pw = os.environ.get("MARKETLENS_PASSWORD")
    if not pw:
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Confirm password: "):
            sys.exit("Passwords do not match.")
    problems = password_problems(pw)
    if problems:
        sys.exit("Password needs " + ", ".join(problems) + ".")

    init_db()
    with session_scope() as db:
        username = args.username.strip().lower()
        user = db.scalars(select(User).where(func.lower(User.username) == username)).first()
        action = "Updated" if user else "Created"
        if user is None:
            user = User(username=username)
            db.add(user)
        user.full_name = args.name or user.full_name
        user.password_hash = hash_password(pw)
        user.is_active = True
        if args.owner:
            db.flush()
            db.execute(update(User).where(User.id != user.id).values(is_admin=False))
            user.is_admin = True
    print(f"{action} user '{username}'{' (owner)' if args.owner else ''}.")


if __name__ == "__main__":
    main()
