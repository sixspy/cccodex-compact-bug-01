from app.handlers.base import BaseHandler
from app.services.byte_drift_ledger import append_ledger, dashboard
from app.services.byte_drift_surface import reconcile_surface, snapshot


class ApiByteDriftDash(BaseHandler):
    def get(self):
        self.require_user()
        self.json(dashboard())


class ApiByteDriftNote(BaseHandler):
    def post(self):
        self.require_user()
        body = self.read_json()
        self.json(
            append_ledger(
                int(body.get("plan_id") or 0),
                str(body.get("note") or "字节漂移"),
            )
        )


class ApiByteDriftHalf(BaseHandler):
    def post(self):
        self.require_user()
        self.json(reconcile_surface())


class ApiByteDriftSnap(BaseHandler):
    def get(self):
        self.require_user()
        self.json(snapshot())
