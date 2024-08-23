from odoo import models, fields, api, _

# Define the date format constant here instead of relying on Service class
DATE_FORMAT = "%d/%m/%Y"


class RiverflowStateRecord(models.Model):
    _name = "riverflow.state.record"
    _description = "Global View of Riverflow State"
    _order = "res_model,res_name,res_id,is_subject desc,root_name,root_id,sequence"

    active = fields.Boolean(
        default=True, help="Set active to false to archive the service"
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
        return [
            (model.model, model.name)
            for model in self.env["ir.model"].sudo().search([])
        ]

    # Fields to identify the record
    name = fields.Char(string="Name", required=True, index=True)
    display_name = fields.Char(string="Display Name", required=True, index=True)
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
                record.master_record_reference = (
                    f"{record.master_model},{record.master_res_id}"
                )
            else:
                record.master_record_reference = False

    # --- service fields
    res_id = fields.Integer(string="Subject of Service ID", required=False)
    res_model = fields.Char(
        string="Subject of Service Model Name",
    )
    res_name = fields.Char(
        string="Subject of Service",
        store=True,
        index="trigram",
    )

    root_id = fields.Integer(string="Root ID", index=True)
    root_name = fields.Char(string="Root Name", index=True)
    indented_name = fields.Char("Record", compute="_compute_indented_name", store=False)

    deadline = fields.Date(
        "Deadline Date",
        help="Deadline based on the project-deadline and the relative day of this service",
        index=True,
    )
    deadline_formatted = fields.Char(
        "Deadline", compute="_compute_deadline_formatted", store=False
    )

    timing_json = fields.Json(
        "Timing",
        compute="_compute_timing_json",
        store=False,
    )
    sequence = fields.Integer(
        default=1,
        index=True,
        required=True,
    )

    tag_ids = fields.Many2many(
        comodel_name="riverflow.service.tag",
        relation="riverflow_state_record_tag_rel",
        column1="state_record_id",
        column2="tag_id",
        string="Tags",
    )

    # Fields from RiverflowWorkflowStateMixin
    workflow_id = fields.Many2one(
        "riverflow.workflow",
        string="Workflow",
        readonly=True,
    )
    state_id = fields.Many2one(
        "riverflow.state",
        string="Workflow State",
        readonly=True,
        index=True,
    )
    state_json = fields.Json(
        string="State",
        readonly=True,
        compute="_compute_state_json",
    )

    # fields from MailThreadReviewMixin
    internal_notes_summary = fields.Html(
        string="Internal Notes", compute="_compute_internal_notes_summary"
    )
    external_messages_summary = fields.Html(
        string="External Messages", compute="_compute_external_messages_summary"
    )
    unreviewed_message_count = fields.Integer(
        string="Review", compute="_compute_unreviewed_message_count"
    )

    @api.depends("master_record_reference")
    def _compute_indented_name(self):
        for slave in self:
            master = self.env[slave.master_model].browse(slave.master_res_id)
            if hasattr(master, "indented_name"):
                slave.indented_name = (
                    "\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}\N{NO-BREAK SPACE}"
                    + master.indented_name
                )
            else:
                slave.indented_name = master.name

    @api.depends("master_record_reference")
    def _compute_internal_notes_summary(self):
        for slave in self:
            master = self.env[slave.master_model].browse(slave.master_res_id)
            if hasattr(master, "internal_notes_summary"):
                slave.internal_notes_summary = master.internal_notes_summary
            else:
                slave.internal_notes_summary = False

    @api.depends("master_record_reference")
    def _compute_external_messages_summary(self):
        for slave in self:
            master = self.env[slave.master_model].browse(slave.master_res_id)
            # Check if the master record has the 'external_messages_summary' attribute
            if hasattr(master, "external_messages_summary"):
                slave.external_messages_summary = master.external_messages_summary
            else:
                # If the attribute doesn't exist, set a default value or handle accordingly
                slave.external_messages_summary = False

    @api.depends("master_record_reference")
    def _compute_unreviewed_message_count(self):
        for slave in self:
            master = self.env[slave.master_model].browse(slave.master_res_id)
            # Check if the master record has the 'unreviewed_message_count' attribute
            if hasattr(master, "unreviewed_message_count"):
                slave.unreviewed_message_count = master.unreviewed_message_count
            else:
                # If the attribute doesn't exist, set a default value or handle accordingly
                slave.unreviewed_message_count = 0

    def init(self):
        # Create a unique index on (master_model, master_res_id) to ensure no duplicates
        self._cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS riverflow_global_state_unique_record
            ON %s (master_model, master_res_id)
        """
            % self._table
        )

    def _compute_state_json(self):
        for slave in self:
            master = slave.master_record_reference
            if hasattr(master, "state_json"):
                json = master.state_json

                json["buttons"] = [
                    {
                        "index": 0,
                        "caption": "View",
                        "help": "",
                        "action": "action_view_master_record",
                    }
                ]
                slave.state_json = json
            else:
                slave.state_json = False

    def action_view_master_record(self):
        master = self.master_record_reference
        action = {
            "name": "View " + self.name,
            "type": "ir.actions.act_window",
            "res_model": self.master_model,
            "res_id": self.master_res_id,
            "target": "current",
            "view_mode": "form",
        }

        return action

    @api.depends("deadline")
    def _compute_deadline_formatted(self):
        for slave in self:
            master = self.env[slave.master_model].browse(slave.master_res_id)
            if hasattr(master, "deadline_formatted"):
                slave.deadline_formatted = master.deadline_formatted
            else:
                slave.deadline_formatted = False

    def _compute_timing_json(self):
        for slave in self:
            master = slave.master_record_reference
            if hasattr(master, "timing_json"):
                slave.timing_json = master.timing_json
            else:
                slave.timing_json = False

    def action_button_click(self):
        master = self.master_record_reference
        action = master.action_button_click()
        action["res_model"] = self.master_model
        action["res_id"] = self.master_res_id
        action["target"] = "current"
        return action

    def unlink(self):
        """
        Override unlink method to clear res_model and res_id before deletion.
        This ensures that any potential references are cleaned up.
        """
        # self.write({
        #     'master_model': False,
        #     'master_res_id': False,
        # })
        return super(RiverflowStateRecord, self).unlink()
