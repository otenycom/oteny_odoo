/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";

/**
 * Patches the ListRenderer.Record to automatically add a 'row-highlight-info' class
 * to any row in a list view if the record has a field `highlight_row` that is true.
 *
 * This allows a model inheriting from `riverflow.highlight.row.mixin` to visually
 * highlight recently updated rows without needing a custom js_class on the view.
 */
patch(ListRenderer.prototype, {
    getRowClass(record) {
        let classNames = super.getRowClass(record);
        if (record.data.highlight_row) {
            if (!record.data.highlight_row_type) {
                classNames += (" row-bg-info");
            } else {
                classNames += (" row-bg-" + record.data.highlight_row_type);
            }
        }
        return classNames;
    },
}); 