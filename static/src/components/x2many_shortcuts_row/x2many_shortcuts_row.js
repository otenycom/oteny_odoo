/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * The row of shortcut buttons above an in-form list (an x2many field in
 * list mode): the shortcuts of the list's model whose Show When expression
 * is true for this form. One button is active at a time; clicking the
 * active one again shows every row. A gear next to the active button opens
 * the Set Up Shortcut wizard for it. The X2ManyField patch
 * (views/x2many_field_patch.js) owns the state and the filtering, this
 * component only draws the buttons, in the same style as the banner above
 * top-level views.
 *
 * inToolbar: the row sits in the toolbar of buttons above the list, at its
 * right end (Thijs, 2026-09-15), instead of on its own line above the list.
 */
export class X2ManyShortcutsRow extends Component {
    static template = "oteny_shortcut.X2ManyShortcutsRow";
    static props = {
        shortcuts: Array,
        activeId: { optional: true },
        onClick: Function,
        onSetup: Function,
        inToolbar: { type: Boolean, optional: true },
    };

    get activeShortcut() {
        return this.props.shortcuts.find((shortcut) => shortcut.id === this.props.activeId) || null;
    }
}
