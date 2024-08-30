# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)


class AutoAddService(models.Model):
    _name = "riverflow.auto.add.service"
    _description = "Auto Add Service"

    name = fields.Char(
        string="Rule Name", compute="_compute_name", store=True, index=True
    )
    active = fields.Boolean(
        default=True,
        help="If unchecked, the rule will be disabled without removing it.",
    )

    applies_to_model_id = fields.Many2one(
        "ir.model",
        string="Subject Model",
        required=True,
        ondelete="cascade",
        help="The model to which services will be added.",
    )
    applies_to_model = fields.Char(
        string="Applies to Model",
        related="applies_to_model_id.model",
        store=True,
        index=True,
    )

    condition_domain = fields.Text(
        string="Condition",
        required=True,
        default="[]",
        help="Domain filter to determine when the service should be added.",
    )
    note = fields.Text(
        string="Description",
        help="Internal notes about the rule's purpose or behavior.",
    )

    service_name = fields.Char(string="Service Name", required=True)
    service_workflow_id = fields.Many2one(
        "riverflow.workflow", string="Workflow", required=True
    )

    apply_on_create = fields.Boolean(
        string="Apply on Create",
        default=True,
        help="Apply this rule when a new subject record is created.",
    )
    apply_on_write = fields.Boolean(
        string="Apply on Write",
        default=True,
        help="Apply this rule when a subject record is updated.",
    )

    @api.depends("service_name", "service_workflow_id.name")
    def _compute_name(self):
        for record in self:
            record.name = f"{record.service_name} - {record.service_workflow_id.name}"

    @api.model
    def _eval_context(self):
        return {
            "user": self.env.user.with_context({}),
            "time": tools.safe_eval.time,
            "datetime": tools.safe_eval.datetime,
            "company_ids": self.env.companies.ids,
            "company_id": self.env.company.id,
            "ref": self.env.ref,
        }

    @api.model
    def auto_add_services(self, records, trigger="create"):
        """Check rules and add services to matching records."""
        Service = self.env["riverflow.service"]
        services_to_create = []

        # Collect distinct model names from the records
        model_names = list(set(record._name for record in records))

        # Lookup matching rules with one query
        matching_rules = self.search(
            [
                ("applies_to_model_id.model", "in", model_names),
                ("active", "=", True),
                (f"apply_on_{trigger}", "=", True),
            ]
        )

        eval_context = self._eval_context()
        for record in records:
            rules_for_model = matching_rules.filtered(
                lambda r: r.applies_to_model_id.model == record._name
            )
            for rule in rules_for_model:
                try:
                    domain = safe_eval(rule.condition_domain, eval_context)
                    domain = expression.normalize_domain(domain)
                    if record.sudo().filtered_domain(domain):
                        services_to_create.append(
                            {
                                "name": rule.service_name,
                                "workflow_id": rule.service_workflow_id.id,
                                "res_model": record._name,
                                "res_id": record.id,
                                "created_by_auto_add": True,
                            }
                        )
                except Exception as e:
                    _logger.error(f"Error evaluating domain for rule {rule.name}: {e}")

        if services_to_create:
            Service.create(services_to_create)
