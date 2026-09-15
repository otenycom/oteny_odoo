/** @odoo-module **/

/**
 * The Font Awesome icons this backend has loaded, read once from the
 * stylesheets of the page.
 *
 * Odoo ships Font Awesome 4.7 in web.assets_backend and gives every icon one
 * rule of the shape ".fa-name::before { content: '\fxxx' }". That rule is the
 * only place where the set of icon names exists in the browser: there is no
 * list to import, so a chooser has to read the stylesheets. Odoo does the same
 * twice in its own code — the pictogram tab of the media dialog
 * (html_editor/utils/fonts.js) and the Studio icon picker (web_studio/utils.js,
 * enterprise only). This module repeats the idea in a few lines so that
 * oteny_shortcut keeps depending on "web" alone.
 */

// A rule defines an icon when its selector names the icon class "fa-name" and,
// at most, the base class "fa" beside it, in either order. Anchoring the match
// this way keeps the helper rules out (.fa-lg, .fa-spin, .fa-stack-1x, the
// bullets of .fa-ul) and keeps the icons of Odoo's fontawesome_overridden.scss
// in: that file writes ".fa.fa-tiktok::before" for an icon it adds and
// ".fa-twitter.fa::before" for one that already exists (dropped as a duplicate
// below, because the name is the same).
const ICON_SELECTOR = /^\.(?:fa\.)?(fa-[a-z0-9-]+)(?:\.fa)?::?before$/;

let cachedIcons = null;

/**
 * The icon names a CSS rule defines, or null when the rule defines no icon.
 * One rule can name several: Font Awesome groups an icon with the older
 * aliases it keeps (".fa-gears:before, .fa-cogs:before"), the aliases first
 * and the current name last.
 *
 * @param {CSSRule} rule
 * @returns {string[]|null}
 */
function iconNamesOf(rule) {
    // The rule that carries the glyph sets "content" and nothing else. Every
    // other rule mentioning an icon class sets something else (a font size, an
    // animation, a position), so this single test drops them all.
    if (!rule.selectorText || rule.style?.length !== 1 || rule.style[0] !== "content") {
        return null;
    }
    const names = [];
    for (const part of rule.selectorText.split(",")) {
        const match = part.trim().match(ICON_SELECTOR);
        if (!match) {
            return null;
        }
        names.push(match[1]);
    }
    return names.length ? names : null;
}

/**
 * Every icon the page can render, as SelectMenu choices, ordered by class name
 * so that an icon and its variants sit together (fa-cog, fa-cogs). Read once
 * and kept: the stylesheets of a page do not change.
 *
 * @returns {{value: string, label: string}[]} value is the bare class of the
 *      icon ("fa-cogs"), label is what a search matches on.
 */
export function getFontAwesomeIcons() {
    if (cachedIcons) {
        return cachedIcons;
    }
    const icons = [];
    const seen = new Set();
    for (const sheet of document.styleSheets) {
        let rules;
        try {
            rules = sheet.cssRules;
        } catch {
            // A stylesheet from another origin refuses to list its rules.
            continue;
        }
        for (const rule of rules || []) {
            const names = iconNamesOf(rule);
            if (!names) {
                continue;
            }
            // The last name is the current Font Awesome name; the ones before
            // it are the older aliases of the same icon ("fa-gears" is
            // "fa-cogs", "fa-remove" and "fa-close" are "fa-times").
            const className = names.at(-1);
            if (seen.has(className)) {
                continue;
            }
            seen.add(className);
            icons.push({
                value: className,
                // What the search box matches on: every name of the icon
                // without the "fa-" prefix and with the dashes as spaces, so
                // that a person who types "gears" finds fa-cogs and one who
                // types "clock" finds fa-clock-o.
                label: names.map((name) => name.slice(3).replace(/-/g, " ")).join(" "),
            });
        }
    }
    icons.sort((first, second) => first.value.localeCompare(second.value));
    cachedIcons = icons;
    return cachedIcons;
}

/**
 * Forget the icons read so far. For the tests, which add a stylesheet of their
 * own and need it read.
 */
export function clearFontAwesomeIconsCache() {
    cachedIcons = null;
}
