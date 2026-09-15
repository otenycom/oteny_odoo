/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

/**
 * Open the Set Up Shortcut wizard (wizard/shortcut_setup_wizard.py) for one
 * favorite. The wizard is Python; this is only its door, called by the gear
 * that appears when a filter is selected (the banner, the in-form row).
 *
 * @param {Object} actionService
 * @param {Object} params
 * @param {number} params.filterId the ir.filters id
 * @param {string} [params.subjectModel] the form's model, so "Only in the
 *   form of ..." opens with that form chosen
 * @param {boolean} [params.noReload] close instead of reloading the page;
 *   the caller refreshes what it shows (the in-form row)
 * @param {Function} [params.onClose]
 */
export function openShortcutSetup(actionService, { filterId, subjectModel, noReload, onClose }) {
    return actionService.doAction(
        {
            type: "ir.actions.act_window",
            name: _t("Set Up Shortcut"),
            res_model: "shortcut.setup.wizard",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_filter_id: filterId,
                shortcut_subject_model: subjectModel || false,
                shortcut_wizard_no_reload: Boolean(noReload),
            },
        },
        { onClose }
    );
}
