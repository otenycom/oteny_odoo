from odoo import api, fields, models, tools
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval
import logging
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class AutoAddService(models.Model):
    _name = "riverflow.auto.add.service"
    _description = "Auto Add Service"
    _order = "applies_to_model, template_relative_timing desc, template_daily_order"

    name = fields.Char(string="Name", compute="_compute_name", store=True, index=True)
    active = fields.Boolean(
        default=True,
        help="If unchecked, the auto-add rule will be disabled without removing it.",
    )
    domain_id = fields.Many2one(
        "riverflow.auto.add.domain",
        string="Domain Condition",
        required=True,
        ondelete="restrict",
    )
    applies_to_model_id = fields.Many2one(
        related="domain_id.applies_to_model_id",
        store=True,
        readonly=True,
    )
    applies_to_model = fields.Char(
        related="domain_id.applies_to_model",
        store=True,
        index=True,
    )
    domain = fields.Text(
        related="domain_id.domain",
        readonly=True,
    )
    service_template_id = fields.Many2one(
        "riverflow.service",
        string="Service Template",
        required=True,
        domain=[("is_this_a_template", "=", True)],
        help="Template that will be copied to create the auto-added service",
    )
    template_relative_timing = fields.Char(
        related="service_template_id.relative_timing_formatted",
        string="Template Timing",
        store=True,
        readonly=True,
    )
    template_daily_order = fields.Integer(
        related="service_template_id.daily_prio",
        string="Priority",
        help="Sort order for services that have the same deadline",
        store=True,
        readonly=True,
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

    def _filter_auto_add_candidates(self, new_services, model):
        """Hook for filtering auto-add candidates before dedup.

        Called between candidate building and dedup. Override in inheriting
        modules to add filtering logic (e.g. credential plan-item check).
        """
        return new_services

    @api.model
    def auto_add_services(self, subjects):
        if subjects and isinstance(subjects[0].id, api.NewId):
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
        a  dependency on applicable_auto_add_service_ids.domain to make this more responsive
        """
        # Force active_test=True so deactivated rules are never evaluated,
        # even when the calling compute method runs with active_test=False
        # leaked from the ORM's trigger traversal context.
        auto_add_rules = self.with_context(active_test=True).search(
            [
                ("applies_to_model", "=", model),
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
                domain = safe_eval(auto_add_rule.domain, eval_context)
                rule_domains[auto_add_rule] = Domain(domain)
            except Exception as e:
                raise ValidationError(f"Error evaluating domain for rule {auto_add_rule.name}: {e}")

        # Performance optimization: batch-evaluate all subjects per rule using search()
        # instead of filtered_domain() per subject. This reduces O(subjects x rules) Python
        # domain evaluations to O(rules) database queries, dramatically improving performance.
        rule_matching_ids = {}
        for auto_add_rule, domain in rule_domains.items():
            # Combine rule domain with subject filter - single DB query per rule
            # Domain objects are iterable ASTs, so list() converts to traditional list format
            combined_domain = list(domain) + [("id", "in", subjects.ids)]
            matching = self.env[model].sudo().search(combined_domain)
            rule_matching_ids[auto_add_rule] = set(matching.ids)

        # Now iterate without expensive per-record domain evaluation
        for subject in subjects:
            for auto_add_rule in rule_domains:
                if subject.id in rule_matching_ids[auto_add_rule]:
                    new_services.append(
                        {
                            "res_id": subject.id,
                            "res_model": subject._name,
                            "created_by_auto_add_service_id": auto_add_rule.id,
                            "template_id": auto_add_rule.service_template_id.id,
                        }
                    )

        # Hook for filtering candidates before dedup (e.g. credential plan-item check)
        new_services = self._filter_auto_add_candidates(new_services, model)

        # Get existing auto-added services to avoid duplicates.
        # Dedup key is (rule_id, subject_id, context_ref) so the same rule can create
        # multiple services for different occasions (e.g. initial vs renewal credentials).
        # context_ref defaults to False for backward compatibility with rules that don't use it.
        current_services_dict = {
            (s.created_by_auto_add_service_id.id, s.res_id, s.auto_add_context_ref or False): s
            for s in self.with_context(active_test=False)
            .env["riverflow.service"]
            .search(
                [
                    ("res_id", "in", subjects.ids),
                    ("res_model", "=", model),
                    ("created_by_auto_add_service_id", "!=", False),
                ]
            )
        }

        # Services to create (in new_services_set but not in current_services_dict)
        # Only create services that don't already exist - no deactivation or reactivation
        to_create = [
            ns
            for ns in new_services
            if (ns["created_by_auto_add_service_id"], ns["res_id"], ns.get("auto_add_context_ref") or False)
            not in current_services_dict
        ]

        if to_create:
            for service_vals in to_create:
                ctx = self._get_service_creation_context(service_vals)
                service_context = self.env["riverflow.service"].with_context(**ctx)
                service_context._create_services_from_template(service_vals["template_id"])

    def _get_service_creation_context(self, service_vals):
        """Build context dict for creating a service from auto-add vals.

        Override in inheriting modules to inject additional default fields
        (e.g. credential_plan_item_id in rivercreds).
        """
        return {
            "default_res_id": service_vals["res_id"],
            "default_res_model": service_vals["res_model"],
            "default_created_by_auto_add_service_id": service_vals["created_by_auto_add_service_id"],
            "default_auto_add_context_ref": service_vals.get("auto_add_context_ref"),
        }
