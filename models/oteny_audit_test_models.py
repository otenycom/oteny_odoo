# -*- coding: utf-8 -*-
from odoo import api, fields, models


class OtenyAuditTestParent(models.Model):
    _name = "oteny.audit.test.parent"
    _description = "Oteny Audit Test Parent Model"
    _oteny_audit_ignore = False

    name = fields.Char()
    # Computed field with inverse that simulates the company_id behavior during creation
    computed_field = fields.Char(
        compute="_compute_computed_field",
        inverse="_inverse_computed_field",
        store=True,
        string="Computed Field",
    )
    child_ids = fields.One2many("oteny.audit.test.child", "parent_id")

    @api.depends("name")
    def _compute_computed_field(self):
        """Compute method that will be triggered during creation when name is set"""
        for record in self:
            if record.name:
                record.computed_field = f"Computed: {record.name}"
            else:
                record.computed_field = False

    def _inverse_computed_field(self):
        """Inverse method - required for the field to be properly audited"""
        # In real scenarios, this might update related fields
        # For testing, we just pass
        pass


class OtenyAuditTestChild(models.Model):
    _name = "oteny.audit.test.child"
    _description = "Oteny Audit Test Child Model"
    _oteny_audit_parent_field = "parent_id"
    _oteny_audit_ignore = False

    name = fields.Char()
    parent_id = fields.Many2one("oteny.audit.test.parent", ondelete="cascade")
