# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval
import logging
from odoo.exceptions import ValidationError
from ..util import log_execution_time


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
    description = fields.Text(
        string="Description",
        help="Internal notes about the rule's purpose or behavior.",
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
    def prepare_services_to_create(self, to_create):
        """
        Hook method to prepare or modify service values before creation.
        This method can be overridden in inherited models to customize service values.
        """
        pass

    @api.model
    def service_created(self, service):
        """
        Hook method to perform actions after a service is created.
        This method can be overridden in inherited models to customize post-creation actions.
        """
        if service.created_by_auto_add_service_id.service_note:
            # post the note as a comment on the chatter
            service.message_post(
                body=service.created_by_auto_add_service_id.service_note,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )

    @api.model
    @log_execution_time
    def auto_add_services(self, subjects):
        if subjects and isinstance(subjects[0].id, models.NewId):
            """Because of the fake id in form view, we need to return
            todo: review if we can use .add() and .new() on the many2one fields in the sync below to also make this work in form view
            """
            return

        """Check rules and add services to matching records."""
        if not subjects:
            return

        model = subjects[0]._name

        """
        TODO: also make this a log_entry.applicable_auto_add_service_ids field, so that log entry services_ids can take 
        a  dependency on applicable_auto_add_service_ids.condition_domain to make this more responsive
        """
        auto_add_rules = self.search(
            [
                ("applies_to_model_id.model", "=", model),
            ]
        )

        eval_context = self._eval_context()
        new_services = []
        # Prefetch the records to avoid multiple database hits
        self.env[model].browse(subjects.ids)

        # Pre-process domains for all auto_add_rules
        rule_domains = {}
        for auto_add_rule in auto_add_rules:
            try:
                domain = safe_eval(auto_add_rule.condition_domain, eval_context)
                rule_domains[auto_add_rule] = expression.normalize_domain(domain)
            except Exception as e:
                raise ValidationError(
                    f"Error evaluating domain for rule {auto_add_rule.name}: {e}"
                )

        for record in subjects:
            for auto_add_rule, domain in rule_domains.items():
                try:
                    if record.sudo().filtered_domain(domain):
                        new_services.append(
                            {
                                "name": auto_add_rule.service_name,
                                "workflow_id": auto_add_rule.service_workflow_id.id,
                                "res_model": record._name,
                                "res_id": record.id,
                                "created_by_auto_add_service_id": auto_add_rule.id,
                                "responsible_team_id": (
                                    auto_add_rule.service_responsible_team_id.id
                                    if auto_add_rule.service_responsible_team_id
                                    else record.responsible_team_id.id
                                ),
                                "use_project_deadline_from": auto_add_rule.service_use_project_deadline_from,
                                "days_relative_to_project": auto_add_rule.service_days_relative_to_project,
                            }
                        )
                except Exception as e:
                    _logger.error(
                        f"Error applying domain for rule {auto_add_rule.name} to record {record}: {e}"
                    )

        # Sync the generated services with the existing services
        current_services = (
            self.with_context(active_test=False)
            .env["riverflow.service"]
            .search(
                [
                    ("res_id", "in", subjects.ids),
                    ("res_model", "=", model),
                    ("created_by_auto_add_service_id", "!=", False),
                ]
            )
        )

        # Create sets for easy comparison
        new_services_set = {
            (ns["created_by_auto_add_service_id"], ns["res_id"]) for ns in new_services
        }
        current_services_dict = {
            (s.created_by_auto_add_service_id.id, s.res_id): s for s in current_services
        }

        # Services to activate (in new_services_set and currently inactive)
        to_activate = current_services.filtered(
            lambda s: (s.created_by_auto_add_service_id.id, s.res_id)
            in new_services_set
            and not s.active
        )

        # Services to deactivate (not in new_services_set and currently active)
        to_deactivate = current_services.filtered(
            lambda s: (s.created_by_auto_add_service_id.id, s.res_id)
            not in new_services_set
            and s.active
        )

        # Services to create (in new_services_set but not in current_services_dict)
        to_create = [
            ns
            for ns in new_services
            if (ns["created_by_auto_add_service_id"], ns["res_id"])
            not in current_services_dict
        ]

        if to_activate:
            to_activate.write({"active": True})

        if to_deactivate:
            to_deactivate.write({"active": False})

        if to_create:
            # Allow inherited classes to update service values
            self.prepare_services_to_create(to_create)
            created_services = self.env["riverflow.service"].create(to_create)
            for created_service in created_services:
                self.service_created(created_service)
