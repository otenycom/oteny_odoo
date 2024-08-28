# -*- coding: utf-8 -*-

from odoo import fields, models, api


class CheckResult(models.Model):
    _name = "riverflow.check.result"
    _description = "Base Check Result"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    check_type = fields.Selection([], string="Check Type", required=True)
    description = fields.Text(string="Description")
    severity = fields.Selection(
        [
            ("info", "Info"),
            ("warning", "Warning"),
            ("error", "Error"),
        ],
        string="Severity",
        required=True,
    )
    color = fields.Integer(string="Color", compute="_compute_color", store=True)

    @api.depends("check_type")
    def _compute_name(self):
        for record in self:
            record.name = f"{record.check_type.capitalize()} Check"

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

    def compare_base(self, other):
        """
        Base compare method for check results.
        Compare basic fields common to all check results.
        """
        if isinstance(other, dict):
            return (
                self.check_type == other.get("check_type")
                and self.description == other.get("description")
                and self.severity == other.get("severity")
            )
        elif isinstance(other, type(self)):
            return (
                self.check_type == other.check_type
                and self.description == other.description
                and self.severity == other.severity
            )
        return False
