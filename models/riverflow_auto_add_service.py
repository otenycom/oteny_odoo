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
        string="Add Service To",
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
    service_name = fields.Char(string="Service Name", required=True)
    service_workflow_id = fields.Many2one(
        "riverflow.workflow", string="Workflow", required=True
    )
    service_use_project_deadline_from = fields.Selection(
        [
            ("self", "Self"),
            ("root", "Root Service"),
        ],
        string="Deadline From",
        required=True,
        default="self",
    )
    service_days_relative_to_project = fields.Integer(
        "Days relative",
        help="Number of days before or after the project deadline for this service to be completed, e.g. -1 for the day before",
        required=False,
    )
    service_note = fields.Char(string="Service Note")
    service_responsible_team_id = fields.Many2one(
        "riverflow.team",
        string="Responsible Team",
        help="Team executing the workflow of the service. If blank, taken from the subject record.",
    )

    @api.depends("service_name", "service_workflow_id.name")
    def _compute_name(self):
        for record in self:
            if record.service_name and record.service_workflow_id.name:
                record.name = (
                    f"{record.service_name} - {record.service_workflow_id.name}"
                )
            else:
                record.name = f"New Auto Add Service"

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
    def prepare_service_values(self, service_vals):
        """
        Hook method to prepare or modify service values before creation.
        This method can be overridden in inherited models to customize service values.
        """
        return service_vals

    @api.model
    def service_created(self, auto_add_rule, service):
        """
        Hook method to perform actions after a service is created.
        This method can be overridden in inherited models to customize post-creation actions.
        """
        if auto_add_rule.service_note:
            # post the note as a comment on the chatter
            service.message_post(
                body=auto_add_rule.service_note,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )

    @api.model
    def auto_add_services(self, records, trigger="create"):
        """Check rules and add services to matching records."""
        Service = self.env["riverflow.service"]

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
            auto_add_rules = matching_rules.filtered(
                lambda r: r.applies_to_model_id.model == record._name
            )
            for auto_add_rule in auto_add_rules:
                try:
                    domain = safe_eval(auto_add_rule.condition_domain, eval_context)
                    domain = expression.normalize_domain(domain)
                    if record.sudo().filtered_domain(domain):
                        service_vals = {
                            "name": auto_add_rule.service_name,
                            "workflow_id": auto_add_rule.service_workflow_id.id,
                            "res_model": record._name,
                            "res_id": record.id,
                            "created_by_auto_add_rule_id": auto_add_rule.id,
                            "responsible_team_id": (
                                auto_add_rule.service_responsible_team_id.id
                                if auto_add_rule.service_responsible_team_id
                                else record.responsible_team_id.id
                            ),
                            "use_project_deadline_from": auto_add_rule.service_use_project_deadline_from,
                            "days_relative_to_project": auto_add_rule.service_days_relative_to_project,
                        }
                        # Allow inherited classes to update service values
                        service_vals = self.prepare_service_values(service_vals)
                        service = Service.create([service_vals])[0]

                        self.service_created(auto_add_rule, service)
                except Exception as e:
                    _logger.error(
                        f"Error evaluating domain for rule {auto_add_rule.name}: {e}"
                    )
