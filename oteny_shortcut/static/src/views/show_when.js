/** @odoo-module **/

import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { user } from "@web/core/user";

// Why this exists:
// A shortcut button shows everywhere by default: the banner above every
// multi-record view of its model and the row above every list of its model
// inside a form. ir.filters.shortcut_show_when is a Python expression that
// narrows that (Thijs, 2026-09-14: the services filters under an employee
// differ from those under a log entry). It is evaluated here, in the browser,
// with Odoo's own expression engine, at the two places a button can appear
// (views/search_model_patch.js, views/x2many_field_patch.js).

/**
 * The names an expression can use, for one place.
 *
 * @param {Object} place
 * @param {string|false} [place.subject] model of the record the list belongs
 *   to inside a form; false on a top-level view
 * @param {number|false} [place.subjectId] id of that record; false for a new
 *   record or a top-level view
 * @param {string|false} [place.field] the x2many field name inside a form
 * @param {string|false} [place.view] "form" inside a form, else the view type
 */
export function showWhenContext({ subject = false, subjectId = false, field = false, view = false } = {}) {
    return {
        subject,
        subject_id: subjectId,
        field,
        view,
        uid: user.userId,
        context: user.context,
    };
}

/**
 * Whether a shortcut button shows at the given place. An empty expression
 * shows everywhere. An expression the browser cannot evaluate (a name it does
 * not know) hides the button and says why in the console: hiding is the safe
 * direction, because a shortcut's Default Filter follows this answer.
 *
 * @param {string|false} expression ir.filters.shortcut_show_when
 * @param {Object} context from showWhenContext()
 * @returns {boolean}
 */
export function isShortcutShown(expression, context) {
    if (!expression || !expression.trim()) {
        return true;
    }
    try {
        return evaluateBooleanExpr(expression, context);
    } catch (error) {
        console.warn(
            `oteny_shortcut: the Show When expression (${expression}) could not be evaluated; the shortcut stays hidden.`,
            error
        );
        return false;
    }
}
