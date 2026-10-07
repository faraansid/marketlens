"""Set or rotate the master password (requires server access).

    python -m scripts.set_master_password

Anyone who knows the master password can change ANY user's password,
including the owner's. Only its scrypt hash is stored. The value is read
interactively (or from MARKETLENS_MASTER_PASSWORD for automation) and never printed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.master import set_master  # noqa: E402
from app.auth.security import password_problems  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Set the MarketLens master password")
    p.parse_args()

    pw = os.environ.get("MARKETLENS_MASTER_PASSWORD")
    if not pw:
        pw = getpass.getpass("Master password: ")
        if pw != getpass.getpass("Confirm master password: "):
            sys.exit("Passwords do not match.")
    problems = password_problems(pw)
    if problems:
        sys.exit("Master password needs " + ", ".join(problems) + ".")

    init_db()
    with session_scope() as db:
        set_master(db, pw)
    print("Master password set.")


if __name__ == "__main__":
    main()
