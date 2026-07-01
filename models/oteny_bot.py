"""The generic Oteny business-bot models (Layer 1 — no workflow / domain coupling).

An Oteny bot is external (its own machine), so it writes its activity back into this Odoo over
the /json/2/ uplink; the owner reviews it here. Everything is domain-agnostic: a session's origin
is a soft ``(model, res_id)`` reference so a workflow engine or an app module can attach a session
to its own record without this addon depending on it.
"""

from odoo import api, fields, models


class OtenyBot(models.Model):
    _name = "oteny.bot"
    _description = "Oteny Business Bot"
    _order = "name"

    name = fields.Char(required=True)
    bot_user_id = fields.Many2one(
        "res.users", string="Bot User",
        help="The Odoo login the bot authenticates as over /json/2/ (its scoped seam user).")
    discuss_channel_id = fields.Many2one(
        "discuss.channel", string="Channel",
        help="The Discuss channel the bot converses in with its owner/operators.")
    uplink_ref = fields.Char(
        "Uplink Ref", index=True, copy=False,
        help="The Oteny-side tenant reference (e.g. hh00140) the bot writes its activity under. "
        "Opaque to this Odoo; the bot supplies it when it calls record_activity.")
    active = fields.Boolean(default=True)
    session_ids = fields.One2many("oteny.bot.session", "bot_id", string="Activity")
    session_count = fields.Integer(compute="_compute_session_count")

    @api.depends("session_ids")
    def _compute_session_count(self):
        for bot in self:
            bot.session_count = len(bot.session_ids)

    @api.model
    def record_activity(self, uplink_ref, session, turns=None):
        """The seam the bot calls over /json/2/ to log ONE exchange (owner-visibility, generic).

        Creates an ``oteny.bot.session`` (+ optional child ``turns``) for the bot identified by
        ``uplink_ref``. ``sudo`` internally — the bot's least-privilege key need not carry write
        on the log models — but scoped to the bot's OWN record, so a bot can only log for itself.
        ``session`` is the session vals ({name, kind, request, response, outcome, outcome_detail,
        origin_model, origin_res_id, started_at, duration_s}); ``turns`` an optional list of turn
        vals. Kwargs are never named ``ids`` (the /json/2/ recordset selector). Returns
        ``{ok, session_id}``."""
        bot = self.sudo().search([("uplink_ref", "=", uplink_ref)], limit=1)
        if not bot:
            return {"ok": False, "reason": f"no oteny.bot with uplink_ref {uplink_ref!r}"}
        allowed = set(self.env["oteny.bot.session"]._fields)
        vals = {k: v for k, v in (session or {}).items() if k in allowed}
        vals["bot_id"] = bot.id
        if turns:
            tallowed = set(self.env["oteny.bot.turn"]._fields)
            vals["turn_ids"] = [
                (0, 0, {k: v for k, v in (t or {}).items() if k in tallowed}) for t in turns]
        rec = self.env["oteny.bot.session"].sudo().create(vals)
        return {"ok": True, "session_id": rec.id}

    def action_open_sessions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "oteny.bot.session",
            "view_mode": "list,form",
            "domain": [("bot_id", "=", self.id)],
            "context": {"search_default_bot_id": self.id},
        }


class OtenyBotSession(models.Model):
    _name = "oteny.bot.session"
    _description = "Oteny Bot Activity (one exchange)"
    _order = "started_at desc, id desc"

    bot_id = fields.Many2one("oteny.bot", required=True, ondelete="cascade", index=True)
    name = fields.Char("Task", help="A short label for the exchange (the task / request summary).")
    kind = fields.Selection(
        [("conversational", "Conversational"), ("isolated_turn", "Isolated turn")],
        default="isolated_turn",
        help="conversational = a chat turn in the channel session; isolated_turn = a fresh, "
        "single-purpose run anchored on one task (the workflow-driven path).")
    request = fields.Text("Request / anchored task", readonly=True)
    response = fields.Text("Response", readonly=True)
    outcome = fields.Selection(
        [("ok", "OK"), ("halted", "Halted / handed back"), ("escalated", "Escalated"),
         ("error", "Error")], index=True, readonly=True)
    outcome_detail = fields.Char(readonly=True)
    # Generic origin — the Odoo record this exchange is about (e.g. a riverflow.service). A SOFT
    # reference (model name + id), not a Many2one, so this generic addon never depends on the
    # consuming module's models; the workflow/app layer sets these + renders an embedded view.
    origin_model = fields.Char("Origin Model", index=True, readonly=True)
    origin_res_id = fields.Integer("Origin Res ID", index=True, readonly=True)
    started_at = fields.Datetime(default=fields.Datetime.now, index=True, readonly=True)
    duration_s = fields.Float("Duration (s)", readonly=True)
    turn_ids = fields.One2many("oteny.bot.turn", "session_id", string="Turns", readonly=True)
    turn_count = fields.Integer(compute="_compute_turn_metrics")
    tool_call_count = fields.Integer(compute="_compute_turn_metrics")

    @api.depends("turn_ids", "turn_ids.tool_call_count")
    def _compute_turn_metrics(self):
        for s in self:
            s.turn_count = len(s.turn_ids)
            s.tool_call_count = sum(s.turn_ids.mapped("tool_call_count"))


class OtenyBotTurn(models.Model):
    _name = "oteny.bot.turn"
    _description = "Oteny Bot Activity Turn (one LLM call)"
    _order = "session_id, sequence, id"

    session_id = fields.Many2one("oteny.bot.session", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    system_prompt = fields.Text(readonly=True)
    user_message = fields.Text(readonly=True)
    llm_response = fields.Text(readonly=True)
    tool_calls = fields.Json(
        "Tool Calls", readonly=True,
        help="This turn's tool calls (name, args, result) — the exchange detail an admin reviews.")
    tool_call_count = fields.Integer(readonly=True)
    llm_model = fields.Char("LLM Model", readonly=True)
    tokens_in = fields.Integer(readonly=True)
    tokens_out = fields.Integer(readonly=True)
    duration_s = fields.Float("Duration (s)", readonly=True)
