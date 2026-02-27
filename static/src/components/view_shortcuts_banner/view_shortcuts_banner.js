/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";

export class ViewShortcutsBanner extends Component {
    static template = "oteny_shortcut.ViewShortcutsBanner";
    static props = {};

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
    }

    isActive(shortcut) {
        return this.state.activeIds.has(shortcut.id);
    }

    /**
     * Activate the favorite matching this shortcut in the SearchModel,
     * then switch view if the shortcut specifies a different view type.
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
