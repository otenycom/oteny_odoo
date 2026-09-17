"""riverflow answers the bridge's work contract for its own carriers.

The platform calls ``oteny.bot`` (``work_consume``, ``work_probe``, ``work_release``)
by work token and never names this engine. This extension maps the three verbs to
the bot mixin: the run-claim consume, the token check, and the hand-back through
the state's ``is_bot_timeout`` exit.
"""
from odoo import models


class OtenyBotRiverflow(models.Model):
    _inherit = "oteny.bot"

    def _riverflow_carrier(self, origin_model):
        Model = self.env.get(origin_model) if origin_model else None
        if Model is None or not hasattr(Model, "bot_run_claim"):
            return None
        return Model

    def _work_consume(self, origin_model, res_id, work_token):
        Model = self._riverflow_carrier(origin_model)
        if Model is None:
            return super()._work_consume(origin_model, res_id, work_token)
        return Model.bot_run_claim(res_id, work_token)

    def _work_probe(self, origin_model, res_id, work_token):
        Model = self._riverflow_carrier(origin_model)
        if Model is None:
            return super()._work_probe(origin_model, res_id, work_token)
        check = Model.bot_token_check(res_id=res_id, work_token=work_token) or {}
        if check.get("ok"):
            return {"ok": True, "mine": True, "released": False, "state": check.get("state")}
        record = Model.browse(res_id).exists()
        released = bool(record) and record.bot_released_token == work_token
        out = {"ok": True, "mine": False, "released": released,
               "reason": "released by the turn" if released else str(check.get("reason") or ""),
               "state": record.state_id.name if record else check.get("state")}
        if released and record.state_id.bot_stage == "in_progress" and record.bot_claim_token:
            out["next_token"] = record.bot_claim_token
        return out

    def _work_release(self, origin_model, res_id, work_token, reason):
        Model = self._riverflow_carrier(origin_model)
        if Model is None:
            return super()._work_release(origin_model, res_id, work_token, reason)
        record = Model.browse(res_id).exists()
        if not record:
            return {"ok": False, "released": False, "reason": "unknown record"}
        if record.state_id.bot_stage != "in_progress" or record.bot_claim_token != work_token:
            return {"ok": True, "released": False, "state": record.state_id.name,
                    "reason": "not this token's live claim"}
        exit_transition = record.state_id.bot_timeout_transition()
        if not exit_transition:
            return {"ok": True, "released": False, "state": record.state_id.name,
                    "reason": "the state has no timeout exit; the reaper stays the backstop"}
        # No ``bot_reap`` context: this turn did not wait for the state's SLA.
        claim = Model.bot_claim(res_id, exit_transition.id, work_token=work_token) or {}
        return {"ok": bool(claim.get("ok")),
                "released": bool(claim.get("ok") and not claim.get("already")),
                "state": claim.get("state"),
                "reason": str(claim.get("reason") or reason or "released")}
