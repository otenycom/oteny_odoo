"""Contract + SQL-replay for oteny_bot/data/neutralize.sql (WP4).

A restore without this SQL would keep live broker tokens and an uplink_ref
pointing at the production bot. The SQL must list every param the broker client
and set_broker_config know about, and must clear uplink_ref while keeping the
seeded discuss_channel_id / bot_user_id so the next provision rebinds.
"""
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.oteny_bot.models.oteny_broker import (
    BASE_PARAM,
    TOKEN_LIVE_WATCH_PARAM,
    TOKEN_PARAM,
    TOKEN_REPLAY_VIEW_PARAM,
)

LOGIN_URL_PARAM = "posted_workers_nl_url"
NEUTRALIZE_SQL = Path(__file__).resolve().parents[1] / "data" / "neutralize.sql"

# Every broker / portal param the client + provisioner write — the SQL must name them all.
BROKER_PARAMS = (
    BASE_PARAM,
    TOKEN_PARAM,
    TOKEN_LIVE_WATCH_PARAM,
    TOKEN_REPLAY_VIEW_PARAM,
    LOGIN_URL_PARAM,
)


@tagged("oteny_bot", "post_install", "-at_install", "test_barney_neutralize")
class TestBarneyNeutralize(TransactionCase):
    def test_sql_lists_every_broker_param_name(self):
        """A fourth broker param can never be added without disconnecting it too."""
        sql = NEUTRALIZE_SQL.read_text()
        for key in BROKER_PARAMS:
            self.assertIn(f"'{key}'", sql, f"{key} missing from neutralize.sql")

    def test_sql_replay_clears_params_and_unbinds_uplink(self):
        icp = self.env["ir.config_parameter"].sudo()
        for key in BROKER_PARAMS:
            icp.set_param(key, f"seed-{key}")

        channel = self.env["discuss.channel"].create({"name": "HR-and-Barney (neutralize test)"})
        bot = self.env["oteny.bot"].sudo().create({
            "name": "Barney",
            "uplink_ref": "hh0prod",
            "discuss_channel_id": channel.id,
            "bot_user_id": self.env.user.id,
            "login_dance_token": "dance-token",
            "login_dance_user_id": self.env.user.id,
        })

        self.env.cr.execute(NEUTRALIZE_SQL.read_text())
        icp.invalidate_model()
        bot.invalidate_recordset()

        for key in BROKER_PARAMS:
            self.assertFalse(
                icp.get_param(key),
                f"{key} should be gone after neutralize.sql",
            )
        self.assertFalse(bot.uplink_ref)
        self.assertFalse(bot.login_dance_token)
        self.assertFalse(bot.login_dance_user_id)
        self.assertFalse(bot.login_dance_until)
        self.assertEqual(bot.discuss_channel_id, channel)
        self.assertEqual(bot.bot_user_id, self.env.user)
