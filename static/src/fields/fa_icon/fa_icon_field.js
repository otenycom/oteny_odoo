/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { SelectMenu } from "@web/core/select_menu/select_menu";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { getFontAwesomeIcons } from "./fa_icons";

/**
 * A searchable chooser for a Char field that holds a Font Awesome icon class,
 * used with widget="fa_icon".
 *
 * Why it exists: the Shortcut Icon of a saved Favorite was a free text field,
 * so setting it meant knowing the Font Awesome names by heart and spelling
 * them right. A typo shows no icon and says nothing about why. The chooser
 * offers every icon the backend has loaded and searches them by name, so
 * nobody has to look a name up outside Odoo.
 *
 * The stored value stays the bare class without the "fa" base class, for
 * example "fa-clock-o". That is what the existing records hold and what the
 * shortcut templates already render ("fa #{shortcut_icon}").
 */
export class FaIconField extends Component {
    static template = "oteny_shortcut.FaIconField";
    static components = { SelectMenu };
    static props = { ...standardFieldProps };

    setup() {
        this.icons = getFontAwesomeIcons();
        this.knownClasses = new Set(this.icons.map((icon) => icon.value));
    }

    /**
     * The icon class the record holds. A value written before this widget
     * existed can carry the base class as well ("fa fa-check"), which renders
     * the same; the class that names the icon is the "fa-" one, so read that
     * one and ignore the rest.
     */
    get iconClass() {
        const value = this.props.record.data[this.props.name] || "";
        return value.split(/\s+/).find((cls) => cls.startsWith("fa-")) || "";
    }

    /**
     * The icons to choose from. A value the loaded stylesheets do not know (an
     * old typo, or a class of a font this database does not load) is put in
     * front of them, so that the chooser still shows what the record holds and
     * the person can clear it, instead of the field looking empty.
     */
    get choices() {
        const current = this.iconClass;
        if (current && !this.knownClasses.has(current)) {
            return [{ value: current, label: current }, ...this.icons];
        }
        return this.icons;
    }

    isKnown(iconClass) {
        return this.knownClasses.has(iconClass);
    }

    onSelect(value) {
        this.props.record.update({ [this.props.name]: value || false });
    }
}

export const faIconField = {
    component: FaIconField,
    displayName: _t("Font Awesome Icon"),
    supportedTypes: ["char"],
};

registry.category("fields").add("fa_icon", faIconField);
