"""compact-bug-01 专属核验：单轨求和、重算芯片、挡合并、并发锁。"""
import threading

import pytest

from app.db import get_db
from app.services import plans, reconcile, rewrite
from app.services.errors import ServiceError
from app.services.plan_bytes import recompute_plan_bytes


def _mount(db, plan_id):
    with get_db(db) as conn:
        return int(
            conn.execute(
                "SELECT COALESCE(SUM(f.size_bytes),0) AS s FROM plan_items i "
                "JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=?",
                (plan_id,),
            ).fetchone()["s"]
        )


def _locked(db, plan_id):
    with get_db(db) as conn:
        return int(
            conn.execute(
                "SELECT plan_bytes FROM compact_plans WHERE id=?", (plan_id,)
            ).fetchone()["plan_bytes"]
        )


def _bump_file_size(db, plan_id, delta):
    with get_db(db) as conn:
        row = conn.execute(
            "SELECT f.id AS fid FROM plan_items i "
            "JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=? LIMIT 1",
            (plan_id,),
        ).fetchone()
        conn.execute(
            "UPDATE lake_files SET size_bytes=size_bytes+? WHERE id=?",
            (delta, row["fid"]),
        )


def test_seed_plan_card_matches_mount(db):
    items = plans.list_plans(db_path=db)
    assert items
    for p in items:
        assert p["plan_bytes"] == p["mount_bytes"]
        assert p["bytes_chip"] == "已重算"


def test_drift_blocks_merge_then_recompute_unlocks(db):
    p = plans.create_plan("CP-DRIFT", "漂移计划", "dw_users", db_path=db)
    plans.attach_loose_files(p["id"], db_path=db)
    plans.publish_plan(p["id"], db_path=db)
    _bump_file_size(db, p["id"], 4096)
    # 计划字节偏离挂载和：卡片亮待重算，合并被挡
    listed = {x["id"]: x for x in plans.list_plans(db_path=db)}[p["id"]]
    assert listed["bytes_chip"] == "待重算"
    with pytest.raises(ServiceError):
        rewrite.start_rewrite(p["id"], db_path=db)
    # 仓管点重算：一次写完求和，凭证行落库，芯片转已重算
    out = recompute_plan_bytes(p["id"], db_path=db)
    assert out["chip"] == "已重算"
    assert out["plan_bytes"] == _mount(db, p["id"])
    assert _locked(db, p["id"]) == _mount(db, p["id"])
    with get_db(db) as conn:
        v = conn.execute(
            "SELECT * FROM plan_byte_vouchers WHERE plan_id=? ORDER BY id DESC",
            (p["id"],),
        ).fetchall()
    assert v
    assert int(v[0]["mount_bytes"]) == _mount(db, p["id"])
    # 重算后卡片芯片与库内和一致，合并放行，对账同源
    listed = {x["id"]: x for x in plans.list_plans(db_path=db)}[p["id"]]
    assert listed["bytes_chip"] == "已重算"
    assert listed["plan_bytes"] == _locked(db, p["id"])
    job = rewrite.start_rewrite(p["id"], db_path=db)
    assert job["status"] == "成功"
    report = reconcile.run_reconcile(p["id"], db_path=db)
    assert report["before_bytes"] == report["after_bytes"]
    assert report["chip"] == "已同源"


def test_concurrent_recompute_serialized(db):
    p = plans.create_plan("CP-LOCK", "并发重算", "dw_users", db_path=db)
    plans.attach_loose_files(p["id"], db_path=db)
    errors = []

    def worker():
        try:
            recompute_plan_bytes(p["id"], db_path=db)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    # 两侧同时重算不双写互覆：最终锁写字节等于挂载和
    assert _locked(db, p["id"]) == _mount(db, p["id"])
    listed = {x["id"]: x for x in plans.list_plans(db_path=db)}[p["id"]]
    assert listed["bytes_chip"] == "已重算"
