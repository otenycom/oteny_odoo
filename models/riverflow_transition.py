from odoo import models, fields, api
from markupsafe import escape


class RiverflowTransition(models.Model):
    _name = "riverflow.transition"
    _description = "Workflow state transition"
    _order = "workflow_id,from_state_id,sequence,name,id"
    _rec_name = "display_name"
    _oteny_audit_parent_field = "workflow_id"

    name = fields.Char("Transition name", required=True)
    description = fields.Html("Description", required=False, sanitize_style=True)
    sequence = fields.Integer(default=10)
    icon = fields.Char("Icon", help="Font awesome icon e.g. fa-tasks")
    icon_name_html = fields.Html(
        "Name",
        compute="_compute_icon_name_html",
        store=True,
        help="Combination of Icon and name",
    )
    active = fields.Boolean("Active", default=True)
    from_state_id = fields.Many2one(
        "riverflow.state",
        "From",
        help="Leave blank to define a start-transition",
        copy=True,
        index=True,
        required=False,
        # todo: only restrict for new records, allow a way to make transitions between workflows
        domain="[('workflow_id', '=', workflow_id)]",
    )
    to_state_id = fields.Many2one(
        "riverflow.state",
        "To",
        copy=True,
        index=True,
        required=True,
        # Todo: refine this domain, so that it is possible to create a transition between workflows
        # For now disabled since i couldn't make it to back office via ui
        # domain="[('workflow_id', '=', workflow_id)]",
    )
    workflow_id = fields.Many2one(
        "riverflow.workflow",
        string="Workflow",
        help="Derived from the to-state, since the from-state is optional",
        compute="_compute_workflow_id",
        store=True,
    )

    workflow_name = fields.Char(
        string="Workflow Name",
        compute="_compute_workflow_name",
        store=True,
    )

    to_responsible_team_id = fields.Many2one(
        "res.partner",
        "Assign to Responsible Team",
        help="Team to assign the service to",
        required=False,
        # domain="['|', ('is_user', '=', True), ('is_riverflow_team', '=', True)]",
        domain="[('is_riverflow_team', '=', True)]",
    )

    @api.depends("workflow_id")
    def _compute_workflow_name(self):
        for transition in self:
            transition.workflow_name = transition.workflow_id.name if transition.workflow_id else False

    model = fields.Char(
        "Related Model",
        related="workflow_id.model",
        help="Model on which the workflow runs",
        index=True,
        store=True,
        readonly=True,
    )
    action_id = fields.Many2one(
        "riverflow.transition.action",
        "Action",
        domain="[('model', '=', model)]",
        copy=True,
    )
    action_context = fields.Text(
        "Action context", help="Configuration values for the action screen", copy=True
    )
    display_name = fields.Char("Display Name", compute="_compute_display_name", store=True, index="trigram")

    # Per-transition email template override. When set, the Send Email wizard
    # uses this template instead of the service's mail_template_id. This allows
    # different email transitions within the same workflow to use different
    # templates (e.g., AB appointment request vs. pickup request).
    mail_template_id = fields.Many2one(
        "mail.template",
        string="Email Template",
        copy=True,
        domain="[('model', '=', 'riverflow.service')]",
        help="When set, the Send Email transition wizard uses this template "
        "instead of the service's mail_template_id.",
    )

    @api.depends("from_state_id.workflow_id", "to_state_id.workflow_id")
    def _compute_workflow_id(self):
        for transition in self:
            if transition.from_state_id:
                transition.workflow_id = transition.from_state_id.workflow_id
            else:
                # start transition
                transition.workflow_id = transition.to_state_id.workflow_id

    @api.depends("name", "from_state_id", "from_state_id")
    def _compute_display_name(self):
        for transition in self:
            fromState = transition.from_state_id.display_name if transition.from_state_id else "Start"
            transition.display_name = (
                f"{transition.name}: {fromState} → {transition.to_state_id.display_name}"
            )

    @api.depends("icon", "name", "action_id.icon")
    def _compute_icon_name_html(self):
        for record in self:
            icon = record.icon or record.action_id.icon
            if icon:
                record.icon_name_html = (
                    f'<span><span class="fa {escape(icon)}"></span>&nbsp;{escape(record.name)}</span>'
                )
            else:
                record.icon_name_html = escape(record.name)

    @api.model
    def _get_transition_description(self, transition):
        if self.transition_id.from_state_id:
            transition_description = (
                self.transition_id.from_state_id.name + " → " + self.transition_id.to_state_id.name
            )
        else:  # start transition
            transition_description = self.transition_id.to_state_id.name
        if self.transition_id.description:
            transition_description += f" | {self.transition_id.description}"
