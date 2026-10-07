"""Dialect-aware bulk upsert (SQLite and PostgreSQL)."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy.orm import Session


def bulk_upsert(
    db: Session,
    model,
    rows: Sequence[dict] | Iterable[dict],
    conflict_cols: list[str],
    update_cols: list[str] | None = None,
    chunk: int = 500,
) -> int:
    rows = list(rows)
    if not rows:
        return 0
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:  # pragma: no cover
        raise NotImplementedError(f"upsert not implemented for {dialect}")

    cols = update_cols or [k for k in rows[0] if k not in conflict_cols]
    # SQLite caps bound parameters per statement; keep chunks well below it.
    per_row = max(1, len(rows[0]))
    chunk = max(1, min(chunk, 30000 // per_row))
    for i in range(0, len(rows), chunk):
        stmt = insert(model).values(rows[i : i + chunk])
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_={c: getattr(stmt.excluded, c) for c in cols},
        )
        db.execute(stmt)
    return len(rows)
