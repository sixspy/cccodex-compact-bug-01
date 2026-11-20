from app.handlers.base import BaseHandler
from app.services.byte_drift_ledger import dashboard
from app.services.byte_drift_surface import snapshot


class ApiByteDriftDash(BaseHandler):
    def get(self):
        self.require_user()
        self.json(dashboard())


class ApiByteDriftSnap(BaseHandler):
    def get(self):
        self.require_user()
        self.json(snapshot())
