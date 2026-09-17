/** @odoo-module **/

import { Component, onWillStart } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

/**
 * The shortcut banner: the saved Favorites promoted to buttons, shown above
 * every multi-record view (list, kanban, calendar, pivot, graph, gantt and
 * custom views). It is rendered by Odoo's Layout component (see
 * views/layout_patch.xml), so no view has to opt in with a js_class any more
 * (Thijs, 2026-09-14). Form views and dialogs get no banner.
 *
 * The buttons come from the favorites the view's SearchModel already holds:
 * ir.filters.get_filters carries the shortcut fields and the SearchModel
 * patch (views/search_model_patch.js) keeps them on each favorite and marks
 * the ones whose Show When expression is true for this view (shortcutVisible).
 * A click is simply toggling that favorite, so the banner and the Favorites
 * menu always agree on what is active.
 *
 * The settings of a shortcut (button on or off, where it shows, icon) are
 * fields on the favorite's own form; a user edits the filter to change them
 * (Thijs, 2026-09-15). The banner itself carries no door to that form.
 *
 * A view that has a layout worth storing (list columns, calendar scale, the
 * timeline period) exposes it through env.shortcutLayout, an object with
 * getViewLayout() and applyViewLayout(layout), set with useSubEnv by its
 * controller (views/list_controller_patch.js, views/calendar_controller_patch.js,
 * rivercreds' timeline controller). Without it the Store Layout button stays
 * hidden and stored layouts are ignored.
 */
export class ViewShortcutsBanner extends Component {
    static template = "oteny_shortcut.ViewShortcutsBanner";
    static props = {};

    setup() {
        this.actionService = useService("action");
        // Tracks which shortcut's layout was last applied, so we only
        // re-apply when the active shortcut actually changes (not on
        // every SearchModel update like sort or pagination).
        this._lastAppliedLayoutId = null;

        if (this.isEnabled) {
            // Covers the initial page load where a favorite is already active
            // from the URL or a default filter.
            onWillStart(() => this._applyActiveShortcutLayout());
            // Re-derive active state whenever the SearchModel changes (user
            // toggles filters via the search bar, favorites dropdown, etc.).
            useBus(this.env.searchModel, "update", () => {
                this._applyActiveShortcutLayout();
                this.render();
            });
        }
    }

    /**
     * Only a multi-record view with a search model shows the banner. Form
     * views have a search model too (for the record pager), and dialogs
     * (Search More...) have their own; neither wants shortcut buttons.
     */
    get isEnabled() {
        const { searchModel, inDialog, config } = this.env;
        return Boolean(searchModel) && !inDialog && config?.viewType !== "form";
    }

    /**
     * The favorites promoted to shortcut buttons, in banner order. Each item
     * is an enriched SearchModel favorite: `id` is the search item id,
     * `serverSideId` the ir.filters id, `isActive` whether it is in the query.
     */
    get shortcuts() {
        if (!this.isEnabled) {
            return [];
        }
        return this.env.searchModel
            .getSearchItems((item) => item.type === "favorite" && item.shortcutVisible)
            .sort(
                (a, b) =>
                    a.shortcutSequence - b.shortcutSequence ||
                    a.description.localeCompare(b.description)
            );
    }

    /**
     * Return the single active shortcut, or null if none/multiple.
     */
    get activeShortcut() {
        const active = this.shortcuts.filter((shortcut) => shortcut.isActive);
        return active.length === 1 ? active[0] : null;
    }


    /**
     * True when exactly one shortcut is active and the view exposes a layout,
     * so the Store Layout button has an unambiguous target filter.
     */
    get canStoreLayout() {
        return Boolean(this.activeShortcut) && Boolean(this.env.shortcutLayout?.getViewLayout);
    }

    /**
     * If exactly one shortcut with a stored layout is now active, and it
     * differs from the last one we applied, push its layout to the view.
     */
    _applyActiveShortcutLayout() {
        const applyViewLayout = this.env.shortcutLayout?.applyViewLayout;
        if (!applyViewLayout) {
            return;
        }
        const shortcut = this.activeShortcut;
        const layoutId = shortcut?.shortcutLayout ? shortcut.serverSideId : null;
        if (layoutId === this._lastAppliedLayoutId) {
            return;
        }
        this._lastAppliedLayoutId = layoutId;

        if (shortcut?.shortcutLayout) {
            try {
                applyViewLayout(JSON.parse(shortcut.shortcutLayout));
            } catch {
                // Ignore invalid JSON
            }
        } else {
            // Active shortcut changed to one without layout, or no shortcut
            // is active -- clear any previously applied layout state.
            applyViewLayout(null);
        }
    }

    /**
     * Icon class for the shortcut's target view type, read from the same
     * server-provided per-view-type icon map Odoo's own view switcher uses
     * (session.view_info, populated from ir.ui.view._get_view_info). Returns
     * "" when the shortcut targets no view type or the type is unknown, so
     * the template can skip rendering the icon.
     */
    viewTypeIcon(shortcut) {
        const viewType = shortcut.shortcutViewType;
        return (viewType && session.view_info?.[viewType]?.icon) || "";
    }

    /**
     * Capture the current view layout and open the confirmation wizard.
     */
    async onStoreLayout() {
        const shortcut = this.activeShortcut;
        const getViewLayout = this.env.shortcutLayout?.getViewLayout;
        if (!shortcut || !getViewLayout) {
            return;
        }
        const layout = getViewLayout();
        if (!layout) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "shortcut.store.layout.wizard",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_filter_id: shortcut.serverSideId,
                default_layout_json: JSON.stringify(layout),
            },
        });
    }

    /**
     * Toggle the favorite behind this shortcut in the SearchModel (toggling a
     * favorite clears the other active facets), then switch view if the
     * shortcut specifies a different view type.
     *
     * Layout restoration follows automatically: toggleSearchItem() fires the
     * SearchModel "update" event that _applyActiveShortcutLayout() listens to.
     */
    async onShortcutClick(shortcut) {
        this.env.searchModel.toggleSearchItem(shortcut.id);

        const targetView = shortcut.shortcutViewType;
        if (
            targetView &&
            targetView !== this.env.config.viewType &&
            this._actionHasView(targetView)
        ) {
            this.actionService.switchView(targetView);
        }
    }

    /**
     * Whether the current action can switch to the given view type. A shortcut's
     * preferred view type may point at a view the current action does not expose
     * — e.g. a favorite saved on a model whose action lacks that view — in which
     * case switchView() would throw ViewNotFoundError. viewSwitcherEntries lists
     * the (multi-record) views this action actually offers, so we only switch
     * when the target is among them; otherwise we just apply the filter in place.
     */
    _actionHasView(viewType) {
        const entries = this.env.config.viewSwitcherEntries || [];
        return entries.some((v) => v.type === viewType);
    }
}
