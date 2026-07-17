{
    "name": "Oteny Business Bot",
    "version": "19.0.1.4",  # 19.0.1.3: the login-dance latch — login_dance_until / login_dance_user_id + the per-bot dance/run mutex (login_dance_hold / login_dance_blocks_run / login_dance_start / login_dance_stop). A bot's isolated runs and a human's attended sign-in share one cookie profile, so they must take turns; one Postgres advisory key per bot orders them (EXCLUSIVE + blocking on the dance side, try-SHARED + defer-never-wait on the run side), and the latch's 15-min TTL means an abandoned dance unlatches the bot on wall clock alone — no cron, no operator. Additive columns; no migration.
    "depends": ["base", "mail"],
    "author": "Oteny",
    "category": "Productivity",
    "summary": "Generic host for an Oteny business bot: talk to it over Discuss, review its activity log.",
    "description": """
The generic Odoo side of an Oteny business bot — the layer any Odoo instance installs to host a
bot it talks to over Discuss, independent of any workflow engine or domain.

An Oteny business bot runs on its own isolated machine and reaches this Odoo over a scoped
/json/2/ uplink; because it is external, it writes its activity back here so the bot's owner (an
Odoo user) can review every exchange without leaving Odoo — the same visibility an in-process
ai.agent (Wilma) has natively.

Models: oteny.bot (a bot connected to this Odoo), oteny.bot.session (one request/response
exchange + outcome), oteny.bot.turn (per-LLM-call detail). The record_activity() seam is what the
bot calls over /json/2/ to log an exchange. A session's origin is a soft (model, id) reference, so
a workflow module (riverflow) or an app module attaches its own record without this addon
depending on it.
""",
    "data": [
        "security/oteny_bot_groups.xml",
        "security/ir.model.access.csv",
        "views/oteny_bot_views.xml",
    ],
    "auto_install": False,
    "license": "OEEL-1",
}
