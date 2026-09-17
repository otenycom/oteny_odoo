import { afterEach, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame, runAllTimers } from "@odoo/hoot-mock";
import {
    clickSave,
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";

import {
    clearFontAwesomeIconsCache,
    getFontAwesomeIcons,
} from "@oteny_shortcut/fields/fa_icon/fa_icons";

// The icon chooser (fields/fa_icon): a Char field that holds a Font Awesome
// class gets a searchable list of every icon the page can render, instead of
// the person having to type the class by hand. The list is read from the
// stylesheets of the page, which is why every test below adds a stylesheet of
// its own. The names in it cannot collide with the real Font Awesome ones, so
// the assertions hold whether or not the test page loads Font Awesome itself.

class Filter extends models.Model {
    _name = "filter";
    icon = fields.Char();
    _records = [
        { id: 1, icon: "fa-zztest-alpha" },
        // A class no stylesheet defines, as a filter saved before the chooser
        // existed can hold: the field was free text and a typo was possible.
        { id: 2, icon: "fa-typed-wrong" },
    ];
}

defineModels([Filter]);

// The module's Form Wide Toggle reads a system parameter on every form open;
// the mock server has no ir.config_parameter model, so answer it here.
onRpc("ir.config_parameter", "get_param", () => "False");

const addedStyles = [];

/** Add a stylesheet of icon rules and have the chooser read the page again. */
function defineIcons(css) {
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
    addedStyles.push(style);
    clearFontAwesomeIconsCache();
}

afterEach(() => {
    while (addedStyles.length) {
        addedStyles.pop().remove();
    }
    clearFontAwesomeIconsCache();
});

const TEST_ICONS = `
    .fa-zztest-alpha:before { content: "\\f000"; }
    .fa-zztest-old:before, .fa-zztest-new:before { content: "\\f001"; }
    .fa.fa-zztest-added:before { content: "\\f002"; }
    .fa-zztest-alpha.fa:before { content: "\\f000"; }
    .fa-zztest-alpha.fa-lg { font-size: 1.33em; }
    .fa-zztest-nocontent:before { font-weight: bold; }
`;

const FORM = `<form><field name="icon" widget="fa_icon"/></form>`;

test("the icon list holds one entry per icon, named by its current class", async () => {
    defineIcons(TEST_ICONS);

    const icons = getFontAwesomeIcons().filter((icon) => icon.value.startsWith("fa-zztest-"));
    expect(icons).toEqual([
        // A compound selector is how Odoo's fontawesome_overridden.scss adds
        // an icon of its own, so it counts as an icon.
        { value: "fa-zztest-added", label: "zztest added" },
        // Read once, although two rules define it.
        { value: "fa-zztest-alpha", label: "zztest alpha" },
        // The older aliases of an icon come first in its rule and the current
        // name last; a search matches on all of them.
        { value: "fa-zztest-new", label: "zztest old zztest new" },
    ]);
    // A rule that sets no glyph defines no icon, so the helper classes of Font
    // Awesome (.fa-lg, .fa-spin) never reach the list.
    expect(icons.map((icon) => icon.value)).not.toInclude("fa-zztest-nocontent");
});

test("the chooser shows the icon of the record, searches, and writes the class picked", async () => {
    defineIcons(TEST_ICONS);
    onRpc("filter", "web_save", ({ args }) => expect.step(args[1].icon));

    await mountView({ type: "form", resModel: "filter", resId: 1, arch: FORM });
    expect(".o_field_widget[name='icon'] .o_select_menu_toggler").toHaveText("fa-zztest-alpha");
    expect(".o_field_widget[name='icon'] .o_select_menu_toggler i.fa-zztest-alpha").toHaveCount(1);

    await click(".o_select_menu_toggler");
    await animationFrame();
    await contains(".o_fa_icon_field_menu .o_select_menu_input").edit("zztest", {
        confirm: false,
    });
    await runAllTimers();
    await animationFrame();
    expect(".o_fa_icon_field_menu i[title^='fa-zztest-']").toHaveCount(3);

    // The search matches an older alias of the icon as well as its current name.
    await contains(".o_fa_icon_field_menu .o_select_menu_input").edit("zztest old", {
        confirm: false,
    });
    await runAllTimers();
    await animationFrame();
    expect(".o_fa_icon_field_menu i[title^='fa-zztest-']").toHaveCount(1);

    await click(".o_fa_icon_field_menu i[title='fa-zztest-new']");
    await animationFrame();
    expect(".o_field_widget[name='icon'] .o_select_menu_toggler").toHaveText("fa-zztest-new");

    await clickSave();
    // The bare class is stored, without the "fa" base class: that is what the
    // shortcut templates render and what the older records hold.
    expect.verifySteps(["fa-zztest-new"]);
});

test("a readonly field shows the icon and its class, and no chooser", async () => {
    defineIcons(TEST_ICONS);

    await mountView({
        type: "form",
        resModel: "filter",
        resId: 1,
        arch: `<form><field name="icon" widget="fa_icon" readonly="1"/></form>`,
    });
    expect(".o_field_widget[name='icon'] i.fa-zztest-alpha").toHaveCount(1);
    expect(".o_field_widget[name='icon']").toHaveText("fa-zztest-alpha");
    expect(".o_select_menu").toHaveCount(0);
});

test("a class the page cannot render stays visible and can be cleared", async () => {
    defineIcons(TEST_ICONS);
    onRpc("filter", "web_save", ({ args }) => expect.step(args[1].icon));

    await mountView({ type: "form", resModel: "filter", resId: 2, arch: FORM });
    expect(".o_field_widget[name='icon'] .o_select_menu_toggler").toHaveText("fa-typed-wrong");

    // It is offered as a choice of its own, shown as its class because there
    // is no glyph to show, so the chooser can deselect it.
    await click(".o_select_menu_toggler");
    await animationFrame();
    expect(".o_fa_icon_field_menu .o_select_menu_item:contains('fa-typed-wrong')").toHaveCount(1);

    await click(".o_select_menu_toggler_clear");
    await animationFrame();
    expect(".o_field_widget[name='icon'] .o_select_menu_toggler").toHaveText("Choose an icon");

    await clickSave();
    expect.verifySteps([false]);
});
