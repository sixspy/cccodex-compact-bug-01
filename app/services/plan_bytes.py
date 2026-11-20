"""计划体积单轨求和：挂载和重算后写凭证并锁写计划字节，全站只读这一套。"""
from __future__ import annotations

from app.db import get_db, get_db_locked
from app.services.errors import ServiceError

_MOUNT_SQL = (
    "SELECT COALESCE(SUM(f.size_bytes),0) AS s, COUNT(*) AS c "
    "FROM plan_items i JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=?"
)

CHIP_OK = "已重算"
CHIP_OFF = "待重算"


def true_plan_bytes(plan_id: int, db_path: str | None = None) -> int:
    """碎件挂载实时求和。"""
    with get_db(db_path) as conn:
        return int(
            conn.execute(_MOUNT_SQL, (plan_id,)).fetchone()["s"]
        )


def locked_plan_bytes(plan_id: int, db_path: str | None = None) -> int:
    """计划卡片/对账/合并共同读的锁写计划字节。"""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT plan_bytes FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not row:
            raise ServiceError("计划不存在", 404)
        return int(row["plan_bytes"])


def write_sum_in_txn(conn, plan_id: int, source: str) -> dict:
    """在已有事务内一次写完：算挂载和 -> 插凭证行 -> 锁写计划字节。"""
    row = conn.execute(_MOUNT_SQL, (plan_id,)).fetchone()
    mount, count = int(row["s"]), int(row["c"])
    cur = conn.execute(
        "INSERT INTO plan_byte_vouchers(plan_id, mount_bytes, file_count, source) "
        "VALUES (?,?,?,?)",
        (plan_id, mount, count, source),
    )
    conn.execute(
        "UPDATE compact_plans SET plan_bytes=? WHERE id=?",
        (mount, plan_id),
    )
    return {
        "plan_id": plan_id,
        "plan_bytes": mount,
        "file_count": count,
        "voucher_id": cur.lastrowid,
    }


def recompute_plan_bytes(
    plan_id: int,
    source: str = "recompute",
    db_path: str | None = None,
) -> dict:
    """仓管点重算：BEGIN IMMEDIATE 串行化，并发两侧不会双写互覆。"""
    with get_db_locked(db_path) as conn:
        plan = conn.execute(
            "SELECT id FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        out = write_sum_in_txn(conn, plan_id, source)
    out["chip"] = CHIP_OK
    return out


def recompute_all(db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        ids = [
            int(r["id"])
            for r in conn.execute("SELECT id FROM compact_plans ORDER BY id").fetchall()
        ]
    items = [recompute_plan_bytes(pid, db_path=db_path) for pid in ids]
    return {"recomputed": len(items), "items": items}


def list_vouchers(plan_id: int, db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM plan_byte_vouchers WHERE plan_id=? ORDER BY id DESC",
            (plan_id,),
        ).fetchall()
        return [dict(r) for r in rows]
