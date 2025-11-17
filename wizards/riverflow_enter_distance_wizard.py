from odoo import api, fields, models, Command, _
from odoo.exceptions import ValidationError


class RiverflowEnterDistanceWizard(models.TransientModel):
    _name = "riverflow.enter.distance.wizard"
    _inherit = "riverflow.service.wizard"
    _description = "Enter Distance Wizard"

    leg_ids = fields.One2many(
        "riverflow.enter.distance.wizard.leg",
        "wizard_id",
        string="Legs",
    )

    @api.model
    def default_get_using_records(self, defaultValues, records_to_transition):
        """Populate legs from the service"""
        super().default_get_using_records(defaultValues, records_to_transition)

        if len(records_to_transition) != 1:
            return

        service = records_to_transition[0]

        # Create wizard leg records for each service leg
        leg_vals = []
        for leg in service.leg_ids:
            leg_vals.append(
                Command.create(
                    {
                        "service_leg_id": leg.id,
                        "supply_from": leg.supply_from,
                        "supply_to": leg.supply_to,
                        "supply_distance_km": leg.supply_distance_km or 0,
                    }
                )
            )

        if leg_vals:
            defaultValues["leg_ids"] = leg_vals

    def update_write_values(self, service, vals):
        """Update the service legs with distances and verified locations"""
        super().update_write_values(service, vals)

        # Validate that service has legs
        if not self.leg_ids:
            raise ValidationError(
                _(
                    "No legs found for this service. "
                    "Please add legs to the service before entering distances."
                )
            )

        # Validate that all legs have distance entered
        for wizard_leg in self.leg_ids:
            if not wizard_leg.supply_distance_km or wizard_leg.supply_distance_km <= 0:
                raise ValidationError(
                    _("Please enter a valid distance for all legs. " "Leg %s → %s has no distance entered.")
                    % (wizard_leg.supply_from, wizard_leg.supply_to)
                )

        # Update the actual service legs with distances and locations
        for wizard_leg in self.leg_ids:
            if wizard_leg.service_leg_id:
                leg_vals = {}
                if wizard_leg.supply_from:
                    leg_vals["supply_from"] = wizard_leg.supply_from
                if wizard_leg.supply_to:
                    leg_vals["supply_to"] = wizard_leg.supply_to
                if wizard_leg.supply_distance_km:
                    leg_vals["supply_distance_km"] = wizard_leg.supply_distance_km

                if leg_vals:
                    wizard_leg.service_leg_id.write(leg_vals)


class RiverflowEnterDistanceWizardLeg(models.TransientModel):
    _name = "riverflow.enter.distance.wizard.leg"
    _description = "Distance Entry Wizard Leg"
    _order = "sequence,id"

    wizard_id = fields.Many2one(
        "riverflow.enter.distance.wizard",
        required=True,
        ondelete="cascade",
    )

    service_leg_id = fields.Many2one(
        "riverflow.service.leg",
        string="Service Leg",
        required=True,
        ondelete="cascade",
    )

    sequence = fields.Integer(related="service_leg_id.sequence", store=False)
    supply_from = fields.Char(string="From")
    supply_to = fields.Char(string="To")
    supply_distance_km = fields.Float(string="Distance (km)", required=True)
