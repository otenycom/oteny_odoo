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

TOKEN-FENCED CLAIM (the anti-double-file mechanism). A government filing is not idempotent, so
the state machine enforces AT MOST ONE live agent run per claim epoch with three primitives:

1. **CAS claim** — ``bot_claim`` locks the row (``FOR NO KEY UPDATE``), re-reads committed truth,
   and only then advances — two concurrent claimants can never both win.
2. **Dispatch token** — ``bot_claim_token`` is minted on EVERY entry into a bot ``in_progress``
   state and cleared on every exit, in the same vals/transaction as the state change. Only the
   claim winner holds the token; every exit from in-progress (work advance, escalate, reaper
   timeout) requires the current token, so a reaped-then-re-handed record's stale token is
   rejected everywhere — a zombie run cannot advance, escalate, or refile.
3. **Turn-start consume** — ``bot_run_claim`` stamps ``bot_run_started_at`` exactly once per
   token; the dispatcher (hh-discuss adapter / webhook harness) consumes it BEFORE any LLM
   activity, so a replayed dispatch message can never start a second agent run.
"""

import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Fast re-dispatch window (the belt for a dispatch that never reached a live agent). A claim
# whose isolated run was NEVER consumed (``bot_run_started_at`` unset) past ``GRACE`` minutes is
# an orphan — the flagged dispatch was lost while the bot's gateway was down/reconnecting (its
# poll marker seeds PAST history on reconnect, so it never picks the old message up on its own).
# The dispatch cron re-posts it (same claim epoch) until ``CEILING`` minutes, after which the
# in-progress SLA reaper takes over. Re-fire is safe: ``bot_run_claim`` admits at most one run
# per epoch, so a re-post that races a live pickup is dropped (never a double side effect).
_BOT_REDISPATCH_GRACE_MINUTES = 3
_BOT_REDISPATCH_CEILING_MINUTES = 30


class RiverflowStateBotMixin(models.AbstractModel):
    _inherit = "riverflow.state.mixin"

    bot_work_started_at = fields.Datetime(
        "Bot Work Started",
        copy=False,
        help="When this record entered a bot `in_progress` state (stamped by the state mixin on the "
        "state change; cleared on leaving). The timeout reaper escalates a record whose dwell here "
        "exceeds the state's bot_timeout_minutes.",
    )
    bot_claim_token = fields.Char(
        "Bot Claim Token",
        copy=False,
        help="The epoch of ONE claim: minted on every entry into a bot `in_progress` state (same "
        "vals/transaction as the state change), cleared on every exit. Only the claim winner holds "
        "it; every bot_claim exit from in-progress requires it, so a stale (reaped/re-handed) run "
        "is rejected server-side. Rides the dispatch message so the isolated run can prove its "
        "epoch (bot_run_claim / bot_token_check).",
    )
    bot_run_started_at = fields.Datetime(
        "Bot Run Started",
        copy=False,
        help="Stamped by bot_run_claim when the dispatcher consumes this claim's ONE agent run "
        "(before any LLM activity). Unset = the run for the current token has not started; a "
        "replayed dispatch message finds it set and is dropped. Cleared with the token on every "
        "state change.",
    )

    def _sync_workflow_with_state(self, vals):
        """Extend the mixin's state-change hook to stamp/clear the bot in-progress clock AND the
        claim-token epoch: entering a bot `in_progress` state stamps ``bot_work_started_at`` (for
        the timeout reaper) and mints a fresh ``bot_claim_token`` (the epoch of this one claim);
        any other state change clears both. ``bot_run_started_at`` resets on every state change
        (a fresh epoch's run has not been consumed). Minting here — inside write()/create(), same
        vals as the state change — makes claim + token (+ the app's flagged dispatch message)
        commit or roll back atomically."""
        super()._sync_workflow_with_state(vals)
        if "state_id" in vals:
            new_state = (
                self.env["riverflow.state"].browse(vals["state_id"]) if vals["state_id"] else False
            )
            in_progress = bool(new_state and new_state.bot_stage == "in_progress")
            vals["bot_work_started_at"] = fields.Datetime.now() if in_progress else False
            vals["bot_claim_token"] = secrets.token_urlsafe(9) if in_progress else False
            vals["bot_run_started_at"] = False

    def write(self, vals):
        """Extend write to dispatch INLINE when a record enters a bot ``queue`` state: the
        hand-off (e.g. Kirsten's *Hand to Barney* wizard) triggers the bot in the same
        transaction — real time, not on the next cron tick (on odoo.sh cron workers run out of
        band and slowly). The 3-min dispatch cron stays as the catch-up belt for records whose
        inline dispatch failed (bot unbound, post error) or that were queued before activation."""
        res = super().write(vals)
        if "state_id" in vals:
            self._bot_dispatch_inline()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._bot_dispatch_inline()
        return records

    def _bot_dispatch_inline(self):
        """Dispatch every record of ``self`` that now sits in a bot ``queue`` state, inline in
        the caller's transaction — claim + flagged message + activity session commit (or roll
        back) WITH the hand-off write. Each record dispatches under its own savepoint: a failed
        dispatch rolls back cleanly and NEVER breaks the user's hand-off (the record stays
        queued; the cron belt retries). Runs sudo — the dispatch is system machinery (message
        post to the bot's channel + the activity session), not something the handing user needs
        rights for; parity with the cron, which runs as superuser. Opt out with context
        ``bot_no_inline_dispatch`` (tests exercising the raw queue/claim primitives)."""
        if self.env.context.get("bot_no_inline_dispatch"):
            return
        for record in self.filtered(lambda r: r.state_id.bot_stage == "queue"):
            try:
                with self.env.cr.savepoint():
                    record.sudo()._bot_dispatch_one()
            except Exception:  # noqa: BLE001 — never break the hand-off; the cron belt retries
                _logger.exception(
                    "inline bot dispatch failed for %s(%s) — record stays queued for the "
                    "dispatch cron belt", record._name, record.id)

    @api.model
    def bot_work_queue(self):
        """The bot-owned work waiting for an isolated agent run (the harness contract, generic).

        One dict per record in a ``queue`` bot-stage state, resolved to {res_model, res_id, state,
        claim_transition_id, in_progress_state, escalate_transition_id, expect_state_in,
        max_tool_turns, verbose} from the workflow shape + {skill, prompt, dto} from the domain
        ``_bot_task_spec()`` hook. A record whose workflow isn't bot-configured (no ``claim``
        transition) is skipped. No sudo — the caller is the bot user; kwargs are never named
        ``ids`` (the /json/2/ recordset selector)."""
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
        ``claim`` transition out of the queue state). The skill + prompt + max tool turns come
        DECLARATIVELY from the claim transition (``bot_skill``/``bot_prompt``/``bot_max_tool_turns``
        — the workflow states what the run does, beside the ``bot_role`` that states when), falling
        back to the ``_bot_task_spec`` hook; the bot-safe DTO always comes from the hook (it is
        computed record data). ``res_model``/``res_id`` name the WORKFLOW record itself — distinct
        from ``riverflow.service``'s own ``res_model``/``res_id`` fields, which point at the
        service's *subject* (e.g. a log entry)."""
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
            "res_model": self._name,
            "res_id": self.id,
            "state": state.name,
            "claim_transition_id": claim.id,
            "in_progress_state": in_progress.name,
            "escalate_transition_id": escalate.id if escalate else False,
            "expect_state_in": expect.mapped("name"),
            "skill": claim.bot_skill or spec.get("skill"),
            "prompt": claim.bot_prompt or spec.get("prompt", ""),
            "max_tool_turns": claim.bot_max_tool_turns or spec.get("max_tool_turns") or 0,
            "verbose": claim.bot_verbose,
            "dto": spec.get("dto") or {},
        }

    def _bot_task_spec(self):
        """Domain hook: the {skill, prompt, dto} for one record's isolated agent run. Base is
        generic/empty; an app module (e.g. crewradar_cuneus_sign for MFNL) overrides per record
        type to supply the bot-safe DTO (and, when the workflow doesn't declare them on the
        claim transition via ``bot_skill``/``bot_prompt``, the skill + anchored prompt)."""
        self.ensure_one()
        return {"skill": False, "prompt": "", "dto": {}}

    def _bot_lock_row(self):
        """Serialize concurrent claimants on THIS row: flush pending ORM writes, take the row lock
        (``FOR NO KEY UPDATE`` — the strength Odoo's own UPDATE takes, blocking, so the loser waits
        and then re-reads the winner's committed truth; unlike FOR UPDATE it doesn't block FK
        inserts referencing the row), then invalidate the cache so every re-check below reads the
        committed values, not a stale snapshot. The ORDER is load-bearing: flush → lock →
        invalidate."""
        self.ensure_one()
        self.env.cr.flush()  # flush ALL pending ORM writes so the lock sees current data
        self.env.cr.execute(
            f'SELECT id FROM "{self._table}" WHERE id = %s FOR NO KEY UPDATE', [self.id]
        )
        self.invalidate_recordset()

    @api.model
    def bot_claim(self, res_id, transition_id, work_token=None):
        """Advance ONE record through ``transition_id`` under the row lock — the single choke
        point for the harness claim (→ in-progress before running), the agent's work advance,
        the escalate (→ a human state on failure) and the reaper's timeout exit.

        CAS + token fence (checked against COMMITTED truth, in this order):

        * record/transition gone → ``{ok: False}``;
        * already in the target state → ``{ok: True, already: True}`` — NO token: a re-poll /
          replay must never be handed a live epoch (the running claim owns the record);
        * state ≠ the transition's source state → ``{ok: False}`` (CAS loss — someone advanced
          it under us);
        * exiting a bot ``in_progress`` state whose stored ``bot_claim_token`` doesn't match
          ``work_token`` → ``{ok: False, reason: 'stale work token'}`` — the zombie-run fence;
        * else the normal ORM ``record.write()`` (keeps ``_sync_workflow_with_state``, mail
          tracking, oteny_audit) → ``{ok: True, state}`` + ``token`` when the target is a bot
          ``in_progress`` state (the freshly minted epoch — only the claim WINNER sees it).

        Kwargs are never named ``ids`` (the /json/2/ recordset selector); ``res_id`` names the
        record on THIS model (the model is implied by the /json/2/<model>/bot_claim endpoint)."""
        record = self.browse(res_id).exists()
        transition = self.env["riverflow.transition"].browse(transition_id).exists()
        if not record or not transition:
            return {"ok": False, "reason": "unknown record or transition"}
        record._bot_lock_row()
        if not record.exists():
            return {"ok": False, "reason": "record deleted"}
        if record.state_id == transition.to_state_id:
            return {"ok": True, "already": True, "state": record.state_id.name}
        if transition.from_state_id and record.state_id != transition.from_state_id:
            return {"ok": False, "state": record.state_id.name,
                    "reason": f"record is in {record.state_id.name!r}, not "
                    f"{transition.from_state_id.name!r}"}
        if (record.state_id.bot_stage == "in_progress" and record.bot_claim_token
                and work_token != record.bot_claim_token):
            return {"ok": False, "state": record.state_id.name, "reason": "stale work token"}
        # Domain precondition: a real-world invariant the CAS/token fence can't express (e.g.
        # MFNL: no *Filed* without a captured filing proof). Runs under the row lock, so it is
        # model-independent — a weak agent that TRIES the advance is refused here, not trusted.
        guard = record._bot_claim_guard(transition)
        if guard:
            return {"ok": False, "state": record.state_id.name, "reason": guard}
        vals = {"state_id": transition.to_state_id.id}
        if transition.to_responsible_team_id:
            vals["responsible_team_id"] = transition.to_responsible_team_id.id
        record.write(vals)
        result = {"ok": True, "state": record.state_id.name}
        if record.bot_claim_token:
            # the target is a bot in_progress state — hand the WINNER its fresh epoch
            result["token"] = record.bot_claim_token
        return result

    def _bot_claim_guard(self, transition):
        """Server-side precondition for a bot advance — the ONE place a domain layer can REFUSE
        a ``bot_claim`` transition even when the CAS/token fence would allow it. Base: no guard
        (falsy). An app overrides it to enforce an invariant the workflow STATE alone can't — MFNL
        makes a *File* → *Filed* advance require a captured filing proof, so a fabricated/skipped
        "Filed" is structurally impossible regardless of which model drives the run. Return a short
        reason string to REFUSE (``bot_claim`` then returns ``{ok: False, reason}`` and does not
        advance); return a falsy value to allow."""
        return None

    @api.model
    def bot_run_claim(self, res_id, work_token):
        """Consume the ONE agent run of the current claim epoch — called by deterministic
        dispatcher code (the hh-discuss adapter / the webhook harness) BEFORE any LLM/session
        activity. Under the row lock: require a bot ``in_progress`` state + a matching
        ``work_token`` + ``bot_run_started_at`` unset, then stamp it. A second consume, a
        wrong/stale token, or a post-reap replay all return ``{ok: False}`` — at most one agent
        run per dispatch, across message replays and multiple gateway processes."""
        record = self.browse(res_id).exists()
        if not record:
            return {"ok": False, "reason": "unknown record"}
        record._bot_lock_row()
        if not record.exists():
            return {"ok": False, "reason": "record deleted"}
        if record.state_id.bot_stage != "in_progress":
            return {"ok": False, "state": record.state_id.name, "reason": "not in progress"}
        if not work_token or work_token != record.bot_claim_token:
            return {"ok": False, "reason": "stale work token"}
        if record.bot_run_started_at:
            return {"ok": False, "reason": "run already consumed"}
        record.bot_run_started_at = fields.Datetime.now()
        return {"ok": True, "state": record.state_id.name}

    @api.model
    def bot_token_check(self, res_id, work_token):
        """Read-only epoch probe for the RUNNING agent: ``{ok: True}`` iff the record is still in
        a bot ``in_progress`` state and ``work_token`` is its current ``bot_claim_token``. The
        skill runs this immediately before any irreversible action (portal submit) — not ok means
        the run was timed out/reaped and the work re-assigned, so it must STOP."""
        record = self.browse(res_id).exists()
        if not record:
            return {"ok": False, "reason": "unknown record"}
        if record.state_id.bot_stage != "in_progress":
            return {"ok": False, "state": record.state_id.name, "reason": "not in progress"}
        if not work_token or work_token != record.bot_claim_token:
            return {"ok": False, "reason": "stale work token"}
        return {"ok": True, "state": record.state_id.name}

    @api.model
    def _bot_reap_timeouts(self):
        """Escalate bot in-progress records stuck past their state's SLA — the timeout reaper, run by
        an ir.cron on each concrete workflow-bearing model. For every ``in_progress`` state with a
        positive ``bot_timeout_minutes``, any record whose ``bot_work_started_at`` is older than the
        SLA is advanced through that state's ``is_bot_timeout`` transition (the reaper's exit,
        distinct from the agent's own escalate). The reaper passes the token it READS as its
        ``work_token``: ``bot_claim`` re-checks it under the row lock, so a record whose run
        completed (or whose token rotated) between the read and the lock is a clean no-op — the
        reaper can never revert a just-completed record. Returns the count reaped. This is the
        backstop for a harness that died mid-run and never reported back."""
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
                claim = self.with_context(bot_reap=True).bot_claim(
                    record.id, timeout_transition.id, work_token=record.bot_claim_token)
                if claim.get("ok") and not claim.get("already"):
                    reaped += 1
        return reaped

    @api.model
    def bot_dispatch_queue(self):
        """Push each queued bot-owned record to its bot as an isolated turn (the Odoo-driven trigger
        that replaces the Oteny-side harness poll: the owner's Odoo asks the bot to act, and the bot's
        own channel poll picks it up — no external sweep, no webhook). The PRIMARY dispatch is the
        inline one on the hand-off write (``_bot_dispatch_inline`` — real time); this cron is the
        catch-up belt for records whose inline dispatch failed and for work queued before
        activation. Idempotent: the dispatch claims the record (→ its in-progress state), so it
        leaves the queue and is never re-dispatched. Returns the number dispatched. Run by an
        ir.cron on each concrete workflow-bearing model."""
        queue_states = self.env["riverflow.state"].search([("bot_stage", "=", "queue")])
        dispatched = 0
        if queue_states:
            for record in self.search([("state_id", "in", queue_states.ids)]):
                if record._bot_dispatch_one():
                    dispatched += 1
        # The belt for a lost dispatch: re-post an already-claimed record whose isolated run was
        # never consumed (the orphan a gateway-down window leaves) — same tick, safe by the fence.
        dispatched += self._bot_redispatch_stalled()
        return dispatched

    @api.model
    def _bot_redispatch_stalled(self):
        """Re-post the flagged dispatch for a claimed record whose isolated run was NEVER consumed
        (``bot_run_started_at`` unset) between the grace and the ceiling — the fast recovery for a
        dispatch lost while the bot's gateway was down (its poll marker seeds past the flagged
        message on reconnect, so it never self-recovers). Re-uses the STANDING claim epoch (no
        re-claim — the token holds). A run that DID start then died (``bot_run_started_at`` set) is
        NOT re-fired here — the consume fence would drop it — so the in-progress SLA reaper escalates
        it instead. Returns the count re-dispatched."""
        inprog = self.env["riverflow.state"].search([("bot_stage", "=", "in_progress")])
        if not inprog:
            return 0
        now = fields.Datetime.now()
        floor = now - timedelta(minutes=_BOT_REDISPATCH_CEILING_MINUTES)
        deadline = now - timedelta(minutes=_BOT_REDISPATCH_GRACE_MINUTES)
        stalled = self.search([
            ("state_id", "in", inprog.ids),
            ("bot_run_started_at", "=", False),          # the run was never consumed …
            ("bot_work_started_at", "!=", False),
            ("bot_work_started_at", "<", deadline),      # … and it has sat past the grace …
            ("bot_work_started_at", ">", floor),         # … but not so long the SLA reaper owns it
        ])
        count = 0
        for record in stalled:
            if record._bot_redispatch_one():
                count += 1
        return count

    def _bot_redispatch_one(self):
        """Re-post the flagged dispatch for THIS already-claimed, never-consumed in-progress record.
        Resolves the work item from the claim transition INTO the current state (reusing the standing
        ``bot_claim_token``) and hands it to the domain ``_bot_redispatch`` hook. True when re-fired."""
        self.ensure_one()
        item = self._bot_inprogress_work_item()
        if not item:
            return False
        return bool(self._bot_redispatch(item, self._bot_dispatch_prompt(item)))

    def _bot_inprogress_work_item(self):
        """The harness work item for a record ALREADY in its bot ``in_progress`` state (for a
        re-dispatch): the same shape as ``_bot_work_item`` but resolved from the claim transition
        INTO the current state, and carrying the STANDING ``bot_claim_token`` (no new claim). None
        when the current state isn't a bot in-progress state reachable by a claim transition, or the
        token is missing (nothing to re-fire)."""
        self.ensure_one()
        state = self.state_id
        if state.bot_stage != "in_progress" or not self.bot_claim_token:
            return None
        claim = self.env["riverflow.transition"].search(
            [("to_state_id", "=", state.id), ("bot_role", "=", "claim")], limit=1)
        if not claim:
            return None
        outgoing = state.from_transition_ids
        escalate = outgoing.filtered(lambda t: t.bot_role == "escalate")[:1]
        expect = outgoing.filtered(lambda t: t.bot_role == "work").mapped("to_state_id")
        spec = self._bot_task_spec()
        return {
            "res_model": self._name,
            "res_id": self.id,
            "state": state.name,
            "claim_transition_id": claim.id,
            "in_progress_state": state.name,
            "escalate_transition_id": escalate.id if escalate else False,
            "expect_state_in": expect.mapped("name"),
            "skill": claim.bot_skill or spec.get("skill"),
            "prompt": claim.bot_prompt or spec.get("prompt", ""),
            "max_tool_turns": claim.bot_max_tool_turns or spec.get("max_tool_turns") or 0,
            "verbose": claim.bot_verbose,
            "token": self.bot_claim_token,
            "dto": spec.get("dto") or {},
        }

    def _bot_redispatch(self, item, prompt):
        """Domain hook: RE-post the flagged dispatch for an already-claimed record using the
        standing token in ``item['token']`` — NO re-claim (the record is already in-progress; only
        the isolated run was lost). Base is a no-op (returns False); an app that wires a bot
        overrides it to re-post the flagged message to the bot's channel with that token. Kept off
        ``oteny_bot`` here so riverflow stays a pure engine."""
        return False

    def _bot_dispatch_one(self):
        """Resolve THIS queued record's work item and hand it to the domain ``_bot_dispatch``
        hook (the shared leg of the inline dispatch and the cron belt). True when dispatched."""
        self.ensure_one()
        item = self._bot_work_item()
        return bool(item and self._bot_dispatch(item, self._bot_dispatch_prompt(item)))

    def _bot_dispatch_prompt(self, item):
        """The THIN isolated-turn instruction for one queued record — names the skill + the record
        + the transition's declared task instruction (``bot_prompt``, a static instruction — no
        record data), NEVER the DTO (the bot fetches that itself over its uplink, so no PII rides
        the channel). Without the declared prompt the workflow's per-transition instruction (e.g.
        the MFNL unattended contract) would reach only the webhook escape hatch, not the primary
        Discuss dispatch."""
        self.ensure_one()
        thin = (f"Run the '{item.get('skill') or ''}' task for {item.get('state')} record "
                f"#{self.id}. Load the skill, fetch this record's details over your uplink, complete "
                "the work, and advance the record. Act only on this one record.")
        declared = (item.get("prompt") or "").strip()
        return f"{thin}\n{declared}" if declared else thin

    def _bot_dispatch(self, item, prompt):
        """Domain hook: dispatch ONE isolated turn for this record (its work ``item`` + a thin
        ``prompt``) to its bot. Base is a no-op (returns False) — an app that wires a bot (e.g.
        crewradar → the oteny_bot Discuss seam) overrides it to CLAIM the record (via
        ``item['claim_transition_id']``) and post the flagged message to the bot's channel; a truthy
        return counts it dispatched. The claim's fresh ``token`` MUST ride the flagged message (the
        oteny_bot work header) — no token, no dispatch. Kept off ``oteny_bot`` here so riverflow
        stays a pure engine."""
        return False
