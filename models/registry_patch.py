import logging

from odoo.modules import registry
from odoo.api import Environment
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Keep a reference to the original signal_changes method
_original_signal_changes = registry.Registry.signal_changes


def _signal_changes_and_run_audit(self):
    """
    Monkey-patched version of Registry.signal_changes.
    This method is called once the registry is fully loaded and ready, just
    before other processes are notified of changes. This is the ideal moment
    to run our synchronous, one-time setup.
    """
    # The first time this is called during a server startup, `self.ready` is True.
    # We add a guard to ensure our code runs only once per registry instantiation.
    if not getattr(self, "_audit_actions_setup_done", False):
        # Set a flag on the registry instance to prevent re-execution.
        self._audit_actions_setup_done = True
        try:
            _logger.info("Registry is ready. Running initial audit action setup just before signaling.")
            # We must create a new cursor and environment with the current registry.
            with self.cursor() as cr:
                env = Environment(cr, SUPERUSER_ID, {})
                env["oteny.audit.log"].install_for_all_models_action()
                _logger.info("Initial audit action setup completed successfully.")

                # IMPORTANT: We have modified the registry by adding server actions,
                # so we must mark it as invalidated. The original signal_changes
                # will use this flag to notify other processes.
                self.registry_invalidated = True

        except Exception:
            _logger.error(
                "Failed to run initial audit action setup before signaling.",
                exc_info=True,
            )

    # Always call the original method to perform the actual signaling.
    _original_signal_changes(self)


# Apply the monkey-patch
registry.Registry.signal_changes = _signal_changes_and_run_audit
