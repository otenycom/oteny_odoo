"""The generic bot-driven-workflow layer on riverflow.state.mixin (D173/D174, Layer 2).

The transition harness (hermeshost) drives ANY riverflow workflow with a bot: it reads
``bot_work_queue`` over /json/2/ and, per queued record, claims it (``bot_claim``) then fires an
isolated agent run. This layer lives on the STATE MIXIN — not ``riverflow.service`` — so any
workflow-bearing model (a service, or any model that carries ``riverflow.state.mixin``) is
bot-drivable. It resolves the harness work-item contract from the WORKFLOW SHAPE + the generic
state/transition roles (``state.bot_stage`` + ``transition.bot_role``) — never a hard-coded xml-id —
plus a ``_bot_task_spec()`` hook an app overrides for its domain (the skill / prompt / bot-safe DTO).
No ``oteny_bot`` dependency: the queue/claim/reaper are self-contained; the activity write-back is
the bot's job.

The mixin also owns the SAFETY BELT for a dead harness: it stamps ``bot_work_started_at`` when a
record enters a bot ``in_progress`` state, and ``_bot_reap_timeouts`` (an ir.cron) escalates any
record stuck past its state's ``bot_timeout_minutes`` SLA through the state's ``is_bot_timeout``
transition — so a crashed run that never reports back still hands the work back to a human.
"""

from datetime import timedelta

from odoo import api, fields, models


class RiverflowStateBotMixin(models.AbstractModel):
    _inherit = "riverflow.state.mixin"

    bot_work_started_at = fields.Datetime(
        "Bot Work Started",
        copy=False,
        help="When this record entered a bot `in_progress` state (stamped by the state mixin on the "
        "state change; cleared on leaving). The timeout reaper escalates a record whose dwell here "
        "exceeds the state's bot_timeout_minutes.",
    )

    def _sync_workflow_with_state(self, vals):
        """Extend the mixin's state-change hook to stamp/clear the bot in-progress clock: entering a
        bot `in_progress` state stamps ``bot_work_started_at`` (for the timeout reaper), any other
        state change clears it. Runs inside write() and create() before the DB write."""
        super()._sync_workflow_with_state(vals)
        if "state_id" in vals:
            new_state = (
                self.env["riverflow.state"].browse(vals["state_id"]) if vals["state_id"] else False
            )
            vals["bot_work_started_at"] = (
                fields.Datetime.now() if new_state and new_state.bot_stage == "in_progress" else False
            )

    @api.model
    def bot_work_queue(self):
        """The bot-owned work waiting for an isolated agent run (the harness contract, generic).

        One dict per record in a ``queue`` bot-stage state, resolved to {service_id, state,
        claim_transition_id, in_progress_state, escalate_transition_id, expect_state_in} from the
        workflow shape + {skill, prompt, dto} from the domain ``_bot_task_spec()`` hook. A record
        whose workflow isn't bot-configured (no ``claim`` transition) is skipped. No sudo — the
        caller is the bot user; kwargs are never named ``ids`` (the /json/2/ recordset selector)."""
        queue_states = self.env["riverflow.state"].search([("bot_stage", "=", "queue")])
        if not queue_states:
            return []
        items = []
        for record in self.search([("state_id", "in", queue_states.ids)]):
            item = record._bot_work_item()
            if item:
                items.append(item)
        return items

    def _bot_work_item(self):
        """Resolve ONE queued record to the harness work item from the workflow shape + the generic
        roles + the ``_bot_task_spec`` hook. ``None`` when the workflow isn't bot-configured (no
        ``claim`` transition out of the queue state)."""
        self.ensure_one()
        state = self.state_id
        claim = state.from_transition_ids.filtered(lambda t: t.bot_role == "claim")[:1]
        if not claim:
            return None
        in_progress = claim.to_state_id
        outgoing = in_progress.from_transition_ids
        escalate = outgoing.filtered(lambda t: t.bot_role == "escalate")[:1]
        # the agent's expected success targets = the `work` transitions out of the in-progress state
        expect = outgoing.filtered(lambda t: t.bot_role == "work").mapped("to_state_id")
        spec = self._bot_task_spec()
        return {
            "service_id": self.id,
            "state": state.name,
            "claim_transition_id": claim.id,
            "in_progress_state": in_progress.name,
            "escalate_transition_id": escalate.id if escalate else False,
            "expect_state_in": expect.mapped("name"),
            "skill": spec.get("skill"),
            "prompt": spec.get("prompt", ""),
            "dto": spec.get("dto") or {},
        }

    def _bot_task_spec(self):
        """Domain hook: the {skill, prompt, dto} for one record's isolated agent run. Base is
        generic/empty; an app module (e.g. crewradar_cuneus_sign for MFNL) overrides per record
        type to name the Talent skill, the anchored task, and the bot-safe DTO."""
        self.ensure_one()
        return {"skill": False, "prompt": "", "dto": {}}

    @api.model
    def bot_claim(self, service_id, transition_id):
        """Idempotently advance ONE record through ``transition_id`` — the harness claim (→ the
        in-progress state before running), escalate (→ a human state on failure) and the reaper's
        timeout exit. Returns ``{ok, state, already?}``: a no-op when already in the target state (a
        re-poll after a crash — never double-advance), a clean advance from the transition's source
        state, else ``{ok: False}`` (the state moved under us). A direct state write (the engine
        force-couples workflow_id to state_id). The ``service_id`` param name is kept for the stable
        /json/2/ harness contract though the record may be any workflow-bearing model."""
        record = self.browse(service_id).exists()
        transition = self.env["riverflow.transition"].browse(transition_id).exists()
        if not record or not transition:
            return {"ok": False, "reason": "unknown record or transition"}
        if record.state_id == transition.to_state_id:
            return {"ok": True, "already": True, "state": record.state_id.name}
        if transition.from_state_id and record.state_id != transition.from_state_id:
            return {"ok": False, "state": record.state_id.name,
                    "reason": f"record is in {record.state_id.name!r}, not "
                    f"{transition.from_state_id.name!r}"}
        vals = {"state_id": transition.to_state_id.id}
        if transition.to_responsible_team_id:
            vals["responsible_team_id"] = transition.to_responsible_team_id.id
        record.write(vals)
        return {"ok": True, "state": record.state_id.name}

    @api.model
    def _bot_reap_timeouts(self):
        """Escalate bot in-progress records stuck past their state's SLA — the timeout reaper, run by
        an ir.cron on each concrete workflow-bearing model. For every ``in_progress`` state with a
        positive ``bot_timeout_minutes``, any record whose ``bot_work_started_at`` is older than the
        SLA is advanced through that state's ``is_bot_timeout`` transition (the reaper's exit,
        distinct from the agent's own escalate). Idempotent via ``bot_claim``. Returns the count
        reaped. This is the backstop for a harness that died mid-run and never reported back."""
        now = fields.Datetime.now()
        states = self.env["riverflow.state"].search([
            ("bot_stage", "=", "in_progress"),
            ("bot_timeout_minutes", ">", 0),
        ])
        reaped = 0
        for state in states:
            timeout_transition = state.from_transition_ids.filtered("is_bot_timeout")[:1]
            if not timeout_transition:
                continue
            deadline = now - timedelta(minutes=state.bot_timeout_minutes)
            stuck = self.search([
                ("state_id", "=", state.id),
                ("bot_work_started_at", "!=", False),
                ("bot_work_started_at", "<", deadline),
            ])
            for record in stuck:
                if self.bot_claim(record.id, timeout_transition.id).get("ok"):
                    reaped += 1
        return reaped
