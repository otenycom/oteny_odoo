from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAudit(TransactionCase):
    def test_write_field(self):
        main_partner = self.env.ref("base.main_partner")
        main_partner.name = "Test"
        main_partner.write({"name": "Test2"})
        self.assertEqual(main_partner.name, "Test2")

        # TODO: assert the update is in the audit log
