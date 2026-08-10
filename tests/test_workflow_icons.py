"""Guard: every riverflow icon must exist in Odoo's FontAwesome build.

Odoo 19 ships FontAwesome 4.7 only. An icon field holding a newer
FontAwesome 5/6 class name (e.g. fa-file-invoice-dollar, fa-calendar-plus)
fails silently: the glyph renders as an empty box wherever the workflow or
transition is shown. The 2026-08-10 icon audit found several of these in
shipped data, so this test validates every icon class on riverflow
workflows, transitions and transition actions against the actual CSS file
shipped with the web module. It runs post_install, so it also covers the
records loaded by downstream modules (crewradar, crewradar_cuneus_sign, ...)
on a full test database.
"""

import re

from odoo.modules import get_module_path
from odoo.tests import TransactionCase, tagged


@tagged("riverflow", "post_install", "-at_install", "test_workflow_icons")
class TestWorkflowIcons(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        css_path = (
            get_module_path("web")
            + "/static/src/libs/fontawesome/css/font-awesome.css"
        )
        with open(css_path, encoding="utf-8") as css_file:
            css = css_file.read()
        # Glyph selectors look like ".fa-taxi:before"; aliases (fa-bank /
        # fa-institution / fa-university) each get their own selector, so a
        # flat set of all selector names covers them too.
        cls.valid_classes = set(re.findall(r"\.(fa-[\w-]+):before", css))
        if not cls.valid_classes:
            raise AssertionError("FontAwesome CSS yielded no glyph classes")

    def _assert_icons_valid(self, records, label):
        # Archived records still appear in pickers/history, so validate them
        # too — hence the explicit active_test=False (several riverflow
        # models have an active field).
        for record in records:
            if not record.icon:
                continue
            for token in record.icon.split():
                # Non-glyph helper classes like the bare "fa" prefix or
                # sizing modifiers are not glyphs; only fa-* tokens must
                # resolve to a real FontAwesome 4.7 glyph.
                if token.startswith("fa-"):
                    self.assertIn(
                        token,
                        self.valid_classes,
                        f"{label} '{record.display_name}' uses icon class "
                        f"'{token}' which does not exist in the FontAwesome "
                        "4.7 build shipped with Odoo (it would render as an "
                        "empty box). Pick an FA4 class instead.",
                    )

    def test_all_riverflow_icons_exist_in_fontawesome(self):
        env_no_active_test = self.env["riverflow.workflow"].with_context(
            active_test=False
        )
        self._assert_icons_valid(env_no_active_test.search([]), "Workflow")
        self._assert_icons_valid(
            self.env["riverflow.transition"].with_context(active_test=False).search([]),
            "Transition",
        )
        self._assert_icons_valid(
            self.env["riverflow.transition.action"]
            .with_context(active_test=False)
            .search([]),
            "Transition action",
        )
