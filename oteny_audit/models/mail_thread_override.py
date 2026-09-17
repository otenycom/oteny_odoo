from odoo import models, api
from odoo.addons.mail.models.mail_thread import MailThread


# Store original MailThread methods
original_mailthread_create = MailThread.create
original_mailthread_write = MailThread.write


@api.model_create_multi
def patched_mailthread_create(self, vals_list):
    """Override MailThread.create to disable tracking by default."""
    return original_mailthread_create(self.with_context(tracking_disable=True), vals_list)


def patched_mailthread_write(self, vals):
    """Override MailThread.write to disable tracking by default."""
    return original_mailthread_write(self.with_context(tracking_disable=True), vals)


# Apply patches to MailThread class specifically
MailThread.create = patched_mailthread_create
MailThread.write = patched_mailthread_write
