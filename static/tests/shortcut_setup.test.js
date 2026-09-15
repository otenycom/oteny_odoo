import { expect, test } from "@odoo/hoot";
import { click, queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    mockService,
    models,
    mountView,
    onRpc,
    toggleMenuItem,
    toggleSearchBarMenu,
    webModels,
} from "@web/../tests/web_test_helpers";

import { clearFormShortcutsCache } from "@oteny_shortcut/views/x2many_field_patch";

// The door to the Set Up Shortcut wizard (Python): a gear that appears when
// a filter is selected. In the banner of a multi-record view it works on the
// single active favorite, shortcut or not; in the row above an in-form list,
// on the active button. Also: the in-form row moves into the toolbar of
// buttons directly above the list, at its right end.

class Parent extends models.Model {
    _name = "parent";
    name = fields.Char();
    line_ids = fields.One2many({ relation: "line", relation_field: "parent_id" });
    _records = [{ id: 1, name: "Parent", line_ids: [1, 2] }];
    do_it() {}
}

class Line extends models.Model {
    _name = "line";
    name = fields.Char();
    done = fields.Boolean();
    parent_id = fields.Many2one({ relation: "parent" });
    _records = [
        { id: 1, name: "Open A", done: false, parent_id: 1 },
        { id: 2, name: "Done B", done: true, parent_id: 1 },
    ];
}

const { ResCompany, ResPartner, ResUsers } = webModels;
defineModels([Parent, Line, ResCompany, ResPartner, ResUsers]);

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

function mockWizardDoor() {
    const calls = [];
    mockService("action", {
        doAction(action, options) {
            calls.push({ action, options });
            expect.step(`doAction ${action.res_model} filter ${action.context.default_filter_id}`);
        },
    });
    return calls;
}

test("the banner gear appears when one favorite is active, shortcut or not", async () => {
    mockWizardDoor();
    await mountView({
        type: "list",
        resModel: "line",
        arch: `<list><field name="name"/></list>`,
        irFilters: [
            irFilter(3, "Plain favorite", '[("done", "=", False)]'),
            irFilter(4, "Todo", '[("done", "=", False)]', { shortcut_sequence: 10 }),
        ],
    });
    // Nothing active: buttons, no gear.
    expect(".view-shortcuts-banner .o_shortcut_setup").toHaveCount(0);

    // A plain favorite activated from the Favorites menu: the gear is its
    // door to become a button.
    await toggleSearchBarMenu();
    await toggleMenuItem("Plain favorite");
    await animationFrame();
    expect(".view-shortcuts-banner .o_shortcut_setup").toHaveCount(1);
    await click(".view-shortcuts-banner .o_shortcut_setup");
    await animationFrame();
    expect.verifySteps(["doAction shortcut.setup.wizard filter 3"]);
});

test("a model without shortcut buttons still gets the gear once a favorite is active", async () => {
    mockWizardDoor();
    await mountView({
        type: "list",
        resModel: "line",
        arch: `<list><field name="name"/></list>`,
        irFilters: [irFilter(3, "Plain favorite", '[("done", "=", False)]')],
    });
    expect(".view-shortcuts-banner").toHaveCount(0);
    await toggleSearchBarMenu();
    await toggleMenuItem("Plain favorite");
    await animationFrame();
    expect(".view-shortcuts-banner button").toHaveCount(1);
    expect(".view-shortcuts-banner .o_shortcut_setup").toHaveCount(1);
});

test("in a form the row moves into the toolbar above the list and its gear opens the wizard for this form", async () => {
    clearFormShortcutsCache();
    const calls = mockWizardDoor();
    onRpc("ir.filters", "get_shortcuts", () => {
        expect.step("get_shortcuts");
        return [
            {
                id: 7,
                name: "Todo",
                domain: '[("done", "=", False)]',
                is_default: true,
                shortcut_sequence: 10,
                shortcut_view_type: false,
                shortcut_icon: false,
                shortcut_layout: false,
                shortcut_show_when: "",
            },
        ];
    });
    await mountView({
        type: "form",
        resModel: "parent",
        resId: 1,
        arch: `
            <form>
                <div class="d-flex align-items-center gap-2 mb-3">
                    <button name="do_it" type="object" string="Add" class="btn btn-primary"/>
                </div>
                <field name="line_ids">
                    <list><field name="name"/><field name="done"/></list>
                </field>
            </form>`,
    });
    // The row sits in the toolbar, at its right end, and still filters.
    expect("div.d-flex > .o_x2many_shortcuts").toHaveCount(1);
    expect("div.d-flex > .o_x2many_shortcuts").toHaveClass(["order-last", "ms-auto"]);
    expect(".o_field_x2many .o_x2many_shortcuts").toHaveCount(0);
    expect(queryAllTexts(".o_data_row:not(.d-none) .o_data_cell[name='name']")).toEqual(["Open A"]);

    await click(".o_x2many_shortcuts .o_shortcut_setup");
    await animationFrame();
    expect.verifySteps(["get_shortcuts", "doAction shortcut.setup.wizard filter 7"]);
    const { action, options } = calls[0];
    expect(action.context.shortcut_subject_model).toBe("parent");
    expect(action.context.shortcut_wizard_no_reload).toBe(true);

    // Closing the wizard reads the shortcuts again, without a page reload.
    await options.onClose();
    await animationFrame();
    expect.verifySteps(["get_shortcuts"]);
    expect(".o_x2many_shortcuts button.btn-primary").toHaveText("Todo");
});
