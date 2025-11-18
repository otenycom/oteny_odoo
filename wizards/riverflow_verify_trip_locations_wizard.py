from odoo import api, fields, models, Command, _
from odoo.exceptions import ValidationError


class VerifyTripLocationsWizard(models.TransientModel):
    _name = "riverflow.verify.trip.locations.wizard"
    _inherit = "riverflow.service.wizard"
    _description = "Verify Trip Locations Wizard"

    # Override tag_ids with explicit relation name to avoid table name length issue
    tag_ids = fields.Many2many(
        "riverflow.service.tag",
        "riverflow_verify_trip_tag_rel",
        "wizard_id",
        "tag_id",
        string="Tags",
    )

    billing_distance_km = fields.Float(
        string="Billing Distance (km)",
        help="Distance used for billing. Leave empty to use sum of leg distances.",
    )

    total_leg_distance_km = fields.Float(
        string="Total Leg Distance (km)",
        compute="_compute_total_leg_distance_km",
        help="Auto-calculated sum of all leg distances",
    )

    leg_ids = fields.One2many(
        "riverflow.verify.trip.locations.wizard.leg",
        "wizard_id",
        string="Legs",
    )

    @api.depends("leg_ids.supply_distance_km")
    def _compute_total_leg_distance_km(self):
        """Compute total distance from wizard legs"""
        for wizard in self:
            wizard.total_leg_distance_km = sum(leg.supply_distance_km for leg in wizard.leg_ids)

    def get_visibility_defaults(self, transition_id):
        """Override to show internal notes summary in the verify trip locations wizard"""
        visibility_defaults = super().get_visibility_defaults(transition_id)
        visibility_defaults["internal_notes_summary_invisible"] = False
        return visibility_defaults

    @api.model
    def default_get_using_records(self, defaultValues, records_to_transition):
        """Populate wizard with current trip details for verification"""
        super().default_get_using_records(defaultValues, records_to_transition)

        if len(records_to_transition) == 1:
            service = records_to_transition[0]

            # Set billing distance override if present
            defaultValues["billing_distance_km"] = service.billing_distance_km or 0

            # Create wizard leg records for display and optional distance entry
            leg_vals = []
            for leg in service.leg_ids:
                leg_vals.append(
                    Command.create(
                        {
                            "service_leg_id": leg.id,
                            "supply_from": leg.supply_from,
                            "supply_to": leg.supply_to,
                            "supply_distance_km": leg.supply_distance_km or 0,
                            "supply_cost_amount": leg.supply_cost_amount or 0,
                        }
                    )
                )

            if leg_vals:
                defaultValues["leg_ids"] = leg_vals

    def update_write_values(self, service, vals):
        """Update leg details (locations and optional distances)"""
        super().update_write_values(service, vals)

        # Validate that service has legs
        if not self.leg_ids:
            raise ValidationError(
                _(
                    "No legs found for this service. "
                    "Please add legs to the service before verifying locations."
                )
            )

        # Save billing distance override
        vals["billing_distance_km"] = self.billing_distance_km

        # Update service legs with verified locations and distances
        for wizard_leg in self.leg_ids:
            if wizard_leg.service_leg_id:
                leg_vals = {}
                if wizard_leg.supply_from:
                    leg_vals["supply_from"] = wizard_leg.supply_from
                if wizard_leg.supply_to:
                    leg_vals["supply_to"] = wizard_leg.supply_to
                if wizard_leg.supply_distance_km:
                    leg_vals["supply_distance_km"] = wizard_leg.supply_distance_km
                # Always update cost (even if 0, user might be clearing it)
                leg_vals["supply_cost_amount"] = wizard_leg.supply_cost_amount

                if leg_vals:
                    wizard_leg.service_leg_id.write(leg_vals)


class VerifyTripLocationsWizardLeg(models.TransientModel):
    _name = "riverflow.verify.trip.locations.wizard.leg"
    _description = "Verify Trip Locations Wizard Leg"
    _order = "sequence,id"

    wizard_id = fields.Many2one(
        "riverflow.verify.trip.locations.wizard",
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
    supply_distance_km = fields.Float(
        string="Distance (km)", help="Optional: Enter distance now or later in 'Distance Entered' step"
    )
    supply_cost_amount = fields.Monetary(string="Cost", currency_field="supply_cost_currency_id")
    supply_cost_currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="service_leg_id.service_id.company_id.currency_id",
        store=False,
    )
