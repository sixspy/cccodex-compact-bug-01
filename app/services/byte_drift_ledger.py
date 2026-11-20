"""字节漂移看板：凭证行与同源状态同轨，状态即真相。"""
from __future__ import annotations

from app.db import get_db
from app.services.byte_drift_surface import panel_chip, truth_flag

_TITLE = "字节漂移"
_OK = "已同源"
_BAD = "待重算"


def voucher_rows(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT v.*, p.plan_code FROM plan_byte_vouchers v "
            "JOIN compact_plans p ON p.id=v.plan_id ORDER BY v.id DESC LIMIT 20"
        ).fetchall()
        return [dict(r) for r in rows]


def dashboard(db_path: str | None = None) -> dict:
    chip = panel_chip(db_path)
    truth = truth_flag(db_path)
    return {
        "title": _TITLE,
        "chip": chip,
        "truth": truth,
        "rows": voucher_rows(db_path),
        "ok_chip": _OK,
        "bad_chip": _BAD,
        "fake_green": chip == _OK and truth != _OK,
    }
