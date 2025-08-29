# -*- coding: utf-8 -*-
# Part of Oteny. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)

# Check if we can import from odoo and if mail.thread exists
try:
    from odoo import models, api, registry

    # Check if mail.thread model exists in the registry
    mail_thread_available = "mail.thread" in getattr(registry, "models", {})

    if mail_thread_available:

        class MailThreadOverride(models.AbstractModel):
            """Override mail.thread to check for system-wide tracking disable configuration."""

            _inherit = "mail.thread"

            def create(self, vals_list):
                """Override create to check for system-wide tracking disable."""
                if self._is_tracking_disabled():
                    return super().with_context(tracking_disable=True).create(vals_list)
                return super().create(vals_list)

            def write(self, vals):
                """Override write to check for system-wide tracking disable."""
                if self._is_tracking_disabled():
                    return super().with_context(tracking_disable=True).write(vals)
                return super().write(vals)

            @api.model
            def _is_tracking_disabled(self):
                """Check if mail tracking is disabled system-wide."""
                # Check registry flag first (more reliable for tests)
                registry_disabled = getattr(self.env.registry, "_mail_tracking_disabled", False)

                if registry_disabled:
                    return True

                # Fallback to configuration parameter for production use
                try:
                    config_disabled = (
                        self.env["ir.config_parameter"].sudo().get_param("mail.tracking_disabled") == "1"
                    )
                    return config_disabled
                except Exception:
                    # If ir.config_parameter is not available, assume tracking is enabled
                    return False

    else:
        _logger.info("Mail module not available, skipping mail.thread override")

        # Create a dummy class that does nothing
        class MailThreadOverride:
            pass

except ImportError:
    _logger.warning("Odoo not available, skipping mail.thread override")

    # Create a dummy class that does nothing
    class MailThreadOverride:
        pass
