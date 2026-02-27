/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ShortcutListController } from "./shortcut_list_controller";

export const shortcutListView = {
    ...listView,
    Controller: ShortcutListController,
};

registry.category("views").add("shortcut_list", shortcutListView);
