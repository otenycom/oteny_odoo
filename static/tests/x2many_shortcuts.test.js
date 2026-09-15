import { expect, test } from "@odoo/hoot";
import { click, queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { defineModels, fields, models, mountView, onRpc } from "@web/../tests/web_test_helpers";

import { clearFormShortcutsCache } from "@oteny_shortcut/views/x2many_field_patch";

// The in-form shortcut row (views/x2many_field_patch.js): the shortcuts of
// the list's model whose Show When expression is true for this form (the
// form's record is the subject) show as buttons above an x2many list, the
// Default Filter is active at open, a click narrows the rows to the filter's
// domain by hiding the others, and clicking the active button again shows
// every row. The record itself never changes.

class Parent extends models.Model {
    _name = "parent";
    name = fields.Char();
    line_ids = fields.One2many({ relation: "line", relation_field: "parent_id" });
    _records = [{ id: 1, name: "Parent", line_ids: [1, 2, 3] }];
}

class Line extends models.Model {
    _name = "line";
    name = fields.Char();
    done = fields.Boolean();
    parent_id = fields.Many2one({ relation: "parent" });
    _records = [
        { id: 1, name: "Open A", done: false, parent_id: 1 },
        { id: 2, name: "Done B", done: true, parent_id: 1 },
        { id: 3, name: "Open C", done: false, parent_id: 1 },
    ];
}

defineModels([Parent, Line]);

// The module's Form Wide Toggle reads a system parameter on every form open;
// the mock server has no ir.config_parameter model, so answer it here.
onRpc("ir.config_parameter", "get_param", () => "False");

function shortcut(id, name, domain, values) {
    return {
        id,
        name,
        domain,
        is_default: false,
        shortcut_sequence: 10,
        shortcut_view_type: false,
        shortcut_icon: false,
        shortcut_layout: false,
        shortcut_show_when: "",
        ...values,
    };
}

const FORM_SHORTCUTS = [
    // Limited to this form's subject, and the default there.
    shortcut(7, "Todo", '[("done", "=", False)]', {
        is_default: true,
        shortcut_sequence: 10,
        shortcut_show_when: "subject == 'parent' and view == 'form' and field == 'line_ids'",
    }),
    // No expression: everywhere.
    shortcut(8, "Done", '[("done", "=", True)]', {
        shortcut_sequence: 20,
        shortcut_icon: "fa-check",
    }),
    // Another subject: no button here.
    shortcut(9, "Elsewhere", "[]", { shortcut_sequence: 30, shortcut_show_when: "subject == 'other'" }),
    // A name the browser does not know: hidden, with a console warning.
    shortcut(10, "Broken", "[]", { shortcut_sequence: 40, shortcut_show_when: "no_such_name == 1" }),
];

const ARCH = `
    <form>
        <field name="line_ids">
            <list><field name="name"/><field name="done"/></list>
        </field>
    </form>`;

function visibleRowNames() {
    return queryAllTexts(".o_data_row:not(.d-none) .o_data_cell[name='name']");
}

test("the default Forms shortcut is active at open and hides the rows it does not match", async () => {
    clearFormShortcutsCache();
    onRpc("ir.filters", "get_shortcuts", ({ args }) => {
        expect(args).toEqual(["line"]);
        expect.step("get_shortcuts");
        return FORM_SHORTCUTS;
    });
    onRpc("line", "search", ({ args }) => {
        // The row asks the server which of the list's ids match the domain,
        // evaluated in the browser first; the mock ORM answers below.
        expect.step(`search ${JSON.stringify(args[0])}`);
    });
    await mountView({ type: "form", resModel: "parent", resId: 1, arch: ARCH });

    expect(queryAllTexts(".o_x2many_shortcuts button:not(.o_shortcut_setup)")).toEqual(["Todo", "Done"]);
    expect(".o_x2many_shortcuts button.btn-primary").toHaveText("Todo");
    expect(".o_x2many_shortcuts button .fa-check").toHaveCount(1);
    expect(visibleRowNames()).toEqual(["Open A", "Open C"]);
    expect(".o_data_row.o_x2many_shortcut_hidden").toHaveCount(1);
    // Domain.and writes the combined domain in prefix notation.
    expect.verifySteps(["get_shortcuts", 'search ["&",["id","in",[1,2,3]],["done","=",false]]']);
});

test("clicking another shortcut switches, clicking the active one shows all, the record stays clean", async () => {
    clearFormShortcutsCache();
    onRpc("ir.filters", "get_shortcuts", () => FORM_SHORTCUTS);
    await mountView({ type: "form", resModel: "parent", resId: 1, arch: ARCH });

    await click(".o_x2many_shortcuts button:contains(Done)");
    await animationFrame();
    expect(".o_x2many_shortcuts button.btn-primary").toHaveText("Done");
    expect(visibleRowNames()).toEqual(["Done B"]);

    await click(".o_x2many_shortcuts button:contains(Done)");
    await animationFrame();
    expect(".o_x2many_shortcuts button.btn-primary").toHaveCount(0);
    expect(visibleRowNames()).toEqual(["Open A", "Done B", "Open C"]);
    // A filter click is a view preference, not an edit: no save / discard buttons.
    expect(".o_form_status_indicator_buttons.invisible").toHaveCount(1);
});

test("a list with more rows than its page size loads every row while a filter is active", async () => {
    clearFormShortcutsCache();
    onRpc("ir.filters", "get_shortcuts", () => FORM_SHORTCUTS);
    await mountView({
        type: "form",
        resModel: "parent",
        resId: 1,
        arch: `
            <form>
                <field name="line_ids">
                    <list limit="2"><field name="name"/><field name="done"/></list>
                </field>
            </form>`,
    });

    // Default filter active: the third row would be on page two, so the
    // page size was raised to the row count and the pager is gone.
    expect(visibleRowNames()).toEqual(["Open A", "Open C"]);
    expect(".o_field_x2many .o_pager").toHaveCount(0);

    // Switched off: back to the page size of the view, with its pager.
    await click(".o_x2many_shortcuts button:contains(Todo)");
    await animationFrame();
    expect(visibleRowNames()).toEqual(["Open A", "Done B"]);
    expect(".o_field_x2many .o_pager").toHaveCount(1);
});

test("a model without Forms shortcuts gets no row", async () => {
    clearFormShortcutsCache();
    onRpc("ir.filters", "get_shortcuts", () => []);
    await mountView({ type: "form", resModel: "parent", resId: 1, arch: ARCH });
    expect(".o_x2many_shortcuts").toHaveCount(0);
    expect(".o_data_row").toHaveCount(3);
});
