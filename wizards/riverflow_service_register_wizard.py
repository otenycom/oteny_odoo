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

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)
        if not self.supply_quantity_invisible:
            vals["supply_quantity"] = self.supply_quantity

    def get_visibility_defaults(self, transition_id):
        visibility_defaults = super().get_visibility_defaults(transition_id)
        visibility_defaults["name_invisible"] = visibility_defaults.get(
            "name_invisible", True
        )
        visibility_defaults["transition_description_invisible"] = (
            visibility_defaults.get("transition_description_invisible", True)
        )

        return visibility_defaults

    @api.constrains("supply_quantity", "supply_quantity_required")
    def _check_supply_quantity(self):
        """Ensure supply quantity is provided when required"""
        for wizard in self:
            if wizard.supply_quantity_required and not wizard.supply_quantity:
                raise ValidationError(
                    _("Supply quantity is required and cannot be zero.")
                )
