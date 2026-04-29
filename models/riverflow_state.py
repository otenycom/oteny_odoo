from odoo import models, fields, api
from random import randint


class RiverflowWorkflowState(models.Model):
    _name = "riverflow.state"
    _description = "Workflow state"
    _order = "workflow_id,sequence,name,id"
    _rec_name = "display_name"
    _oteny_audit_parent_field = "workflow_id"

    name = fields.Char("State name", required=True)
    description = fields.Text("Description", required=False)
    active = fields.Boolean("Active", default=True)
    workflow_id = fields.Many2one("riverflow.workflow", "Workflow", copy=True, index=True, required=True)
    sequence = fields.Integer(default=10)
    hide_in_statusbar = fields.Boolean("Hide in Statusbar", default=False)
    is_end_state = fields.Boolean("Is End State", default=False)

    """
    SERVICE STATE COLORS
    Aministrative & Financial (Orange - 2)
    Back Office Workflow: Registered, Approved, Booked states
    To Be Invoiced Workflow: To Be Invoiced, Ready for Invoicing, Invoiced states
    Rationale: Orange represents official/formal processes related to finance and administration
    
    Transportation & Travel (Teal - 7)
    Taxi Order Workflow: Not Started, Ordered, Confirmed states
    Train Ticket Workflow: Not Started, Booked states
    Taxi Leg Workflow: Info state
    Rationale: Teal provides good visibility without conflicting with blue used for log entries
    
    Task Management (Raspberry/Pink - 9)
    Task Workflow: Not Started, In Progress, Done states
    Rationale: Distinctive color that stands out for action items and tasks
    
    Communication (Purple - 5)
    Email Workflow: Not Started, Sent, Not Needed states
    Rationale: Purple represents communication and information exchange
    

    ENTRIES
    Work-Related Workflows (Blue - 8)
    Crew Change (already blue)
    Sales (already blue)

    Availability/Waiting Workflows (Green - 10)
    Available
    Standby Home
    Standby Away
    No Replacement Needed

    Time Off Workflows (Yellow - 3)
    Vacation (already yellow)
    Own Request

    Health-Related Workflows (Purple - 5)
    Sick At Home
    Sick Away

    Administrative Workflows (Orange - 2)
    Cash Payout
    Terminated
    Special States

    Cancelled states: Red (1)
    Default/To be planned: Gray (0)

        The 12 colors in $o-colors are:
        0 #a2a2a2 - Gray (for "No color" option)
        1 #ee2d2d - Red
        2 #dc8534 - Orange
        3 #e8bb1d - Yellow
        4 #5794dd - Cyan/Light Blue
        5 #9f628f - Purple
        6 #db8865 - Almond/Light Brown
        7 #41a9a2 - Teal
        8 #304be0 - Blue
        9 #ee2f8a - Raspberry/Pink
        10 #61c36e - Green
        11 #9872e6 - Violet
    """
    color_int = fields.Integer("Color", default=11)

    # todo: add to radar.
    # Extend filters, 'Is Pending' should be 'Pending in Front Office' and 'Pending in Back Office'
    is_back_office_state = fields.Boolean(
        "Is Back Office State",
        help="If true, this state is for back office use; to handle the financial aspect of the workflow.",
        default=False,
    )
    is_cancelled_state = fields.Boolean("Is Cancelled State", default=False)
    is_supply_order_delivered = fields.Boolean(
        "Supply Order Delivered",
        help="If true, this state indicates the supply/service has been delivered to the customer, "
        "even if administrative tasks (verification, billing) remain. Used by info services to track "
        "when the actual service completion occurred.",
        default=False,
    )
    requires_onboarding_credentials = fields.Boolean(
        "Requires Onboarding Credentials",
        help="If true, onboarding credential slots are shown in the credential plan "
        "for entities in this state. Set on employee states where credential "
        "arrangement should be tracked (e.g. Agreement Signed, Employed) and "
        "ship states where ship documents are needed (e.g. Onboarding, Active).",
        default=False,
    )
    show_state_in_crew_planning = fields.Boolean(
        "Show in Crew Planning",
        help="If true, this state is shown as a badge on the slot label in the crew planning view. "
        "Set on states that are not the normal operating state (e.g. not 'Employed' for employees, "
        "not 'Active' for ships) to alert planners.",
        default=False,
    )
    auto_progress_on_children_done = fields.Boolean(
        "Auto-Progress When Children Done",
        help="When set, services in this state automatically progress to the "
        "next sequential workflow state once all active child services "
        "have reached an end state. Used for states that spawn deferred "
        "child tasks (e.g. parallel email-sending services) and should "
        "complete when those tasks finish.",
        default=False,
    )
    auto_done_children_on_enter = fields.Boolean(
        "Auto-Done Children When Entered",
        help="When set, entering this state moves all active non-end-state "
        "child services to the first non-cancelled end state of their own "
        "workflow (by sequence). Mirror of auto_progress_on_children_done in "
        "the opposite direction. Used on parent terminal states whose "
        "semantics imply child tasks are also complete (e.g. AUV Done means "
        "the OPS Review-AUV child task is moot).",
        default=False,
    )

    from_transition_ids = fields.One2many(
        "riverflow.transition",
        "from_state_id",
        string="From-transitions",
        help="Transitions from this state",
    )

    display_name = fields.Char("Display Name", compute="_compute_display_name", store=True, index="trigram")

    @api.depends("name", "workflow_id.name")
    def _compute_display_name(self):
        for state in self:
            state.display_name = f"{state.name} | {state.workflow_id.name}"

    def workflow_add_from_transition(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Add Transition from: " + self.name,
            "view_mode": "form",
            "res_model": "riverflow.transition",
            "context": {
                "default_workflow_id": self.workflow_id.id,
                "default_from_state_id": self.id,
                "is_start_transition": False,
            },
            "target": "current",
        }
