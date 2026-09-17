/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// Why this exists:
// The in-form shortcut row (views/x2many_field_patch.js) narrows an x2many
// list to the rows its active filter matches. The rows are hidden here, by
// a class on the row, instead of by changing the renderer's row loop: other
// modules (project, for one) derive their own row templates from that loop
// with an xpath on it, and the field's value must stay untouched so the form
// does not become dirty. A row that is not saved yet always shows.
patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        // Subscribe this renderer to the field's shortcut state, so a new
        // match result re-renders the rows.
        this.x2manyShortcuts = this.env.x2manyShortcuts
            ? useState(this.env.x2manyShortcuts)
            : null;
    },

    getRowClass(record) {
        const classes = super.getRowClass(record);
        const matchedIds = this.x2manyShortcuts?.matchedIds;
        if (matchedIds && !record.isNew && !matchedIds.has(record.resId)) {
            return `${classes} o_x2many_shortcut_hidden d-none`;
        }
        return classes;
    },
});
