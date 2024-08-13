from odoo import api, fields, models
from odoo.tools import html2plaintext
from odoo.addons.riverflow.util import is_neutralized_or_development  # type: ignore


class MailThreadReviewMixin(models.AbstractModel):
    _name = "riverflow.mail.thread.review.mixin"
    _description = "Mail Thread Review Mixin"
    _inherit = ["mail.thread"]

    internal_note_ids = fields.Many2many(
        "mail.message",
        "mail_message_internal_rel",
        "res_id",
        "message_id",
        string="Internal Notes",
        compute="_compute_internal_note_ids",
        store=True,
    )

    internal_notes_summary = fields.Html(
        string="Top 3 Internal Notes",
        compute="_compute_latest_internal_notes",
        store=False,
        tracking=False,
        index="trigram",
    )

    external_message_ids = fields.Many2many(
        "mail.message",
        "mail_message_external_rel",
        "res_id",
        "message_id",
        string="External Messages",
        compute="_compute_external_message_ids",
        store=True,
    )
    unreviewed_message_ids = fields.Many2many(
        "mail.message",
        "mail_message_unreviewed_rel",
        "res_id",
        "message_id",
        string="Unreviewed Messages",
        compute="_compute_unreviewed_message_ids",
        store=True,
    )
    last_external_message_review_time = fields.Datetime(
        string="External Messages Reviewed",
        tracking=True,
    )
    external_message_count = fields.Integer(
        string="External Message Count",
        compute="_compute_external_message_count",
        store=True,
    )
    unreviewed_message_count = fields.Integer(
        string="Review",
        help="Count of inbound messages that have not yet been reviewed",
        compute="_compute_unreviewed_message_count",
        store=True,
    )
    external_messages_summary = fields.Char(
        string="Top 3 External Messages",
        compute="_compute_external_messages_summary",
        store=False,
        index="trigram",
    )

    # field to store messages specifically from external senders, which
    # will trigger a needs review flag
    message_from_external_sender_ids = fields.Many2many(
        "mail.message",
        "mail_message_external_sender_rel",
        "res_id",
        "message_id",
        string="Messages from External Senders",
        compute="_compute_message_from_external_sender_ids",
        store=True,
    )

    def _get_filtered_messages(self, select_internal):
        """
        Helper function to get message IDs based on message type and subtype internal flag.

        :param select_internal: Boolean, True to select internal messages, False for external
        :return: Recordset of filtered mail.message
        """
        valid_message_types = ["email", "comment", "email_outgoing"]
        return self.message_ids.filtered(
            lambda m: m.message_type in valid_message_types
            and bool(m.subtype_id.internal) == select_internal
        )

    @api.depends("message_ids")
    def _compute_internal_note_ids(self):
        for record in self:
            record.internal_note_ids = record._get_filtered_messages(
                select_internal=True
            )

    @api.depends("message_ids")
    def _compute_external_message_ids(self):
        for record in self:
            record.external_message_ids = record._get_filtered_messages(
                select_internal=False
            )

    @api.depends("external_message_ids")
    def _compute_message_from_external_sender_ids(self):
        """
        Compute method for message_from_external_sender_ids.
        This field contains messages that have a sender who is not an internal user of the system.
        """
        for record in self:
            if is_neutralized_or_development():
                record.message_from_external_sender_ids = record.external_message_ids
            else:
                record.message_from_external_sender_ids = (
                    record.external_message_ids.filtered(
                        lambda m: not m.author_id
                        or not m.author_id.user_ids.filtered(
                            lambda u: u.has_group("base.group_user")
                        )
                    )
                )

    @api.depends("internal_note_ids.body")
    def _compute_latest_internal_notes(self):
        for record in self:
            # Concatenate the bodies of the latest two messages, marking them up as safe HTML
            # todo: add a css class to the <p> tag, as the default css has too big a margin
            # p {   margin-top: 0;    margin-bottom: 1rem; }
            internal_notes_summary = ""
            for message in record.internal_note_ids:
                # trim the Markup wrapper class from the body value
                body = str(message.body)
                # Replace <p> tags with <p> tags that have inline styles
                body = body.replace("<p>", '<p style="margin-bottom: 0rem;">')
                internal_notes_summary += body

            record.internal_notes_summary = internal_notes_summary

    @api.depends("external_message_ids")
    def _compute_external_messages_summary(self):
        for record in self:
            summary = []
            for message in record.external_message_ids.sorted(
                key=lambda m: m.date, reverse=True
            )[
                :3
            ]:  # Get the 3 most recent external messages
                # Convert HTML to plain text and remove any line breaks
                content = html2plaintext(message.body or message.subject or "").replace(
                    "\n", " "
                )
                # This works because replace('\n', ' ') removes all newline characters,
                # effectively making the content a single line of text
                truncated_content = (
                    content[:100] + "..." if len(content) > 100 else content
                )
                summary.append(truncated_content.strip())

            record.external_messages_summary = " | ".join(summary) if summary else ""

    @api.depends("external_message_ids", "last_external_message_review_time")
    def _compute_unreviewed_message_ids(self):
        for record in self:
            record.unreviewed_message_ids = record.external_message_ids.filtered(
                lambda m: not record.last_external_message_review_time
                or m.date > record.last_external_message_review_time
            )

    @api.depends("external_message_ids")
    def _compute_external_message_count(self):
        for record in self:
            record.external_message_count = len(record.external_message_ids)

    @api.depends("unreviewed_message_ids")
    def _compute_unreviewed_message_count(self):
        for record in self:
            record.unreviewed_message_count = len(record.unreviewed_message_ids)

    def action_mark_external_messages_reviewed(self):
        self.write({"last_external_message_review_time": fields.Datetime.now()})

    def action_view_external_messages(self):
        action = {
            "type": "ir.actions.act_window",
            "name": "External Messages",
            "res_model": "mail.message",
            "view_mode": "tree,form",
            "domain": [("id", "in", self.mapped("external_message_ids").ids)],
            "context": {
                "default_model": self._name,
                "default_res_id": self.ids[0] if self.ids else False,
            },
        }
        if len(self) == 1:
            action["context"]["default_res_id"] = self.id
        return action

    def _message_create(self, values_list):
        messages = super()._message_create(values_list)
        self.invalidate_recordset(
            [
                "external_message_ids",
                "unreviewed_message_ids",
                "external_messages_summary",
            ]
        )
        return messages
