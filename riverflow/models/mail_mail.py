# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError  # For raising user-facing errors

_logger = logging.getLogger(__name__)


class MailMailExtended(models.Model):
    _inherit = "mail.mail"

    def _extract_all_recipient_emails(self, mail_record):
        """
        Helper method to extract and normalize all unique recipient email addresses
        from the mail.mail record's email_to, email_cc, and recipient_ids fields.
        Returns a set of lowercase, normalized email addresses.
        """
        emails = set()
        if mail_record.email_to:
            # email_normalize_all handles comma-separated strings and returns a list
            emails.update(tools.mail.email_normalize_all(mail_record.email_to))
        if mail_record.email_cc:
            emails.update(tools.mail.email_normalize_all(mail_record.email_cc))

        if mail_record.recipient_ids:
            # Partner email fields can also be comma-separated
            for partner in mail_record.recipient_ids:
                if partner.email:
                    emails.update(tools.mail.email_normalize_all(partner.email))

        # Filter out any empty strings, ensure lowercase, and that it's a valid-looking email structure.
        # tools.mail.email_normalize_all already does a good job,
        # but an explicit check for '@' is good before splitting.
        return {email.lower() for email in emails if email and "@" in email}

    def send(self, auto_commit=False, raise_exception=False, post_send_callback=None):
        """
        Override send to perform a pre-check for disallowed recipient domains.
        If any mail is addressed to a disallowed domain, an error is raised immediately.
        Otherwise, the standard send process continues.
        """
        # Retrieve the list of allowed domains from system parameters
        allowed_domains_str = (
            self.env["ir.config_parameter"].sudo().get_param("riverflow.restrict_email_recipients_to", "")
        )

        # If no domains are specified in the configuration, no restrictions apply.
        # Proceed with the original behavior.
        if not allowed_domains_str:
            return super().send(
                auto_commit=auto_commit,
                raise_exception=raise_exception,
                post_send_callback=post_send_callback,
            )

        allowed_domains = {
            domain.strip().lower() for domain in allowed_domains_str.split(",") if domain.strip()
        }

        # Iterate over each mail.mail record in the current recordset
        for mail_record in self:
            # This check primarily targets mails that are about to be sent.
            # Non-outgoing mails will be handled by super().send() or are not relevant to this pre-send check.
            if mail_record.state != "outgoing":
                continue

            all_recipient_emails = self._extract_all_recipient_emails(mail_record)

            # If there are no valid, extractable email addresses, there are no domains to check.
            # Let the standard send process handle this (e.g., it might fail due to no recipients).
            if not all_recipient_emails:
                continue

            for r_email in all_recipient_emails:
                try:
                    # Extract domain part from the normalized email
                    # _extract_all_recipient_emails ensures '@' is present
                    domain_part = r_email.split("@", 1)[1]

                    if domain_part not in allowed_domains:
                        error_msg = _(
                            "Email sending blocked for mail (ID: %s, Subject: '%s'). "
                            "Recipient '%s' has a disallowed email domain '%s'. "
                            "Allowed domains are: %s."
                        ) % (
                            mail_record.id,
                            mail_record.subject,
                            r_email,
                            domain_part,
                            ", ".join(
                                sorted(list(allowed_domains))
                            ),  # Use sorted list for consistent error messages
                        )

                        # Handle based on raise_exception parameter
                        if raise_exception:
                            _logger.error(error_msg)
                            # Raise UserError to stop the process and inform the user
                            raise UserError(error_msg)
                        else:
                            # In cron job context, mark email as failed and log the issue
                            failure_reason = _(
                                "Email blocked due to disallowed recipient domain '%s'. " "Recipient: %s"
                            ) % (domain_part, r_email)
                            _logger.warning(
                                "Marking email (ID: %s, Subject: '%s') as failed due to disallowed domain '%s' in recipient '%s'",
                                mail_record.id,
                                mail_record.subject,
                                domain_part,
                                r_email,
                            )
                            # Mark as exception to remove from queue
                            mail_record.write(
                                {
                                    "state": "exception",
                                    "failure_reason": failure_reason,
                                    "failure_type": "mail_email_invalid",
                                }
                            )
                            # Skip this mail record and continue with others
                            continue
                except IndexError:
                    # This case should ideally not be reached if _extract_all_recipient_emails works correctly,
                    # as it's supposed to return only valid-looking emails with '@'.
                    # However, as a safeguard:
                    error_msg = _(
                        "Email sending blocked for mail (ID: %s, Subject: '%s'). "
                        "Recipient email '%s' is malformed and its domain could not be checked."
                    ) % (mail_record.id, mail_record.subject, r_email)

                    # Handle based on raise_exception parameter
                    if raise_exception:
                        _logger.error(error_msg)
                        # Raise UserError to halt on problematic data.
                        raise UserError(error_msg)
                    else:
                        # In cron job context, mark email as failed and log the issue
                        failure_reason = (
                            _(
                                "Email blocked due to malformed recipient email '%s' - domain could not be checked."
                            )
                            % r_email
                        )
                        _logger.warning(
                            "Marking email (ID: %s, Subject: '%s') as failed due to malformed recipient email '%s'",
                            mail_record.id,
                            mail_record.subject,
                            r_email,
                        )
                        # Mark as exception to remove from queue
                        mail_record.write(
                            {
                                "state": "exception",
                                "failure_reason": failure_reason,
                                "failure_type": "mail_email_invalid",
                            }
                        )
                        # Skip this mail record and continue with others
                        continue

        # If all mails in the batch have passed the domain check, proceed with the original send method
        return super().send(
            auto_commit=auto_commit, raise_exception=raise_exception, post_send_callback=post_send_callback
        )
