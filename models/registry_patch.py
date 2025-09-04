import logging

from odoo.modules import registry
from odoo.api import Environment
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Keep a reference to the original signal_changes method
_original_signal_changes = registry.Registry.signal_changes


def _signal_changes_and_run_audit(self):
    """
    Monkey-patched version of Registry.signal_changes to run the audit setup.

    The setup is triggered only when the registry is invalidated, which happens
    during module installation or updates. This prevents the setup from running
    needlessly on every server restart or for every new worker process, a common
    scenario on platforms like Odoo.sh.
    """
    # A per-process flag to ensure the setup runs at most once per registry instance.
    setup_done = getattr(self, "_audit_actions_setup_done", False)

    # Only perform the setup if there's a genuine registry change.
    if self.registry_invalidated and not setup_done:
        self._audit_actions_setup_done = True
        try:
            _logger.info("Registry is invalidated; running audit action setup before signaling.")
            with self.cursor() as cr:
                env = Environment(cr, SUPERUSER_ID, {})
                env["oteny.audit.log"].install_for_all_models_action()
                _logger.info("Audit action setup completed successfully.")

        except Exception:
            _logger.error(
                "Failed to run audit action setup before signaling.",
                exc_info=True,
            )

    # Always call the original method to perform the actual signaling.
    # It will notify other processes if self.registry_invalidated is True.
    _original_signal_changes(self)


# Apply the monkey-patch
registry.Registry.signal_changes = _signal_changes_and_run_audit
