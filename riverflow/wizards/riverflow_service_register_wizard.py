from odoo import models, fields, Command, api, _
from odoo.exceptions import ValidationError


class ServiceRegisterWizard(models.TransientModel):
    _name = "riverflow.service.register.wizard"  #
    _inherit = "riverflow.service.wizard"
    _description = "Service Register Wizard"

    supply_quantity = fields.Float(
        "Supplied Quantity",
        help="The quantity supplied (e.g. distance in km for a taxi ride)",
    )
    supply_quantity_required = fields.Boolean()
    supply_quantity_invisible = fields.Boolean()

    supply_unit_price = fields.Float(
        "Unit Price",
        help="The price per unit of the supplied service",
    )
    supply_unit_price_required = fields.Boolean()
    supply_unit_price_invisible = fields.Boolean()

    def default_get_using_records(self, defaultValues, records_to_transition):
        """Handle set_deadline_today context flag.

        When set_deadline_today is True in context, force the deadline to today
        by setting use_project_deadline_from to 'self' and project_deadline to today.
        """
        super().default_get_using_records(defaultValues, records_to_transition)

        if self.env.context.get("set_deadline_today"):
            defaultValues["use_project_deadline_from"] = "self"
            defaultValues["project_deadline"] = fields.Date.today()
            # Hide the deadline fields since they're forced
            defaultValues["use_project_deadline_from_invisible"] = True
            defaultValues["project_deadline_invisible"] = True

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)
        if not self.supply_quantity_invisible:
            vals["supply_quantity"] = self.supply_quantity
        if not self.supply_unit_price_invisible:
            vals["supply_unit_price"] = self.supply_unit_price

        # When set_deadline_today is used, force the deadline values even though fields are hidden
        if self.env.context.get("set_deadline_today"):
            vals["use_project_deadline_from"] = "self"
            vals["project_deadline"] = self.project_deadline
            vals["days_relative_to_project"] = 0

    def get_visibility_defaults(self, transition_id):
        visibility_defaults = super().get_visibility_defaults(transition_id)
        # visibility_defaults["name_invisible"] = visibility_defaults.get(
        #     "name_invisible", True
        # )
        visibility_defaults["transition_description_invisible"] = visibility_defaults.get(
            "transition_description_invisible", True
        )

        visibility_defaults["supply_quantity_invisible"] = visibility_defaults.get(
            "supply_quantity_invisible",
            not transition_id.workflow_id.has_supply_quantity,
        )
        visibility_defaults["supply_quantity_required"] = visibility_defaults.get(
            "supply_quantity_required",
            transition_id.workflow_id.has_supply_quantity,
        )

        visibility_defaults["supply_unit_price_invisible"] = visibility_defaults.get(
            "supply_unit_price_invisible",
            not transition_id.workflow_id.has_supply_unit_price,
        )
        visibility_defaults["supply_unit_price_required"] = visibility_defaults.get(
            "supply_unit_price_required",
            transition_id.workflow_id.has_supply_unit_price,
        )

        return visibility_defaults

    @api.constrains(
        "supply_quantity",
        "supply_quantity_required",
        "supply_unit_price",
        "supply_unit_price_required",
    )
    def _check_supply_quantity(self):
        """Ensure supply quantity and unit price are provided when required"""
        for wizard in self:
            if wizard.supply_quantity_required and not wizard.supply_quantity:
                raise ValidationError(_("Supply quantity is required and cannot be zero."))
            if wizard.supply_unit_price_required and not wizard.supply_unit_price:
                raise ValidationError(_("Unit price is required and cannot be zero."))
