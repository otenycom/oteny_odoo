import { expect, test } from "@odoo/hoot";
import { click, queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    serverState,
    toggleSearchBarMenu,
    webModels,
} from "@web/../tests/web_test_helpers";

// The shortcut banner (components/view_shortcuts_banner): rendered by Odoo's
// Layout on every multi-record view, it reads its buttons from the favorites
// the view loads (the shortcut fields ride on each favorite), shows the ones
// whose Show When expression is true for this view, and a click toggles that
// favorite. A shortcut's Default Filter applies only where its button shows.
// Form views get no banner.

class Line extends models.Model {
    _name = "line";
    name = fields.Char();
    done = fields.Boolean();
    _records = [
        { id: 1, name: "Open A", done: false },
        { id: 2, name: "Done B", done: true },
        { id: 3, name: "Open C", done: false },
    ];
}

// A list view asks res.users for the export group, so the base web models
// are defined next to the test model.
const { ResCompany, ResPartner, ResUsers } = webModels;
defineModels([Line, ResCompany, ResPartner, ResUsers]);

// The module's Form Wide Toggle reads a system parameter on every form open;
// the mock server has no ir.config_parameter model, so answer it here.
onRpc("ir.config_parameter", "get_param", () => "False");

function irFilter(id, name, domain, values) {
    return {
        id,
        name,
        domain,
        context: "{}",
        sort: "[]",
        user_ids: [],
        is_default: false,
        shortcut_sequence: 0,
        shortcut_view_type: false,
        shortcut_icon: false,
        shortcut_layout: false,
        shortcut_show_when: "",
        ...values,
    };
}

const IR_FILTERS = [
    irFilter(1, "Todo", '[("done", "=", False)]', { shortcut_sequence: 20 }),
    irFilter(2, "Done", '[("done", "=", True)]', {
        shortcut_sequence: 10,
        shortcut_show_when: "not subject",
        shortcut_icon: "fa-check",
    }),
    irFilter(3, "Plain favorite", "[]"),
    // Buttons only inside a form, or only on a kanban: not on this list.
    irFilter(4, "In forms only", "[]", { shortcut_sequence: 5, shortcut_show_when: "view == 'form'" }),
    irFilter(5, "Kanban only", "[]", { shortcut_sequence: 1, shortcut_show_when: "view == 'kanban'" }),
    // A default shortcut for the lists inside a form: it stays a favorite of
    // this list, but neither shows a button nor applies its default here. It
    // is the user's own favorite, so the menu lists it without "More...".
    irFilter(6, "Form default", '[("done", "=", True)]', {
        shortcut_sequence: 6,
        is_default: true,
        shortcut_show_when: "subject == 'x'",
        user_ids: [serverState.userId],
    }),
];

test("the banner lists the shortcut favorites in sequence order and a click toggles the favorite", async () => {
    await mountView({
        type: "list",
        resModel: "line",
        arch: `<list><field name="name"/></list>`,
        irFilters: IR_FILTERS,
    });

    // Sequence order; a plain favorite and the filters whose expression is
    // false here are not buttons.
    expect(queryAllTexts(".view-shortcuts-banner button")).toEqual(["Done", "Todo"]);
    expect(".view-shortcuts-banner button .fa-check").toHaveCount(1);
    // "Form default" did not narrow the list at open, and stays in the menu.
    expect(".o_data_row").toHaveCount(3);
    expect(".o_searchview .o_facet_values").toHaveCount(0);
    await toggleSearchBarMenu();
    expect(".o_favorite_menu .o_menu_item:contains(Form default)").toHaveCount(1);
    await toggleSearchBarMenu();

    await click(".view-shortcuts-banner button:contains(Todo)");
    await animationFrame();
    expect(".view-shortcuts-banner button.btn-primary").toHaveText("Todo");
    expect(".o_searchview .o_facet_values").toHaveText("Todo");
    expect(queryAllTexts(".o_data_row .o_data_cell[name='name']")).toEqual(["Open A", "Open C"]);

    // Toggling a favorite clears the other facets: one active button at a time.
    await click(".view-shortcuts-banner button:contains(Done)");
    await animationFrame();
    expect(".view-shortcuts-banner button.btn-primary").toHaveText("Done");
    expect(queryAllTexts(".o_data_row .o_data_cell[name='name']")).toEqual(["Done B"]);

    await click(".view-shortcuts-banner button:contains(Done)");
    await animationFrame();
    expect(".view-shortcuts-banner button.btn-primary").toHaveCount(0);
    expect(".o_data_row").toHaveCount(3);
});

test("a form view shows no banner", async () => {
    await mountView({
        type: "form",
        resModel: "line",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
        irFilters: IR_FILTERS,
    });
    expect(".view-shortcuts-banner").toHaveCount(0);
});

test("a model without shortcut favorites shows no banner", async () => {
    await mountView({
        type: "list",
        resModel: "line",
        arch: `<list><field name="name"/></list>`,
        irFilters: [irFilter(3, "Plain favorite", "[]")],
    });
    expect(".view-shortcuts-banner").toHaveCount(0);
});
