/** @odoo-module **/

import { onMounted, onWillStart, useEffect, useRef, useState, useSubEnv } from "@odoo/owl";
import { Domain } from "@web/core/domain";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";
import { X2ManyShortcutsRow } from "@oteny_shortcut/components/x2many_shortcuts_row/x2many_shortcuts_row";
import { isShortcutShown, showWhenContext } from "@oteny_shortcut/views/show_when";
import { openShortcutSetup } from "@oteny_shortcut/views/shortcut_setup";

// Why this exists:
// A person looking at a list inside a form (the services of an employee, the
// credentials of a ship, ...) wants the same one-click filters the shortcut
// banner gives above a top-level list. An in-form list has no search model,
// so the banner cannot be reused; this patch gives every x2many field in
// list mode a row of buttons for the shortcuts of the list's model whose
// Show When expression is true for this form, with the form's record as
// subject (Thijs, 2026-09-14). It replaced a crewradar mixin that hard-coded
// three states for the Services tab.
//
// How a click filters:
// 1. The list loads every row (the page size is raised to the row count), so
//    the result is complete and no pager is needed while a filter is active.
// 2. The filter's domain is evaluated here, in the browser, exactly like a
//    favorite's domain (context_today() and relativedelta work), and the
//    server is asked which of the list's ids match it. The server does the
//    matching, so dotted paths and record rules apply.
// 3. The rows that do not match are hidden by the list renderer
//    (views/list_renderer_patch.js). The field's value is never touched: no
//    row is removed from the record, the form does not become dirty, and a
//    row added while a filter is active stays visible.
// A filter with Default Filter is active when the form opens. The last click
// is not remembered anywhere; every open starts on the default (decision).
//
// Where the row sits (Thijs, 2026-09-15): when a toolbar of buttons stands
// directly above the list (the crewradar tabs: "Add Service", "Full Screen"
// in a flex div right before the field), the row moves into that toolbar, at
// its right end, so the filters share the line with the actions. The toolbar
// is found after mount as the element before the field, and the row is
// rendered into it with a portal; without such a toolbar the row stays on its
// own line above the list.
//
// A gear next to the active button opens the Set Up Shortcut wizard
// (Python, wizard/shortcut_setup_wizard.py) for that filter, with this form's
// model as the "Only in the form of ..." choice; on close the row reloads its
// shortcuts instead of reloading the page, so unsaved edits in the form stay.

// Shortcuts per model for this page load; which of them show above a given
// list is decided per form (see x2manyShortcuts). An admin who changes the
// filters reloads the page to see the change, the same as for the banner.
const formShortcutsByModel = new Map();

export function loadFormShortcuts(orm, resModel) {
    if (!formShortcutsByModel.has(resModel)) {
        const promise = orm
            .call("ir.filters", "get_shortcuts", [resModel])
            .catch((error) => {
                formShortcutsByModel.delete(resModel);
                throw error;
            });
        formShortcutsByModel.set(resModel, promise);
    }
    return formShortcutsByModel.get(resModel);
}

export function clearFormShortcutsCache() {
    formShortcutsByModel.clear();
}

// Ids for the toolbars the rows are rendered into (an Owl portal needs a
// selector).
let toolbarCount = 0;

/**
 * The toolbar of buttons directly above an x2many field, if any: the
 * element right before the field's wrapper, when it is a flex row holding
 * buttons.
 *
 * @param {HTMLElement|null} fieldEl the field's root element
 * @returns {HTMLElement|null}
 */
export function findShortcutToolbar(fieldEl) {
    const wrapper = fieldEl?.closest(".o_field_widget") || fieldEl;
    const toolbar = wrapper?.previousElementSibling;
    if (
        toolbar &&
        toolbar.tagName === "DIV" &&
        toolbar.classList.contains("d-flex") &&
        toolbar.querySelector("button")
    ) {
        return toolbar;
    }
    return null;
}

X2ManyField.components = { ...X2ManyField.components, X2ManyShortcutsRow };

patch(X2ManyField.prototype, {
    setup() {
        super.setup();
        // matchedIds: null while no filter is active; otherwise the Set of
        // record ids the active filter matches. The list renderer reads it
        // through the environment to hide the other rows.
        this.shortcutState = useState({
            shortcuts: [],
            activeId: null,
            matchedIds: null,
            toolbarSelector: null,
        });
        useSubEnv({ x2manyShortcuts: this.shortcutState });
        if (this.props.viewMode !== "list") {
            return;
        }
        this._shortcutOrm = useService("orm");
        this._shortcutAction = useService("action");
        this._shortcutOriginalLimit = null;
        this._shortcutPending = null;
        this._shortcutRootRef = useRef("x2manyShortcutRoot");

        onMounted(() => {
            const toolbar = findShortcutToolbar(this._shortcutRootRef.el);
            if (toolbar) {
                if (!toolbar.id) {
                    toolbar.id = `o_x2many_shortcut_toolbar_${++toolbarCount}`;
                }
                this.shortcutState.toolbarSelector = `#${toolbar.id}`;
            }
        });

        onWillStart(async () => {
            this.shortcutState.shortcuts = await loadFormShortcuts(
                this._shortcutOrm,
                this.list.resModel
            );
            const defaultShortcut = this.x2manyShortcuts.find((s) => s.is_default);
            if (defaultShortcut) {
                await this._activateShortcut(defaultShortcut);
            }
        });

        // The parent record reloads after a save or an onchange and the list
        // then holds new row datapoints, so the matches are computed again.
        useEffect(
            () => {
                if (this.shortcutState.activeId !== null) {
                    this._refreshShortcutMatches();
                }
            },
            () => [this.list, this.list.records]
        );
    },

    /**
     * The shortcuts whose Show When expression is true for this list: the
     * form's record is the subject, the field is this x2many field.
     */
    get x2manyShortcuts() {
        const record = this.props.record;
        const context = showWhenContext({
            subject: record.resModel,
            subjectId: record.resId || false,
            field: this.props.name,
            view: "form",
        });
        return this.shortcutState.shortcuts.filter((shortcut) =>
            isShortcutShown(shortcut.shortcut_show_when, context)
        );
    },

    get hasX2ManyShortcuts() {
        return this.props.viewMode === "list" && this.x2manyShortcuts.length > 0;
    },

    async onX2ManyShortcutClick(shortcut) {
        if (shortcut.id === this.shortcutState.activeId) {
            return this._deactivateShortcut();
        }
        return this._activateShortcut(shortcut);
    },

    /**
     * The gear: set up the active shortcut in the wizard. On close the row
     * reads the shortcuts again (the page is not reloaded, so the form keeps
     * its unsaved edits) and keeps the same filter active if it still shows.
     */
    async onX2ManyShortcutSetup(shortcut) {
        return openShortcutSetup(this._shortcutAction, {
            filterId: shortcut.id,
            subjectModel: this.props.record.resModel,
            noReload: true,
            onClose: async () => {
                clearFormShortcutsCache();
                this.shortcutState.shortcuts = await loadFormShortcuts(
                    this._shortcutOrm,
                    this.list.resModel
                );
                const active = this.x2manyShortcuts.find(
                    (s) => s.id === this.shortcutState.activeId
                );
                if (active) {
                    this._shortcutPending = null;
                    await this._refreshShortcutMatches();
                } else {
                    await this._deactivateShortcut();
                }
            },
        });
    },

    async _activateShortcut(shortcut) {
        const list = this.list;
        if (this._shortcutOriginalLimit === null) {
            this._shortcutOriginalLimit = list.limit;
        }
        this.shortcutState.activeId = shortcut.id;
        if (list.count > list.limit || list.offset) {
            await list.load({ limit: Math.max(list.count, list.limit), offset: 0 });
        }
        await this._refreshShortcutMatches();
    },

    /**
     * Ask the server which of the loaded rows the active filter matches.
     * One request per filter and row set: a second call for the same filter
     * on the same rows (the effect after a load and the explicit call in
     * _activateShortcut) joins the pending request instead of sending
     * another. A click on another filter is a new pair, so it always asks.
     */
    _refreshShortcutMatches() {
        const shortcut = this.shortcutState.shortcuts.find(
            (s) => s.id === this.shortcutState.activeId
        );
        if (!shortcut) {
            return Promise.resolve();
        }
        const list = this.list;
        const records = list.records;
        const pending = this._shortcutPending;
        if (pending && pending.shortcutId === shortcut.id && pending.records === records) {
            return pending.promise;
        }
        const promise = (async () => {
            const ids = records.map((r) => r.resId).filter((id) => typeof id === "number");
            let matched = [];
            if (ids.length) {
                const domain = Domain.and([
                    [["id", "in", ids]],
                    new Domain(shortcut.domain),
                ]).toList(user.context);
                matched = await this._shortcutOrm.search(list.resModel, domain, {
                    context: list.context,
                });
            }
            // A click on another button or a switch-off while the request
            // ran: that later state wins.
            if (this.shortcutState.activeId === shortcut.id) {
                this.shortcutState.matchedIds = new Set(matched);
            }
        })();
        this._shortcutPending = { shortcutId: shortcut.id, records, promise };
        return promise;
    },

    async _deactivateShortcut() {
        this.shortcutState.activeId = null;
        this.shortcutState.matchedIds = null;
        this._shortcutPending = null;
        const list = this.list;
        if (this._shortcutOriginalLimit !== null && list.limit !== this._shortcutOriginalLimit) {
            await list.load({ limit: this._shortcutOriginalLimit, offset: 0 });
        }
    },
});
