/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class ViewShortcutsBanner extends Component {
    static template = "oteny_shortcut.ViewShortcutsBanner";
    static props = {
        getViewLayout: { type: Function, optional: true },
        applyViewLayout: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            loaded: false,
            shortcuts: [],
            activeIds: new Set(),
        });
        // Maps ir.filters record id -> searchModel searchItem id
        this._serverIdToSearchItemId = {};
        // Tracks which shortcut's layout was last applied, so we only
        // re-apply when the active shortcut actually changes (not on
        // every SearchModel update like sort or pagination).
        this._lastAppliedLayoutId = null;

        onWillStart(async () => {
            const resModel = this.env.searchModel.resModel;
            const actionId = this.env.config.actionId || null;
            const shortcuts = await this.orm.call(
                "ir.filters",
                "get_shortcuts",
                [resModel, actionId]
            );
            Object.assign(this.state, { loaded: true, shortcuts });
            this._buildServerIdMap();
            this._syncActiveState();
        });

        // Re-derive active state whenever the SearchModel changes
        // (user toggles filters via the search bar, favorites dropdown, etc.)
        useBus(this.env.searchModel, "update", () => this._syncActiveState());
    }

    /**
     * Build a lookup from ir.filters server-side id to the SearchModel's
     * internal searchItem id, so we can quickly check active state.
     */
    _buildServerIdMap() {
        this._serverIdToSearchItemId = {};
        const searchItems = this.env.searchModel.searchItems;
        for (const [id, item] of Object.entries(searchItems)) {
            if (item.type === "favorite" && item.serverSideId) {
                this._serverIdToSearchItemId[item.serverSideId] = Number(id);
            }
        }
    }

    /**
     * Check the SearchModel query to determine which shortcuts correspond
     * to an active favorite, and update the highlighted button state.
     * Also auto-applies stored layout when the active shortcut changes
     * (including on initial page load).
     */
    _syncActiveState() {
        const activeSearchItemIds = new Set(
            this.env.searchModel.query.map((q) => q.searchItemId)
        );
        const activeIds = new Set();
        for (const shortcut of this.state.shortcuts) {
            const searchItemId = this._serverIdToSearchItemId[shortcut.id];
            if (searchItemId !== undefined && activeSearchItemIds.has(searchItemId)) {
                activeIds.add(shortcut.id);
            }
        }
        this.state.activeIds = activeIds;

        this._applyActiveShortcutLayout();
    }

    /**
     * If exactly one shortcut with a stored layout is now active, and it
     * differs from the last one we applied, push its layout to the
     * controller. This covers both explicit clicks AND the initial page
     * load where a favorite is already active from the URL/default.
     */
    _applyActiveShortcutLayout() {
        if (!this.props.applyViewLayout) {
            return;
        }

        const shortcut = this._getActiveShortcut();
        const layoutId = shortcut?.shortcut_layout ? shortcut.id : null;

        if (layoutId === this._lastAppliedLayoutId) {
            return;
        }
        this._lastAppliedLayoutId = layoutId;

        if (shortcut?.shortcut_layout) {
            try {
                const layout = JSON.parse(shortcut.shortcut_layout);
                this.props.applyViewLayout(layout);
            } catch {
                // Ignore invalid JSON
            }
        } else {
            // Active shortcut changed to one without layout, or no shortcut
            // is active -- clear any previously applied layout state.
            this.props.applyViewLayout(null);
        }
    }

    isActive(shortcut) {
        return this.state.activeIds.has(shortcut.id);
    }

    /**
     * Icon class for the shortcut's target view type, read from the same
     * server-provided per-view-type icon map Odoo's own view switcher uses
     * (session.view_info, populated from ir.ui.view._get_view_info). This
     * covers list and calendar as well as any custom view type (e.g. the
     * credential planning timeline) without a hardcoded mapping here.
     * Returns "" when the shortcut targets no view type or the type is
     * unknown, so the template can skip rendering the icon.
     */
    viewTypeIcon(shortcut) {
        const viewType = shortcut.shortcut_view_type;
        return (viewType && session.view_info?.[viewType]?.icon) || "";
    }

    /**
     * True when exactly one shortcut is active, so the Store Layout button
     * has an unambiguous target filter.
     */
    get canStoreLayout() {
        return this.state.activeIds.size === 1 && !!this.props.getViewLayout;
    }

    /**
     * Return the single active shortcut, or null if none/multiple.
     */
    _getActiveShortcut() {
        if (this.state.activeIds.size !== 1) {
            return null;
        }
        const activeId = [...this.state.activeIds][0];
        return this.state.shortcuts.find((s) => s.id === activeId) || null;
    }

    /**
     * Capture the current view layout and open the confirmation wizard.
     */
    async onStoreLayout() {
        const shortcut = this._getActiveShortcut();
        if (!shortcut || !this.props.getViewLayout) {
            return;
        }
        const layout = this.props.getViewLayout();
        if (!layout) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "shortcut.store.layout.wizard",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_filter_id: shortcut.id,
                default_layout_json: JSON.stringify(layout),
            },
        });
    }

    /**
     * Activate the favorite matching this shortcut in the SearchModel,
     * then switch view if the shortcut specifies a different view type.
     *
     * Layout restoration is handled automatically by _syncActiveState()
     * which fires on the SearchModel "update" event triggered by
     * toggleSearchItem().
     */
    async onShortcutClick(shortcut) {
        const searchItemId = this._serverIdToSearchItemId[shortcut.id];
        if (searchItemId !== undefined) {
            this.env.searchModel.toggleSearchItem(searchItemId);
        }

        if (
            shortcut.shortcut_view_type &&
            shortcut.shortcut_view_type !== this.env.config.viewType
        ) {
            this.actionService.switchView(shortcut.shortcut_view_type);
        }
    }
}
