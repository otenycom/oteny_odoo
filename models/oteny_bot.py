"""The generic Oteny business-bot models (Layer 1 — no workflow / domain coupling).

An Oteny bot is external (its own machine), so it writes its activity back into this Odoo over
the /json/2/ uplink; the owner reviews it here. Everything is domain-agnostic: a session's origin
is a soft ``(model, res_id)`` reference so a workflow engine or an app module can attach a session
to its own record without this addon depending on it.
"""

import secrets
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import _, Command, api, fields, models
from odoo.exceptions import UserError

# The leading marker that tells the bot's gateway to run a Discuss message as a FRESH, isolated
# agent turn (its own session) instead of a turn in the accumulating channel chat — the Discuss
# trigger that replaces the Oteny-side harness poll. WIRE CONTRACT: this string MUST match the
# hh-discuss adapter's ISOLATED_SENTINEL (hermeshost catalog/plugins/hh-discuss/discuss_wire.py).
ISOLATED_TURN_SENTINEL = "[oteny:isolated]"

# The machine-readable work header a WORK-carrying dispatch places right after the sentinel:
# names the workflow record + the claim epoch's dispatch token. WIRE CONTRACT: the format MUST
# stay parseable by the hh-discuss adapter's WORK_HEADER_RE (hermeshost discuss_wire.py) —
# `\[oteny:work:([\w.]+):(\d+):([A-Za-z0-9_-]+)\]`. The adapter consumes the token
# (bot_run_claim) BEFORE starting the agent run, so a replayed message can never run twice;
# an old adapter sees the header as prose (harmless), and a headerless isolated message keeps
# working (plain conversation / scenario driver).
WORK_HEADER_FMT = "[oteny:work:{res_model}:{res_id}:{token}]"

# An OPTIONAL flag a dispatch may carry (right after the isolated sentinel) to ask the run to
# STREAM per-tool narration into the channel live — a noisy debug trace only wanted while a Talent
# author is diagnosing a run. Off by default (the end-of-run summary always lands regardless).
# WIRE CONTRACT: must match the hh-discuss adapter's VERBOSE_SENTINEL (hermeshost discuss_wire.py),
# parity-pinned in that repo's tests/test_discuss_adapter.py.
VERBOSE_SENTINEL = "[oteny:verbose]"

# The human/agent-readable token instructions appended to a work-carrying dispatch. The token is
# the run's proof of its claim epoch: it must ride every bot_claim advance/escalate, and the
# skill must probe bot_token_check before anything irreversible.
WORK_TOKEN_TRAILER = (
    "\nYour work token is {token}. Pass work_token={token} on every bot_claim "
    "advance/escalate. Run bot_token_check immediately before any irreversible action "
    "(portal submit) — if not ok, STOP: you were timed out and the work re-assigned."
)

# How long a started attended-login DANCE latches the bot's dispatch path before it expires by
# itself. 15 min mirrors the Oteny broker's own handoff window (browser_handoff_minutes) — a
# dance that outlives the browser session it minted is over regardless of what the human does.
# The TTL is what makes the latch LIVENESS-SAFE: no OK, no cancel, a closed laptop, a crashed
# browser — the bot resumes dispatching on wall clock alone, with no cron and no operator.
LOGIN_DANCE_MINUTES = 15


class OtenyBot(models.Model):
    _name = "oteny.bot"
    _description = "Oteny Business Bot"
    _order = "name"
    # one bot per tenant reference — the write-back's ensure_bot relies on this to be a true upsert
    # (a check-then-create alone races under overlapping sweeps). NULL uplink_ref may repeat (a
    # manually-created bot without an uplink), per Postgres NULL semantics. Odoo 19 constraint style.
    _uplink_ref_uniq = models.Constraint(
        "unique(uplink_ref)",
        "An Oteny bot's uplink reference must be unique.",
    )

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
    login_dance_until = fields.Datetime(
        "Login Dance Until", copy=False,
        help="Set while a human is completing an attended sign-in for this bot (the 'open a "
        "login browser → sign in → save' dance). While it is in the FUTURE the bot's dispatch "
        "path is latched: no new isolated run is dispatched and no dispatched run may start, so "
        "the human's browser session and the bot's never overlap. Cleared on save/cancel and "
        "EXPIRES BY ITSELF — an abandoned dance unlatches the bot on wall clock alone, with no "
        "cron and no operator.")
    login_dance_user_id = fields.Many2one(
        "res.users", string="Login Dance By", copy=False,
        help="Who started the login dance currently holding the latch — so a second person is "
        "told WHO is signing in rather than just 'busy'.")
    login_dance_token = fields.Char(
        "Login Dance Token", copy=False,
        help="The epoch of ONE dance: minted on every login_dance_start and required by "
        "login_dance_stop, which is a COMPARE-and-clear. The latch is per-BOT but the screens "
        "that release it are per-user and per-record, so 'stop the dance' must mean 'stop MY "
        "dance' — without the epoch, anyone's Cancel would release whoever's dance was live and "
        "re-open the run/login overlap the latch exists to close. Same fence as bot_claim_token.")

    @api.depends("session_ids")
    def _compute_session_count(self):
        for bot in self:
            bot.session_count = len(bot.session_ids)

    # --- the dance/run mutex (multi-user concurrency) ------------------------------------ #
    # A bot's browser does two kinds of work that must never overlap: its OWN isolated runs
    # (already serialized one-at-a-time on its machine) and a HUMAN's attended login. They
    # share one cookie profile, so an overlap means the login's flush clobbers the run's
    # session — or the login's cleanup kills the run's live browser mid-filing. The two take
    # turns via ONE per-bot Postgres advisory lock + this TTL'd latch:
    #
    #   dance side (login_dance_hold)  → EXCLUSIVE, blocking. It is the FIRST lock its caller
    #                                    takes, so it can never be part of a cycle.
    #   run side  (login_dance_blocks_run) → try-SHARED, NEVER waits. Contention means DEFER,
    #                                    which is free: the bot_dispatch_queue cron re-drives
    #                                    a deferred dispatch. Shared, so concurrent dispatches
    #                                    for one bot don't exclude each OTHER — only the dance.
    #
    # No deadlock is constructible: only the dance ever waits, and it waits holding nothing.

    def _login_dance_lock_key(self):
        """The deterministic per-bot key both sides of the dance/run mutex hash. ONE key per
        bot and one only — a single global lock ordering, so there is no second key to invert
        it against."""
        self.ensure_one()
        return f"oteny.bot:{self.id}:dispatch"

    def login_dance_active(self):
        """True while a login dance holds the latch — set AND still in the future. Expiry needs
        no cron and no sweep: the comparison against ``now`` IS the expiry."""
        self.ensure_one()
        return bool(self.login_dance_until and self.login_dance_until > fields.Datetime.now())

    def login_dance_hold(self):
        """DANCE side: take this bot's dance/run mutex EXCLUSIVELY for the caller's transaction,
        then re-read the latch from COMMITTED truth. flush → lock → invalidate, the same
        load-bearing order as riverflow's ``_bot_lock_row``: a read taken before the lock could
        be a pre-lock snapshot.

        Postgres releases the lock when the transaction ends, so it stands across whatever the
        caller does next (for the login gate: the broker mint). That is deliberate — a dispatch
        must not slip in between the admission check and the latch — and it costs nothing,
        because nothing that matters waits on it (the run side tries and defers). The only
        possible waiter is a SECOND dance start, bounded by the first's own HTTP timeout."""
        self.ensure_one()
        self.env.cr.flush()
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))", [self._login_dance_lock_key()])
        self.invalidate_recordset(["login_dance_until", "login_dance_user_id"])

    def login_dance_blocks_run(self):
        """RUN side: True when NO isolated run may be dispatched or started for this bot right
        now — either a dance holds the latch, or one is being taken THIS INSTANT (the mutex is
        held exclusively and the latch is about to appear).

        NEVER waits. It TRIES the shared lock and reads contention as a defer, so a dispatch is
        only ever delayed (the 3-min ``bot_dispatch_queue`` cron re-drives it), never failed —
        and a dispatch can never sit in a lock cycle. Callers must treat True as 'try again
        later', never as an error."""
        self.ensure_one()
        self.env.cr.flush()
        self.env.cr.execute(
            "SELECT pg_try_advisory_xact_lock_shared(hashtext(%s))",
            [self._login_dance_lock_key()])
        if not self.env.cr.fetchone()[0]:
            return True  # a dance start owns the mutex right now — defer, don't wait
        self.invalidate_recordset(["login_dance_until", "login_dance_user_id"])
        return self.login_dance_active()

    def login_dance_start(self, minutes=None):
        """Latch the bot for an attended login dance (TTL'd — see LOGIN_DANCE_MINUTES) and return
        the dance's EPOCH TOKEN. The caller MUST hold the mutex (``login_dance_hold``) so the latch
        and any concurrent dispatch's latch-read are ordered.

        The token is the caller's proof of ownership: keep it and hand it back to
        ``login_dance_stop``. A second dance start (a takeover — the newest click wins, matching the
        broker's handoff supersede) mints a FRESH token, which is exactly what makes the superseded
        screen's later Cancel/OK a no-op instead of a release of somebody else's live dance.

        sudo: writing the bot is manager-only, but starting a dance is an HR act on a record the
        HR user may only read."""
        self.ensure_one()
        token = secrets.token_urlsafe(9)
        self.sudo().write({
            "login_dance_until": fields.Datetime.now() + timedelta(minutes=minutes or LOGIN_DANCE_MINUTES),
            "login_dance_user_id": self.env.uid,
            "login_dance_token": token,
        })
        return token

    def login_dance_stop(self, token):
        """COMPARE-and-clear: release the latch ONLY if ``token`` is the CURRENT dance's epoch.
        Returns True when it released, False when it was somebody else's dance (or none).

        The compare is the whole point. The latch is per-BOT, but the screens that release it are
        per-user and per-record and there are several people working at once — so an unconditional
        clear would mean *any* Cancel releases *whoever* is mid-sign-in, dropping a run straight
        into their login and re-opening the exact overlap this latch exists to close. Owning the
        dance, not merely having a screen open, is what earns the release.

        Takes the mutex for the same reason ``login_dance_start`` needs it: without it, a stop that
        read a matching token could still land its write AFTER a concurrent takeover committed, and
        destroy the new dance's latch. flush → lock → invalidate, then compare against committed
        truth. Never required for correctness (the TTL is the backstop) — it just returns the bot to
        work now instead of in 15 minutes."""
        self.ensure_one()
        if not token:
            return False
        self.login_dance_hold()
        if token != self.sudo().login_dance_token:
            return False
        self.sudo().write({
            "login_dance_until": False, "login_dance_user_id": False, "login_dance_token": False,
        })
        return True

    @api.model
    def record_activity(self, uplink_ref, session, turns=None):
        """The seam the bot calls over /json/2/ to log ONE exchange (owner-visibility, generic).

        Creates an ``oteny.bot.session`` (+ optional child ``turns``) for the bot identified by
        ``uplink_ref``. ``sudo`` internally — the bot's least-privilege key need not carry write
        on the log models. The security boundary is ``bot_id``: a caller can only ever log under the
        bot its OWN ``uplink_ref`` resolves to (an uplink reaches only its own owner's Odoo), never
        another bot's. The ``origin`` (``origin_model`` + ``origin_res_id``) is an ADVISORY soft
        reference the bot self-reports — it is not validated here (this addon is domain-agnostic and
        the record may since be gone), and a bot that can log is one that already has write access to
        those records, so a mis-stated origin is a self-report artefact, not a privilege escalation.
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

    @api.model
    def record_run(self, work_token, run=None, turns=None):
        """The seam the bot calls at the END of an isolated dispatch run to fill the open,
        token-matched session with its verdict + forensics (D174 hybrid — "a run must never be
        silent"). It ADOPTS the ``dispatched`` session opened at dispatch (correlated by the claim
        epoch's ``work_token``) instead of forking a new one, so the customer sees ONE row that
        goes from *Dispatched* → its real outcome + reason seconds after the run — no 120-min
        timeout wait, no SSH.

        Field policy: forensic fields (``response``, ``duration_s``) always attach; the run's
        SELF-ASSESSED ``outcome``/``outcome_detail`` are written only while the session is still
        ``dispatched`` — i.e. the workflow state machine has not already closed it. So a hard
        failure (403 spiral, empty reply → ``error`` + the tool-failure breakdown) lands its
        reason, but a state-machine ``ok``/``escalated`` (the record advanced) is never downgraded
        by a softer bot guess. Possessing ``work_token`` proves the claim epoch (same trust model
        as ``bot_claim``); ``sudo`` internally (the bot's least-privilege key need not carry write
        on the log models). Kwargs are never named ``ids``. Returns ``{ok, session_id}``."""
        if not work_token:
            return {"ok": False, "reason": "record_run needs a work_token"}
        Session = self.env["oteny.bot.session"].sudo()
        session = Session.search([("work_token", "=", work_token)], order="id desc", limit=1)
        if not session:
            return {"ok": False, "reason": f"no session for work_token {work_token!r}"}
        allowed = set(Session._fields)
        vals = {k: v for k, v in (run or {}).items() if k in allowed}
        # Never let a soft self-report clobber a terminal outcome the state machine already proved.
        if session.outcome not in ("dispatched", False):
            vals.pop("outcome", None)
            vals.pop("outcome_detail", None)
        if turns:
            tallowed = set(self.env["oteny.bot.turn"]._fields)
            # Replace any prior turns (a re-report is idempotent, not additive).
            vals["turn_ids"] = [Command.clear()] + [
                Command.create({k: v for k, v in (t or {}).items() if k in tallowed})
                for t in turns]
        session.write(vals)
        return {"ok": True, "session_id": session.id}

    @api.model
    def ensure_bot(self, uplink_ref, name=None):
        """Idempotently ensure an ``oteny.bot`` exists for ``uplink_ref`` (owner-visibility, generic).

        The bot lives outside this Odoo (its own machine); it has no way to pre-seed its own record
        here, so the uplink calls this the first time the bot acts — the "Barney" record then simply
        appears in the owner's Odoo, ready to accrue activity. ``sudo`` internally (the bot's
        least-privilege key need not carry create on ``oteny.bot``); a true upsert on ``uplink_ref``,
        never renamed on a re-call (the owner may have relabelled it). The ``unique(uplink_ref)``
        constraint makes it race-safe: two overlapping sweeps that both miss the search collide on
        create, and the loser returns the winner's record rather than forking the log. Kwargs are
        never named ``ids`` (the /json/2/ recordset selector). Returns ``{ok, bot_id, created}``."""
        bot = self.sudo().search([("uplink_ref", "=", uplink_ref)], limit=1)
        if bot:
            return {"ok": True, "bot_id": bot.id, "created": False}
        # Adopt a pre-seeded bot: a business app (e.g. crewradar) seeds the oteny.bot with its
        # discuss_channel_id + bot_user_id but no uplink_ref (it can't know the Oteny tenant ref).
        # The first write-back — authenticated AS that bot user — claims the seeded record by
        # setting its ref, so the channel-bound record is reused (the dispatch needs it), not forked.
        seeded = self.sudo().search(
            [("bot_user_id", "=", self.env.uid), ("uplink_ref", "in", (False, ""))], limit=1)
        if seeded:
            seeded.uplink_ref = uplink_ref
            return {"ok": True, "bot_id": seeded.id, "created": False, "adopted": True}
        try:
            with self.env.cr.savepoint():
                bot = self.sudo().create({"uplink_ref": uplink_ref, "name": name or uplink_ref})
                bot.flush_recordset()   # force the INSERT so a unique-violation fires in the savepoint
            return {"ok": True, "bot_id": bot.id, "created": True}
        except IntegrityError:
            # a concurrent ensure_bot won the create race (unique(uplink_ref)); return its record.
            bot = self.sudo().search([("uplink_ref", "=", uplink_ref)], limit=1)
            if bot:
                return {"ok": True, "bot_id": bot.id, "created": False}
            return {"ok": False, "reason": f"could not ensure oteny.bot for {uplink_ref!r}"}

    def dispatch_isolated_turn(self, prompt, work=None, verbose=False):
        """Dispatch ONE isolated agent turn to this bot over Discuss (the trigger that replaces the
        Oteny-side harness poll). Posts ``<sentinel> [work header] {prompt} [token trailer]`` into
        the bot's channel; the bot's gateway poll picks it up and runs it as a FRESH, isolated
        session — not a turn in the accumulating team chat. The dispatch is a real channel message,
        so the owner sees it. ``work`` (optional) is the token-fenced work reference
        ``{res_model, res_id, token}`` from a winning ``bot_claim``: it renders the machine
        header the adapter consumes (bot_run_claim — at most one run per dispatch) plus the token
        trailer the run needs for its advances. Requires ``discuss_channel_id``. Returns
        ``{ok, message_id}`` (``{ok: False}`` if unbound)."""
        self.ensure_one()
        if not self.discuss_channel_id:
            return {"ok": False, "reason": "bot has no discuss_channel_id"}
        head = ISOLATED_TURN_SENTINEL
        if verbose:
            # opt-in: ask the run to narrate each uplink tool call into the channel live
            head += " " + VERBOSE_SENTINEL
        tail = ""
        if work:
            head += " " + WORK_HEADER_FMT.format(
                res_model=work["res_model"], res_id=work["res_id"], token=work["token"])
            tail = WORK_TOKEN_TRAILER.format(token=work["token"])
        body = f"{head} {(prompt or '').strip()}{tail}".strip()
        msg = self.discuss_channel_id.sudo().message_post(
            body=body, message_type="comment", subtype_xmlid="mail.mt_comment")
        return {"ok": True, "message_id": msg.id}

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
        [("dispatched", "Dispatched"), ("ok", "OK"), ("halted", "Halted / handed back"),
         ("escalated", "Escalated"), ("timeout", "Timed out"), ("error", "Error")],
        index=True, readonly=True,
        help="dispatched = the isolated turn was posted and is (presumed) running; the workflow "
        "layer closes it deterministically to ok / escalated / timeout when the record exits its "
        "bot in-progress state.")
    outcome_detail = fields.Char(readonly=True)
    work_token = fields.Char(
        "Work Token", index=True, readonly=True, copy=False,
        help="The dispatch token of the claim epoch this session records (D174 write-back). Set "
        "at dispatch; the workflow layer matches on it to close the session when the record "
        "exits the bot in-progress state — exact correlation, no LLM self-report needed.")
    # Generic origin — the Odoo record this exchange is about (e.g. a riverflow.service). A SOFT
    # reference (model name + id), not a Many2one, so this generic addon never depends on the
    # consuming module's models; the workflow/app layer sets these + renders an embedded view.
    origin_model = fields.Char("Origin Model", index=True, readonly=True)
    origin_res_id = fields.Integer("Origin Res ID", index=True, readonly=True)
    started_at = fields.Datetime(default=fields.Datetime.now, index=True, readonly=True)
    duration_s = fields.Float("Duration (s)", readonly=True)
    # Opaque broker browser session ids this run used (never live-view URLs — R3).
    # Written by the bot via record_run; powers Watch live / Replay from Bot Activity.
    browser_session_ids = fields.Json(
        "Browser Session Ids", readonly=True, copy=False,
        help="Opaque cloud-browser session ids for this activity. Viewer URLs are "
        "minted on click and never stored.")
    browser_status = fields.Char(
        "Browser", compute="_compute_browser_status",
        help="Plain-language status of the cloud browser for this activity.")
    has_browser_session = fields.Boolean(
        compute="_compute_browser_status",
        help="True when this activity linked at least one cloud-browser session.")
    turn_ids = fields.One2many("oteny.bot.turn", "session_id", string="Turns", readonly=True)
    turn_count = fields.Integer(compute="_compute_turn_metrics")
    tool_call_count = fields.Integer(compute="_compute_turn_metrics")

    # Access window for forensic replay (matches the platform 48h promise).
    _BROWSER_REPLAY_HOURS = 48

    @api.depends("turn_ids", "turn_ids.tool_call_count")
    def _compute_turn_metrics(self):
        for s in self:
            s.turn_count = len(s.turn_ids)
            s.tool_call_count = sum(s.turn_ids.mapped("tool_call_count"))

    @api.depends(
        "browser_session_ids", "outcome", "started_at", "duration_s",
    )
    def _compute_browser_status(self):
        now = fields.Datetime.now()
        for s in self:
            ids = s.browser_session_ids or []
            if not isinstance(ids, list):
                ids = []
            s.has_browser_session = bool(ids)
            if not ids:
                s.browser_status = _("No browser used")
                continue
            if s.outcome == "dispatched":
                s.browser_status = _("Live now")
                continue
            closed = s.started_at
            if closed and s.duration_s:
                closed = closed + timedelta(seconds=int(s.duration_s))
            if closed:
                # hours left in the 48h access window (not a deletion claim).
                age_h = (now - closed).total_seconds() / 3600.0
                left = s._BROWSER_REPLAY_HOURS - age_h
                if left > 0:
                    s.browser_status = _(
                        "Replay available · about %(hours)sh left",
                        hours=max(1, int(round(left))),
                    )
                    continue
            s.browser_status = _("Browser session ended")

    def _can_mint_browser_viewer(self):
        """HR users (and bot managers) may mint a Watch/Replay URL."""
        user = self.env.user
        if user.has_group("oteny_bot.group_oteny_bot_manager"):
            return True
        return user.has_group("hr.group_hr_user")

    def _latest_browser_session_id(self):
        self.ensure_one()
        ids = self.browser_session_ids or []
        if not isinstance(ids, list):
            return None
        for sid in reversed(ids):
            if isinstance(sid, str) and sid:
                return sid
        return None

    def action_watch_live_browser(self):
        """Mint a read-only live view and open it in a new tab (R3 — URL not stored)."""
        self.ensure_one()
        if not self._can_mint_browser_viewer():
            raise UserError(_(
                "Only HR users can open the live browser view."
            ))
        sid = self._latest_browser_session_id()
        if not sid:
            raise UserError(_(
                "This activity did not use a cloud browser, so there is nothing to watch."
            ))
        Broker = self.env["oteny.broker.client"]
        try:
            res = Broker._broker_post(
                f"/v1/browser/session/{sid}/viewer",
                purpose="live-watch",
            )
        except UserError as exc:
            # Friendly wrap — never surface HTTP codes / Steel / session ids.
            msg = str(exc)
            if "404" in msg or "unknown session" in msg.lower():
                raise UserError(_(
                    "The live browser is no longer available. "
                    "If a recording is still within the retention window, try Replay."
                )) from exc
            raise UserError(_(
                "Could not open the live browser view. "
                "Try again in a moment, or ask an administrator if this keeps happening."
            )) from exc
        url = (res or {}).get("session_viewer_url") or ""
        if not url:
            raise UserError(_(
                "The live browser is no longer available."
            ))
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_replay_browser(self):
        """Mint a 48h forensic replay URL and open it (R3 — URL not stored)."""
        self.ensure_one()
        if not self._can_mint_browser_viewer():
            raise UserError(_(
                "Only HR users can open a browser replay."
            ))
        sid = self._latest_browser_session_id()
        if not sid:
            raise UserError(_(
                "This activity did not use a cloud browser, so there is nothing to replay."
            ))
        Broker = self.env["oteny.broker.client"]
        try:
            res = Broker._broker_post(
                f"/v1/browser/session/{sid}/replay",
                purpose="replay-view",
            )
        except UserError as exc:
            msg = str(exc)
            if "410" in msg or "expired" in msg.lower():
                raise UserError(_(
                    "The browser recording is no longer available "
                    "(the access window has closed)."
                )) from exc
            if "404" in msg or "unknown session" in msg.lower():
                raise UserError(_(
                    "No browser recording is available for this activity."
                )) from exc
            if "501" in msg or "not implemented" in msg.lower() or "unavailable" in msg.lower():
                raise UserError(_(
                    "Browser replay is not available yet on this environment."
                )) from exc
            raise UserError(_(
                "Could not open the browser replay. "
                "Try again in a moment, or ask an administrator if this keeps happening."
            )) from exc
        url = (res or {}).get("session_viewer_url") or (res or {}).get("replay_url") or ""
        if not url:
            raise UserError(_(
                "No browser recording is available for this activity."
            ))
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }


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
