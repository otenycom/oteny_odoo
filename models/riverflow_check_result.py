# -*- coding: utf-8 -*-

from odoo import fields, models, api


class CheckResult(models.Model):
    _name = "riverflow.check.result"
    _description = "Base Check Result"

    name = fields.Char(string="Name", store=True)
    check_type = fields.Selection([], string="Check Type", required=True)
    severity = fields.Selection(
        [
            ("info", "Info"),
            ("warning", "Warning"),
            ("error", "Error"),
        ],
        string="Severity",
        required=True,
    )
    color = fields.Integer(string="Color", compute="_compute_color", store=False)

    state_record_id = fields.Many2one(
        comodel_name="riverflow.state.record",
        string="State Record",
        required=False,
        ondelete="cascade",
        compute="_compute_state_record_id",
        store=True,
    )

    @api.depends()
    def _compute_state_record_id(self):
        pass

    @api.depends("severity")
    def _compute_color(self):
        for record in self:
            if record.severity == "info":
                record.color = 4  # Blue
            elif record.severity == "warning":
                record.color = 3  # Yellow
            elif record.severity == "error":
                record.color = 1  # Red
            else:
                record.color = 0  # Gray (default)

    def compare(self, other):
        """
        Base compare method for check results.
        Compare basic fields common to all check results.
        """
        if isinstance(other, dict):
            return (
                self.name == other.get("name")
                and self.check_type == other.get("check_type")
                and self.severity == other.get("severity")
            )
        elif isinstance(other, type(self)):
            return (
                self.name == other.name
                and self.check_type == other.check_type
                and self.severity == other.severity
            )
        return False
