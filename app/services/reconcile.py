"""体积对账：对照计划锁写字节与合并结果，与计划卡片同源。"""
from __future__ import annotations

from app.db import get_db
from app.services.errors import ServiceError


def report_chip(aligned: bool, before_bytes: int, after_bytes: int) -> str:
    if not aligned:
        return "待重算"
    if after_bytes <= 0:
        return "待合并"
    if before_bytes != after_bytes:
        return "须核对"
    return "已同源"


def list_reports(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT r.*, p.plan_code, p.target_table FROM volume_reports r "
            "JOIN compact_plans p ON p.id=r.plan_id ORDER BY r.id DESC"
        ).fetchall()
        items = [dict(r) for r in rows]
        for it in items:
            it["aligned"] = bool(it["aligned"])
            it["chip"] = report_chip(
                it["aligned"], int(it["before_bytes"]), int(it["after_bytes"])
            )
        return items


def run_reconcile(plan_id: int, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        plan = conn.execute(
            "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        before = conn.execute(
            "SELECT COALESCE(SUM(f.size_bytes),0) AS b, COUNT(*) AS c "
            "FROM plan_items i JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=?",
            (plan_id,),
        ).fetchone()
        job = conn.execute(
            "SELECT * FROM rewrite_jobs WHERE plan_id=? AND status='成功' "
            "ORDER BY id DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        after = int(job["merged_bytes"]) if job else 0
        # 与计划卡片同一套锁写字节，对账详情亮同源和
        before_b = int(plan["plan_bytes"])
        aligned = before_b == int(before["b"])
        summary = (
            f"计划#{plan_id} {plan['plan_code']}：挂载前 {before_b} 字节 / "
            f"{before['c']} 文件，合并后记 {after} 字节"
        )
        if not aligned:
            summary += "；计划字节与挂载和未对齐，请先重算"
        elif job and before_b != after:
            summary += "；体积不一致须人工核对"
        else:
            summary += "；口径已同源"
        cur = conn.execute(
            "INSERT INTO volume_reports(plan_id, before_bytes, after_bytes, file_count, aligned, summary) "
            "VALUES (?,?,?,?,?,?)",
            (plan_id, before_b, after, int(before["c"]), 1 if aligned else 0, summary),
        )
        out = dict(
            conn.execute(
                "SELECT * FROM volume_reports WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        )
        out["aligned"] = aligned
        out["chip"] = report_chip(aligned, before_b, after)
        return out
