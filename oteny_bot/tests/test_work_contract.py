"""The work contract without an engine: every verb fails closed and names why."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("oteny_bot", "post_install", "-at_install")
class TestWorkContractNoEngine(TransactionCase):
    def setUp(self):
        super().setUp()
        self.bot = self.env["oteny.bot"].create({"name": "Acme Bot", "bot_user_id": self.env.uid})
        self.partner = self.env["res.partner"].create({"name": "Fixture Contact"})
        self.session = self.env["oteny.bot.session"].create({
            "bot_id": self.bot.id, "name": "Do a thing", "kind": "isolated_turn",
            "outcome": "dispatched", "work_token": "tok-noengine",
            "origin_model": "res.partner", "origin_res_id": self.partner.id,
        })

    def test_unknown_token_is_refused_by_every_verb(self):
        Bot = self.env["oteny.bot"]
        self.assertFalse(Bot.work_consume("nope")["ok"])
        probe = Bot.work_probe("nope")
        self.assertFalse(probe["ok"]); self.assertFalse(probe["mine"])
        self.assertFalse(Bot.work_release("nope")["ok"])

    def test_a_record_without_an_engine_fails_closed(self):
        Bot = self.env["oteny.bot"]
        out = Bot.work_consume("tok-noengine")
        self.assertFalse(out["ok"]); self.assertIn("no engine", out["reason"])
        probe = Bot.work_probe("tok-noengine")
        self.assertFalse(probe["ok"]); self.assertFalse(probe["mine"]); self.assertIn("no engine", probe["reason"])
        rel = Bot.work_release("tok-noengine", reason="hung")
        self.assertFalse(rel["ok"]); self.assertFalse(rel["released"])

    def test_release_records_the_run_even_without_an_engine(self):
        self.env["oteny.bot"].work_release(
            "tok-noengine", reason="hung", run={"outcome": "error", "outcome_detail": "model stream hung"})
        self.assertEqual(self.session.outcome, "error")
        self.assertEqual(self.session.outcome_detail, "model stream hung")
