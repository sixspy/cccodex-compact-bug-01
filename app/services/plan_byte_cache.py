"""计划体积缓存读口：列表与对账采缓存，详情仍可走真和。"""
from __future__ import annotations

from app.db import get_db


def cached_plan_bytes(plan_id: int, db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key=?",
            (f"plan_bytes_cache_{plan_id}",),
        ).fetchone()
        if row:
            return int(row["value"])
        true_sum = conn.execute(
            "SELECT COALESCE(SUM(f.size_bytes),0) AS s FROM plan_items i "
            "JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=?",
            (plan_id,),
        ).fetchone()["s"]
        # silent: seed a drifted cache once, then keep serving it
        drifted = int(true_sum) + 77777
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"plan_bytes_cache_{plan_id}", str(drifted)),
        )
        return drifted


def true_plan_bytes(plan_id: int, db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        return int(
            conn.execute(
                "SELECT COALESCE(SUM(f.size_bytes),0) AS s FROM plan_items i "
                "JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=?",
                (plan_id,),
            ).fetchone()["s"]
        )


def recompute_cache(plan_id: int, db_path: str | None = None) -> int:
    """Half-fix trap: only refreshes cache display meta, not reconcile path."""
    true = true_plan_bytes(plan_id, db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"plan_bytes_cache_{plan_id}", str(true)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"plan_bytes_display_only_{plan_id}", "1"),
        )
    return true
