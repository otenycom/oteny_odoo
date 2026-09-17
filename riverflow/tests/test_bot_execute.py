"""Generic riverflow execute. Same strip, same wizard, same footer.

A person and a bot share ``transition_buttons_json``. Open is
``_prepare_transition_action`` then ``oteny.form.session`` ``open``.
Act is that photo's ``save`` plus the wizard ``action_save``.
``bot_claim`` is open-and-save with no pause.

This file names no client workflow.
"""

from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "riverflow", "test_bot_execute")
class TestBotExecute(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Service = cls.env["riverflow.service"]
        State = cls.env["riverflow.state"]
        Workflow = cls.env["riverflow.workflow"]
        Transition = cls.env["riverflow.transition"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        default_action = cls.env.ref("riverflow.transition_action_default")
        email_action = cls.env.ref("riverflow.transition_action_email_sender")

        cls.workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "Test Execute WF",
        })
        cls.state_draft = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Draft",
            "sequence": 10,
        })
        cls.state_ready = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Ready",
            "sequence": 20,
        })
        cls.state_closed = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Closed",
            "sequence": 30,
            "is_end_state": True,
        })
        cls.state_run = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Running",
            "sequence": 40,
            "bot_stage": "in_progress",
            "is_owned_by_bot": True,
            "bot_timeout_minutes": 30,
        })
        cls.trans_mark_today = Transition.create({
            "name": "Mark today",
            "from_state_id": cls.state_draft.id,
            "to_state_id": cls.state_ready.id,
            "action_id": default_action.id,
            "action_context": "{'set_deadline_to_today': True}",
            "sequence": 10,
        })
        cls.trans_continue = Transition.create({
            "name": "Continue",
            "from_state_id": cls.state_ready.id,
            "to_state_id": cls.state_closed.id,
            "action_id": default_action.id,
            "sequence": 10,
        })
        cls.template = cls.env["mail.template"].create({
            "name": "Execute Note",
            "model_id": service_model.id,
            "subject": "Execute note subject",
            "body_html": "<p>Execute note body</p>",
        })
        cls.trans_send_note = Transition.create({
            "name": "Send note",
            "from_state_id": cls.state_ready.id,
            "to_state_id": cls.state_closed.id,
            "action_id": email_action.id,
            "mail_template_id": cls.template.id,
            "action_context": (
                "{'keep_service_name': True, "
                "'set_deadline_relative': {'from': 'root', 'days': -1}}"
            ),
            "sequence": 20,
        })
        cls.trans_hand_back = Transition.create({
            "name": "Hand back",
            "from_state_id": cls.state_run.id,
            "to_state_id": cls.state_closed.id,
            "action_id": default_action.id,
            "sequence": 10,
        })
        cls.Service = Service
        cls.recipient = cls.env["res.partner"].create({
            "name": "Execute Recipient",
            "email": "execute-recipient@example.com",
        })

    def _make(self, name, state):
        return self.Service.with_context(bot_no_inline_dispatch=True).create({
            "name": name,
            "workflow_id": self.workflow.id,
            "state_id": state.id,
            "company_id": self.env.company.id,
        })

    def _prepare(self, service, transition, bot_caller=False):
        ctx = {"transition_id": transition.id}
        if bot_caller:
            ctx["riverflow_bot_caller"] = True
        private = service.with_context(**ctx)._prepare_transition_action()
        public = service.with_context(**ctx).prepare_transition_action()
        self.assertEqual(private.get("res_model"), public.get("res_model"))
        self.assertEqual(private.get("context"), public.get("context"))
        return public

    def _session(self):
        if "oteny.form.session" not in self.env:
            self.skipTest("oteny_bot is not installed")
        return self.env["oteny.form.session"]

    def _open(self, action):
        photo = self._session().open(action=action)
        photo["effects"] = list(action.get("effects") or [])
        return photo

    def _act_from_photo(self, photo):
        Session = self._session()
        session = Session.browse(photo["handle"])
        saved = Session.save(photo["handle"])
        ctx = dict((session.view_state or {}).get("context") or {})
        wizard = self.env[saved["model"]].with_context(**ctx).browse(saved["res_id"])
        if wizard._name == "riverflow.service.email.sender.wizard":
            wizard.recipient_partner_ids = self.recipient
        return wizard.action_save()

    def test_person_and_bot_see_the_same_buttons(self):
        service = self._make("Shared strip", self.state_draft)
        person = [row["caption"] for row in service.transition_buttons_json["buttons"]]
        self.assertEqual(person, ["Mark today"])
        if "oteny.bot" in self.env:
            self.env["oteny.bot"].create({
                "name": "Execute Bot",
                "bot_user_id": self.env.uid,
            })
        as_bot = service.with_user(self.env.user)
        bot = [row["caption"] for row in as_bot.transition_buttons_json["buttons"]]
        self.assertEqual(person, bot)
        extras = service.transition_buttons_json["buttons"][0]
        self.assertFalse(extras["has_visible_fields"])
        self.assertIn("set_deadline_to_today", extras["action_context_keys"])

    def test_prepare_without_ir_model_acl(self):
        user = self.env["res.users"].create({
            "name": "Execute Seam",
            "login": "execute_seam",
            "group_ids": [Command.set([
                self.env.ref("base.group_user").id,
                self.env.ref("riverflow.group_service_writer").id,
            ])],
        })
        self.env["ir.model.access"].search([
            ("model_id", "=", self.env.ref("base.model_ir_model").id),
            ("perm_read", "=", True),
        ]).write({"perm_read": False})
        service = self._make("Seam prepare", self.state_draft)
        action = service.with_user(user).with_context(
            transition_id=self.trans_mark_today.id,
        ).prepare_transition_action()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertTrue(action.get("res_model"))

    def test_open_uses_prepare_then_form_session(self):
        service = self._make("Open door", self.state_draft)
        action = self._prepare(service, self.trans_mark_today)
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertIn("set_deadline_to_today", action.get("effects") or [])
        photo = self._open(action)
        self.assertTrue(photo.get("handle"))
        self.assertEqual(photo["model"], action["res_model"])
        self.assertIn("set_deadline_to_today", photo["effects"])

    def test_act_and_bot_claim_set_deadline_to_today(self):
        human = self._make("Human today", self.state_draft)
        action = self._prepare(human, self.trans_mark_today)
        self._act_from_photo(self._open(action))
        self.assertEqual(human.state_id, self.state_ready)
        self.assertEqual(human.project_deadline, fields.Date.today())
        self.assertEqual(human.use_project_deadline_from, "self")

        claimed = self._make("Claim today", self.state_draft)
        result = self.Service.bot_claim(claimed.id, self.trans_mark_today.id)
        self.assertTrue(result.get("ok"))
        self.assertEqual(claimed.state_id, self.state_ready)
        self.assertEqual(claimed.project_deadline, fields.Date.today())

    def test_second_act_without_flag_keeps_an_edited_date(self):
        service = self._make("Keep date", self.state_draft)
        self._act_from_photo(self._open(self._prepare(service, self.trans_mark_today)))
        later = fields.Date.today() + timedelta(days=5)
        service.project_deadline = later
        self._act_from_photo(self._open(self._prepare(service, self.trans_continue)))
        self.assertEqual(service.state_id, self.state_closed)
        self.assertEqual(service.project_deadline, later)

    def test_human_click_writes_the_same_deadline(self):
        service = self._make("Human click", self.state_draft)
        action = self._prepare(service, self.trans_mark_today)
        wizard_ctx = dict(action["context"])
        Wizard = self.env[action["res_model"]].with_context(**wizard_ctx)
        defaults = Wizard.default_get(list(Wizard._fields))
        Wizard.create(defaults).action_save()
        self.assertEqual(service.project_deadline, fields.Date.today())
        self.assertEqual(service.state_id, self.state_ready)

    def test_email_sender_set_deadline_relative_drops_tomorrow(self):
        root = self._make("Root card", self.state_ready)
        root.use_project_deadline_from = "self"
        root.project_deadline = fields.Date.today() + timedelta(days=10)
        child = self.Service.with_context(bot_no_inline_dispatch=True).create({
            "name": "Child card",
            "parent_id": root.id,
            "workflow_id": self.workflow.id,
            "state_id": self.state_ready.id,
            "company_id": self.env.company.id,
        })
        action = self._prepare(child, self.trans_send_note)
        self.assertIn("set_deadline_relative", action.get("effects") or [])
        self._act_from_photo(self._open(action))
        self.assertEqual(child.state_id, self.state_closed)
        self.assertEqual(child.use_project_deadline_from, "root")
        self.assertEqual(child.days_relative_to_project, -1)
        self.assertNotEqual(
            child.project_deadline,
            fields.Date.today() + timedelta(days=1),
        )

    def test_fence_refuses_human_and_admits_flagged_bot(self):
        service = self._make("Live run", self.state_run)
        service.bot_run_started_at = fields.Datetime.now()
        self.assertTrue(service._bot_claim_is_live())
        with self.assertRaises(UserError):
            self._prepare(service, self.trans_hand_back)
        action = self._prepare(service, self.trans_hand_back, bot_caller=True)
        photo = self._open(action)
        self._act_from_photo(photo)
        self.assertEqual(service.state_id, self.state_closed)
