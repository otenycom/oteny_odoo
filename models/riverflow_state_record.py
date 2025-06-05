from odoo import models, fields, api, _
from collections import defaultdict
from datetime import datetime

# Define the date format constant here instead of relying on Service class
DATE_FORMAT = "%d/%m/%Y"


class RiverflowStateRecord(models.Model):
    _name = "riverflow.state.record"
    _description = "Global View of Riverflow State"
    _order = "res_model,res_name,res_id,is_subject desc,root_name,root_id,sequence,deadline"

    active = fields.Boolean(
        default=True,
        help="Set active to false to archive the service",
        compute="_compute_active",
        store=True,
    )
    is_subject = fields.Boolean(
        string="Is Subject",
        compute="_compute_is_subject",
        store=True,
    )

    @api.depends("root_id")
    def _compute_is_subject(self):
        for record in self:
            # services have a root_id, but subjects dont
            record.is_subject = record.root_id == 0

    @api.model
    def _selection_target_model(self):
        return [(model.model, model.name) for model in self.env["ir.model"].sudo().search([])]

    # Fields to identify the record
    name = fields.Char(
        string="Name",
        index=True,
        compute="_compute_name",
        store=True,
    )
    display_name = fields.Char(
        string="Display Name",
        index=True,
        compute="_compute_display_name",
        store=True,
    )
    master_model = fields.Char(string="Master Model", required=True, index=True)
    master_res_id = fields.Integer(string="Master Record ID", required=True, index=True)
    master_record_reference = fields.Reference(
        string="Master Record Reference",
        selection="_selection_target_model",
        compute="_compute_master_record_reference",
        readonly=True,
    )

    @api.depends("master_model", "master_res_id")
    def _compute_master_record_reference(self):
        for record in self:
            if record.master_model and record.master_res_id:
                record.master_record_reference = f"{record.master_model},{record.master_res_id}"
            else:
                record.master_record_reference = False

    # --- service fields
    res_id = fields.Integer(
        string="Subject of Service ID",
        required=False,
        compute="_compute_res_id",
        store=True,
    )
    res_model = fields.Char(
        string="Subject of Service Model Name",
        compute="_compute_res_model",
        store=True,
    )
    res_name = fields.Char(
        string="Subject of Service",
        compute="_compute_res_name",
        store=True,
        index="trigram",
    )

    root_id = fields.Integer(
        string="Root ID",
        index=True,
        compute="_compute_root_id",
        store=True,
    )
    root_name = fields.Char(
        string="Root Name",
        index=True,
        compute="_compute_root_name",
        store=True,
    )
    indent_level = fields.Integer(
        string="Indent Level",
        compute="_compute_indent_level",
        store=True,
    )
    indented_name = fields.Char("Record", compute="_compute_indented_name", store=False)

    deadline = fields.Date(
        "Deadline Date",
        help="Deadline based on the project-deadline and the relative day of this service",
        index=True,
        compute="_compute_deadline",
        store=True,
    )
    end_date = fields.Date(
        "End Date",
        compute="_compute_end_date",
        store=True,
    )
    deadline_formatted = fields.Char("Deadline", compute="_compute_deadline_formatted", store=False)

    timing_json = fields.Json(
        "Timing",
        compute="_compute_timing_json",
        store=False,
    )
    sequence = fields.Integer(
        default=1,
        index=True,
        required=True,
        compute="_compute_sequence",
        store=True,
    )

    # Fields from RiverflowWorkflowStateMixin
    workflow_id = fields.Many2one(
        "riverflow.workflow",
        string="Workflow",
        compute="_compute_workflow_id",
        readonly=True,
        store=True,
    )
    current_workflow_name = fields.Char(
        "Workflow name",
        related="workflow_id.name",
        store=True,
        index=True,
    )
    state_id = fields.Many2one(
        "riverflow.state",
        string="Workflow State",
        compute="_compute_state_id",
        store=True,
        readonly=True,
        index=True,
    )
    state_name = fields.Char("State name", related="state_id.name", store=True, index=True)
    state_json = fields.Json(
        string="State",
        readonly=True,
        compute="_compute_state_json",
    )
    is_end_state = fields.Boolean(
        "Is End State",
        compute="_compute_is_end_state",
        store=True,
        index=True,
    )
    # fields from MailThreadReviewMixin
    color_int = fields.Integer(
        related="state_id.color_int",
    )
    internal_notes_summary = fields.Html(
        string="Internal Notes",
        compute="_compute_internal_notes_summary",
        index=True,
        store=True,
    )
    external_messages_summary = fields.Html(
        string="External Messages",
        compute="_compute_external_messages_summary",
        index=True,
        store=True,
    )
    unreviewed_message_count = fields.Integer(
        string="Review",
        compute="_compute_unreviewed_message_count",
        index=True,
        store=True,
    )

    responsible_team_id = fields.Many2one(
        "res.partner",
        string="Responsible Team",
        help="Team executing the workflow. This team is also responsible for reviewing external messages.",
        index=True,
        compute="_compute_responsible_team_id",
        store=True,
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        compute="_compute_company_id",
        store=True,
        required=False,
    )

    service_id = fields.Many2one(
        "riverflow.service",
        string="Service",
        compute="_compute_service_id",
        store=True,
        index=True,
        help="The service to which this record applies",
        ondelete="cascade",
    )

    tag_ids = fields.Many2many(
        comodel_name="riverflow.service.tag",
        relation="riverflow_state_record_service_tag_rel",
        column1="state_record_id",
        column2="tag_id",
        string="Tags",
        compute="_compute_tag_ids",
        ondelete="cascade",
        store=True,  # Needed for compute to be triggered
    )

    check_result_ids = fields.One2many(
        comodel_name="riverflow.check.result",
        inverse_name="state_record_id",
        string="Issues",
        auto_join=True,
    )

    @api.depends("master_model", "master_res_id")
    def _compute_service_id(self):
        for record in self:
            if record.master_model == "riverflow.service":
                record.service_id = record.master_res_id
            else:
                record.service_id = False

    def _inverse_service_id(self):
        for record in self:
            if record.service_id:
                record.master_model = "riverflow.service"
                record.master_res_id = record.service_id.id
            else:
                record.master_model = False
                record.master_res_id = False

    def init(self):
        # Create a unique index on (master_model, master_res_id) to ensure no duplicates
        self._cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS riverflow_global_state_unique_record
            ON %s (master_model, master_res_id)
        """
            % self._table
        )

    @api.depends("service_id.indented_name", "name")
    def _compute_indented_name(self):
        for slave in self:
            if slave.indent_level == 0:
                slave.indented_name = slave.name
            else:
                slave.indented_name = "%s%s" % (
                    "\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}"
                    * slave.indent_level,
                    slave.name,
                )

    @api.depends("service_id.internal_notes_summary")
    def _compute_internal_notes_summary(self):
        for record in self:
            record.internal_notes_summary = self._compute_internal_notes_summary_for_record(record)

    @api.model
    def _compute_internal_notes_summary_for_record(self, record):
        if record.service_id:
            return record.service_id.internal_notes_summary
        return False

    @api.depends("service_id.external_messages_summary")
    def _compute_external_messages_summary(self):
        for record in self:
            record.external_messages_summary = self._compute_external_messages_summary_for_record(record)

    @api.model
    def _compute_external_messages_summary_for_record(self, record):
        if record.service_id:
            return record.service_id.external_messages_summary
        return False

    @api.depends("service_id.unreviewed_message_count")
    def _compute_unreviewed_message_count(self):
        for record in self:
            record.unreviewed_message_count = self._compute_unreviewed_message_count_for_record(record)

    @api.model
    def _compute_unreviewed_message_count_for_record(self, record):
        if record.service_id:
            return record.service_id.unreviewed_message_count
        return 0

    @api.depends("service_id.tag_ids")
    def _compute_tag_ids(self):
        for record in self:
            record.tag_ids = self._compute_tag_ids_for_record(record)

    @api.model
    def _compute_tag_ids_for_record(self, record):
        if record.service_id:
            return record.service_id.tag_ids
        return False

    def _compute_state_json(self):
        # for rendering just the state name and workflow name
        for record in self:
            wf_state_text = record.current_workflow_name or ""
            if wf_state_text:
                if not record.state_name:
                    wf_state_text = "Not Started"
                else:
                    wf_state_text = record.state_name  # " | ".join([wf_state_text, record.state_name])

            # todo: store the icon so its not a lookup
            icon = record.workflow_id.icon or ""
            is_end_state = record.is_end_state == True

            state_json = {
                "text": wf_state_text,
                "workflow_icon": icon,
                "is_end_state": is_end_state,
                # this is not a start transition, so we can refresh the underlying list/form view
                "reload_on_close": True,
                "buttons": [],
            }

            record.state_json = state_json

    @api.depends("deadline")
    def _compute_deadline_formatted(self):
        for record in self:
            if record.deadline:
                # Format the deadline date
                record.deadline_formatted = datetime.strftime(record.deadline, DATE_FORMAT)
            else:
                record.deadline_formatted = False

    def _compute_timing_json(self):
        Service = self.env["riverflow.service"]
        for record in self:
            if not record.deadline:
                record.timing_json = False
                continue

            date_str = record.deadline.strftime(Service.DATE_FORMAT)

            today = fields.Date.today()
            days_remaining = (record.deadline - today).days
            is_past = record.deadline < today
            is_today = record.deadline == today

            record.timing_json = {
                "relative_days": "",
                "date": date_str,
                "days_remaining": days_remaining,
                "is_past": is_past,
                "is_today": is_today,
                "is_end_state": record.is_end_state,
            }

    # @api.depends("service_id.res_name", "name")
    # def _compute_res_name(self):
    #     """Compute res_name based on service_id.res_name or name."""
    #     for record in self:
    #         if record.service_id:
    #             record.res_name = record.service_id.res_name
    #         else:
    #             record.res_name = record.name

    @api.depends("service_id.workflow_id")
    def _compute_workflow_id(self):
        for record in self:
            record.workflow_id = self._compute_workflow_id_for_record(record)

    @api.model
    def _compute_workflow_id_for_record(self, record):
        if record.service_id:
            return record.service_id.workflow_id
        return False

    @api.depends("service_id.state_id")
    def _compute_state_id(self):
        for record in self:
            # print(f"old state_id: {record.state_id.name}")
            record.state_id = self._compute_state_id_for_record(record)
            # print(f"new state_id: {record.state_id.name}")

    @api.model
    def _compute_state_id_for_record(self, record):
        if record.service_id:
            return record.service_id.state_id
        return False

    @api.depends("service_id.is_end_state")
    def _compute_is_end_state(self):
        for record in self:
            record.is_end_state = self._compute_is_end_state_for_record(record)

    @api.model
    def _compute_is_end_state_for_record(self, record):
        if record.service_id:
            return record.service_id.is_end_state
        return False

    @api.depends("service_id.display_name", "name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = self._compute_display_name_for_record(record)

    @api.model
    def _compute_display_name_for_record(self, record):
        if record.service_id:
            return record.service_id.display_name
        return record.name

    @api.depends("service_id.active")
    def _compute_active(self):
        for record in self:
            record.active = self._compute_active_for_record(record)

    @api.model
    def _compute_active_for_record(self, record):
        if record.service_id:
            return record.service_id.active
        return True

    @api.depends("service_id.deadline")
    def _compute_deadline(self):
        for record in self:
            record.deadline = self._compute_deadline_for_record(record)

    @api.model
    def _compute_deadline_for_record(self, record):
        if record.service_id:
            return record.service_id.deadline
        return False

    @api.depends("service_id.end_date", "deadline")
    def _compute_end_date(self):
        for record in self:
            record.end_date = self._compute_end_date_for_record(record)

    @api.model
    def _compute_end_date_for_record(self, record):
        if record.service_id:
            return record.service_id.end_date_for_calendar
        return record.deadline

    @api.depends("service_id.root_name")
    def _compute_root_name(self):
        for record in self:
            if record.service_id:
                record.root_name = record.service_id.root_name
            else:
                record.root_name = False

    @api.depends("service_id.root_id")
    def _compute_root_id(self):
        for record in self:
            if record.service_id:
                record.root_id = record.service_id.root_id
            else:
                record.root_id = False

    @api.depends("service_id.sequence")
    def _compute_sequence(self):
        for record in self:
            if record.service_id:
                record.sequence = record.service_id.sequence
            else:
                record.sequence = 1

    @api.depends("service_id.tag_ids")
    def _compute_tag_ids(self):
        for record in self:
            if record.service_id:
                record.tag_ids = record.service_id.tag_ids
            else:
                record.tag_ids = False

    @api.depends("service_id.res_id")
    def _compute_res_id(self):
        for record in self:
            if record.service_id:
                record.res_id = record.service_id.res_id
            else:
                record.res_id = record.master_res_id

    @api.depends("service_id.res_model")
    def _compute_res_model(self):
        for record in self:
            if record.service_id:
                record.res_model = record.service_id.res_model
            else:
                record.res_model = record.master_model

    @api.depends("service_id.res_name", "name")
    def _compute_res_name(self):
        for record in self:
            if record.service_id:
                record.res_name = record.service_id.res_name
            else:
                record.res_name = record.name

    @api.depends("service_id.responsible_team_id")
    def _compute_responsible_team_id(self):
        for record in self:
            record.responsible_team_id = self._compute_responsible_team_id_for_record(record)

    @api.model
    def _compute_responsible_team_id_for_record(self, record):
        if record.service_id:
            return record.service_id.responsible_team_id
        return False

    @api.depends("service_id.company_id")
    def _compute_company_id(self):
        for record in self:
            record.company_id = self._compute_company_id_for_record(record)

    @api.model
    def _compute_company_id_for_record(self, record):
        if record.service_id:
            return record.service_id.company_id
        return False

    @api.depends("service_id.name")
    def _compute_name(self):
        for record in self:
            record.name = self._compute_name_for_record(record)

    @api.model
    def _compute_name_for_record(self, record):
        if record.service_id:
            return record.service_id.name
        return False

    @api.depends("service_id.indent_level")
    def _compute_indent_level(self):
        for record in self:
            if record.service_id:
                record.indent_level = record.service_id.indent_level
                if record.res_model != False:
                    # services that that are children of a subject-record need to be indented + 1 so they appear as children
                    record.indent_level += 1
            else:
                record.indent_level = 0

    def action_view_master_record(self):
        action = {
            "name": f"View {self.name}",
            "type": "ir.actions.act_window",
            "res_model": self.master_model,
            "res_id": self.master_res_id,
            "target": "current",
            "view_mode": "form",
        }
        return action

    def row_click(self):
        return self.action_view_master_record()

    @api.model
    def action_recompute_company_id(self):
        """Recompute company_id for all state records.
        This is a maintenance action to fix records where company_id was not properly set.
        """
        records = self.search([])
        records._compute_company_id()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Company Recompute"),
                "message": _("Recomputed company for %d state records", len(records)),
                "sticky": False,
                "type": "success",
            },
        }
