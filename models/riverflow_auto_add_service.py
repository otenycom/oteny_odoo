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

    name = fields.Char(string="Name", compute="_compute_name", store=True, index=True)
    active = fields.Boolean(
        default=True,
        help="If unchecked, the auto-add rule will be disabled without removing it.",
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
        help="Specifies when the service should be added.",
    )
    description = fields.Text(
        string="Description",
        help="Internal notes about the rule's purpose or behavior.",
    )
    service_template_id = fields.Many2one(
        "riverflow.service",
        string="Service Template",
        required=True,
        domain=[("is_this_a_template", "=", True)],
        help="Template that will be copied to create the auto-added service",
    )

    @api.depends("service_template_id.name")
    def _compute_name(self):
        for record in self:
            if record.service_template_id:
                record.name = f"Auto-add: {record.service_template_id.name}"
            else:
                record.name = "New Auto Add Service"

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

    # @log_execution_time
    @api.model
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
                raise ValidationError(f"Error evaluating domain for rule {auto_add_rule.name}: {e}")

        for subject in subjects:
            for auto_add_rule, domain in rule_domains.items():
                try:
                    if subject.sudo().filtered_domain(domain):
                        # Instead of creating immediately, collect the values
                        new_services.append(
                            {
                                "res_id": subject.id,
                                "res_model": subject._name,
                                "created_by_auto_add_service_id": auto_add_rule.id,
                                "template_id": auto_add_rule.service_template_id.id,
                            }
                        )
                except Exception as e:
                    _logger.error(
                        f"Error applying domain for rule {auto_add_rule.name} to record {subject}: {e}"
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

        # Create sets for easy comparison using template_id instead of the created service
        new_services_set = {(ns["created_by_auto_add_service_id"], ns["res_id"]) for ns in new_services}
        current_services_dict = {(s.created_by_auto_add_service_id.id, s.res_id): s for s in current_services}

        # Services to activate (in new_services_set and currently inactive)
        to_activate = current_services.filtered(
            lambda s: (s.created_by_auto_add_service_id.id, s.res_id) in new_services_set and not s.active
        )

        # Services to deactivate (not in new_services_set and currently active)
        to_deactivate = current_services.filtered(
            lambda s: (s.created_by_auto_add_service_id.id, s.res_id) not in new_services_set
            and s.active
            # only de-active an auto-added service if it unmodified since it was auto-added.
            and s.create_date == s.write_date
        )

        # Services to create (in new_services_set but not in current_services_dict)
        to_create = [
            ns
            for ns in new_services
            if (ns["created_by_auto_add_service_id"], ns["res_id"]) not in current_services_dict
        ]

        if to_activate:
            to_activate.write({"active": True})

        if to_deactivate:
            to_deactivate.write({"active": False})

        if to_create:
            for service_vals in to_create:
                service_context = self.env["riverflow.service"].with_context(
                    {
                        "default_res_id": service_vals["res_id"],
                        "default_res_model": service_vals["res_model"],
                        "default_created_by_auto_add_service_id": service_vals[
                            "created_by_auto_add_service_id"
                        ],
                    }
                )
                service_context._create_services_from_template(service_vals["template_id"])
