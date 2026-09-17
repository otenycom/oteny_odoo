/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SearchModel } from "@web/search/search_model";
import { isShortcutShown, showWhenContext } from "@oteny_shortcut/views/show_when";

// Why this exists:
// The shortcut banner reads its buttons from the favorites a view already
// loads, so a view open costs no extra request for shortcuts (Thijs,
// 2026-09-14). ir.filters.get_filters (oteny_shortcut/models/ir_filters.py)
// carries the shortcut fields on every favorite it returns; Odoo's
// SearchModel keeps only the keys it knows when it turns an ir.filters row
// into a favorite search item, so this patch copies the shortcut keys along
// and answers, for this view, whether the shortcut's button shows here.
//
// Second rule: a shortcut's Default Filter applies only where its Show When
// expression is true. The favorite itself stays in the Favorites menu, but a
// shortcut meant for the lists inside a form must not narrow the model's
// top-level views at open.
patch(SearchModel.prototype, {
    _createGroupOfFavorites(irFilters) {
        const context = this._shortcutShowWhenContext();
        const filters = irFilters.map((irFilter) => {
            const isHiddenShortcut =
                irFilter.is_default &&
                irFilter.shortcut_sequence > 0 &&
                !isShortcutShown(irFilter.shortcut_show_when, context);
            return isHiddenShortcut ? { ...irFilter, is_default: false } : irFilter;
        });
        return super._createGroupOfFavorites(filters);
    },

    _irFilterToFavorite(irFilter) {
        const favorite = super._irFilterToFavorite(irFilter);
        const sequence = irFilter.shortcut_sequence || 0;
        return Object.assign(favorite, {
            shortcutSequence: sequence,
            shortcutViewType: irFilter.shortcut_view_type || false,
            shortcutIcon: irFilter.shortcut_icon || false,
            shortcutLayout: irFilter.shortcut_layout || false,
            shortcutShowWhen: irFilter.shortcut_show_when || "",
            shortcutVisible:
                sequence > 0 &&
                isShortcutShown(irFilter.shortcut_show_when, this._shortcutShowWhenContext()),
        });
    },

    /**
     * The place of this search model for a Show When expression: a top-level
     * view of the given type, no subject.
     */
    _shortcutShowWhenContext() {
        return showWhenContext({ view: this.env.config?.viewType || false });
    },
});
