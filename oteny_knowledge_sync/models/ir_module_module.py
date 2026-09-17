"""Run the skill sync after an upgrade of any module that lives under a configured root.

``_register_hook`` runs once per registry load; ``registry.updated_modules`` says
which modules were installed or upgraded in this load, so a plain restart syncs
nothing. Test runs skip the sync.
"""
import logging
from pathlib import Path

from odoo import models
from odoo.modules.module import get_module_path
from odoo.tools import config

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _register_hook(self):
        super()._register_hook()
        updated = set(self.env.registry.updated_modules or ())
        if not updated or config["test_enable"]:
            return
        if "oteny.knowledge.sync" not in self.env:
            return
        sync = self.env["oteny.knowledge.sync"]
        roots = {Path(path).resolve() for _label, path in sync._skill_roots()}
        if not roots:
            return
        touched = set()
        for name in updated:
            try:
                module_dir = Path(get_module_path(name) or "").resolve()
            except Exception:  # noqa: BLE001 — a module without a path syncs nothing
                continue
            if module_dir.parent in roots:
                touched.add(name)
        if not touched:
            return
        try:
            _logger.info("Knowledge sync after upgrade of %s", ", ".join(sorted(touched)))
            sync.sync_skills_to_knowledge()
        except Exception as exc:  # noqa: BLE001 — the sync never blocks an upgrade
            _logger.error("Knowledge sync failed after upgrade: %s", exc, exc_info=True)
