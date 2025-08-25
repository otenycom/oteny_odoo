# -*- coding: utf-8 -*-
from odoo import fields, models


class OtenyAuditTestParent(models.Model):
    _name = "oteny.audit.test.parent"
    _description = "Oteny Audit Test Parent Model"

    name = fields.Char()
    child_ids = fields.One2many("oteny.audit.test.child", "parent_id")


class OtenyAuditTestChild(models.Model):
    _name = "oteny.audit.test.child"
    _description = "Oteny Audit Test Child Model"
    _oteny_audit_parent_field = "parent_id"

    name = fields.Char()
    parent_id = fields.Many2one("oteny.audit.test.parent", ondelete="cascade")
