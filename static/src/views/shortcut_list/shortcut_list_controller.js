/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { ViewShortcutsBanner } from "@oteny_shortcut/components/view_shortcuts_banner/view_shortcuts_banner";

export class ShortcutListController extends ListController {
    static template = "oteny_shortcut.ShortcutListView";
    static components = {
        ...ListController.components,
        ViewShortcutsBanner,
    };
}
