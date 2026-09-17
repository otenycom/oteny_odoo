/** @odoo-module **/

import { Layout } from "@web/search/layout";
import { ViewShortcutsBanner } from "@oteny_shortcut/components/view_shortcuts_banner/view_shortcuts_banner";

// Why this exists:
// Every view with a control panel renders Odoo's Layout component, so adding
// the shortcut banner here (template: layout_patch.xml) puts it on list,
// kanban, calendar, pivot, graph, gantt and custom views alike, without a
// js_class per view (Thijs, 2026-09-14). The banner itself decides whether it
// has anything to show: it stays empty on form views, in dialogs, and when
// the model has no shortcut favorites.
Layout.components = { ...(Layout.components || {}), ViewShortcutsBanner };
