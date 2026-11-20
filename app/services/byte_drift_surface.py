"""体积同源状态面：芯片与真相同轨直读计划对齐，不做假绿。"""
from __future__ import annotations

from app.db import get_db

_OK = "已同源"
_BAD = "待重算"


def alignment_rows(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT p.id, p.plan_code, p.plan_bytes, "
            "(SELECT COALESCE(SUM(f.size_bytes),0) FROM plan_items i "
            " JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=p.id) AS mount_bytes "
            "FROM compact_plans p ORDER BY p.id"
        ).fetchall()
        return [dict(r) for r in rows]


def truth_flag(db_path: str | None = None) -> str:
    rows = alignment_rows(db_path)
    aligned = all(
        int(r["plan_bytes"]) == int(r["mount_bytes"]) for r in rows
    )
    return _OK if aligned else _BAD


def panel_chip(db_path: str | None = None) -> str:
    # 芯片与真相同源，不再单独粉刷
    return truth_flag(db_path)


def snapshot(db_path: str | None = None) -> dict:
    flag = truth_flag(db_path)
    return {
        "title": "字节漂移",
        "panel_chip": flag,
        "truth": flag,
        "aligned": flag == _OK,
    }
