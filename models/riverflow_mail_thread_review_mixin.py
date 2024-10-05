from odoo import api, fields, models, tools
from odoo.tools import html2plaintext
from odoo.addons.riverflow.util import is_neutralized_or_development  # type: ignore
import logging

_logger = logging.getLogger(__name__)


class MailThreadReviewMixin(models.AbstractModel):
    _name = "riverflow.mail.thread.review.mixin"
    _description = "Mail Thread Review Mixin"
    _inherit = ["mail.thread"]

    responsible_team_id = fields.Many2one(
        "riverflow.team",
        string="Responsible Team",
        tracking=True,
        help="Team executing the workflow of this log entry. This team is also responsible for reviewing external messages.",
        index=True,
    )

    internal_note_ids = fields.Many2many(
        comodel_name="mail.message",
        column1="res_id",
        column2="message_id",
        string="Internal Notes",
        compute="_compute_internal_note_ids",
        store=False,
    )

    external_message_ids = fields.Many2many(
        comodel_name="mail.message",
        column1="res_id",
        column2="message_id",
        string="External Messages",
        compute="_compute_external_message_ids",
        store=False,
    )
    unreviewed_message_ids = fields.Many2many(
        comodel_name="mail.message",
        column1="res_id",
        column2="message_id",
        string="Unreviewed Messages",
        compute="_compute_unreviewed_message_ids",
        store=False,
    )
    # field to store messages specifically from external senders, which
    # will trigger a needs review flag
    message_from_external_sender_ids = fields.Many2many(
        comodel_name="mail.message",
        column1="res_id",
        column2="message_id",
        string="Messages from External Senders",
        compute="_compute_message_from_external_sender_ids",
        store=False,
    )

    # todo: make this a JSON field and render the summaries properly, maybe with a custom widget and a popover
    internal_notes_summary = fields.Html(
        string="Top 3 Internal Notes",
        compute="_compute_latest_internal_notes",
        inverse="_inverse_internal_notes_summary",
        store=True,
        tracking=False,
        index="trigram",
    )

    def _inverse_internal_notes_summary(self):
        for record in self:
            if record.internal_notes_summary:
                plain_text = record.internal_notes_summary
                record.message_post(
                    body=plain_text,
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
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
    external_messages_summary = fields.Html(
        string="Top 3 External Messages",
        compute="_compute_external_messages_summary",
        store=True,
        index="trigram",
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

    @tools.ormcache()
    def _get_system_user_id(self):
        return self.env.ref("base.user_root").id  # always id 1, login name __system__

    @api.depends("message_ids", "external_message_ids")
    def _compute_message_from_external_sender_ids(self):
        """
        Compute method for message_from_external_sender_ids.
        This field contains messages that have a sender who is not an internal user of the system.
        """

        def _is_from_external_sender(message):
            # Also tried this, but if a reply is made from an email address linked to a user,
            #  it will not be considered an external message, which is not helpful for testing
            # return not message.author_id or not any(
            #     user.has_group("base.group_user")
            #     for user in message.author_id.user_ids
            # )

            # the inbound message robot posts customer messages as the system user
            is_created_by_system_user = (
                message.create_uid.id == self._get_system_user_id()
            )
            return is_created_by_system_user

        for record in self:
            if False and is_neutralized_or_development():
                # _logger.warning(
                #     "Running in development or neutralized mode, skipping external sender filtering"
                # )
                record.message_from_external_sender_ids = record.external_message_ids
            else:
                # _logger.info(
                #     "Running in production mode, filtering external sender messages"
                # )
                messages_from_external_senders = self.env["mail.message"]
                for message in record.external_message_ids:
                    if _is_from_external_sender(message):
                        messages_from_external_senders |= message

                record.message_from_external_sender_ids = messages_from_external_senders

    def _format_message_body(self, body, max_length=100):
        # Convert body to string, remove Markup wrapper if present, and convert to plain text
        body_str = html2plaintext(str(body))
        body_str = " ".join(body_str.split())
        if len(body_str) > max_length:
            body_str = body_str[:max_length] + "..."
        return f'<p style="margin-bottom: 0rem;">{body_str}</p>'

    @api.depends("message_ids.body")
    def _compute_latest_internal_notes(self):
        for record in self:
            formatted_notes = [
                self._format_message_body(message.body)
                for message in record.internal_note_ids[:3]
            ]
            if len(formatted_notes) > 0:
                record.internal_notes_summary = "".join(formatted_notes)
            else:
                record.internal_notes_summary = False  # needed for Odoo search

    @api.depends("message_ids.body")
    def _compute_external_messages_summary(self):
        for record in self:
            sorted_messages = record.external_message_ids.sorted(
                key=lambda m: m.date, reverse=True
            )[:3]
            formatted_messages = [
                self._format_message_body(message.body or message.subject or "")
                for message in sorted_messages
            ]
            if len(formatted_messages) > 0:
                record.external_messages_summary = "".join(formatted_messages)
            else:
                record.external_messages_summary = False  # needed for Odoo search

    @api.depends("message_ids", "last_external_message_review_time")
    def _compute_unreviewed_message_ids(self):
        for record in self:
            record.unreviewed_message_ids = (
                record.message_from_external_sender_ids.filtered(
                    lambda m: not record.last_external_message_review_time
                    or m.date > record.last_external_message_review_time
                )
            )

    @api.depends("message_ids", "external_message_ids")
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
            "view_mode": "list,form",
            "domain": [("id", "in", self.mapped("external_message_ids").ids)],
            "context": {
                "default_model": self._name,
                "default_res_id": self.ids[0] if self.ids else False,
            },
        }
        if len(self) == 1:
            action["context"]["default_res_id"] = self.id
        return action

    # rely on  @api.depends decorators
    # def _message_create(self, values_list):
    #     messages = super()._message_create(values_list)
    #     self.invalidate_recordset(
    #         [
    #             "external_message_ids",
    #             "unreviewed_message_ids",
    #             "external_messages_summary",
    #         ]
    #     )
    #     return messages
