import re

from odoo import _, api, fields, models

# The choices a user gets for "Where" instead of writing the Show When
# expression by hand (Thijs, 2026-09-15: the expression is too technical for
# most users). Abstract words for the two places (views / forms, screens /
# tabs, record / record type) all failed with users, so the labels are built
# from the names of the things themselves: "Only on the Services list" and
# "Only inside an Employee, Ship, Log Entry or Service", from the favorite's
# model and the models that hold a list of it (_show_preset_selection). The
# keys are fixed; each stands for one expression. "custom" keeps whatever the
# filter holds and is the only one that shows the expression itself.
SHOW_PRESET_KEYS = ["everywhere", "views", "forms", "subject", "custom"]

# Fallback labels, used when the wizard is not opened for a favorite (no
# default_filter_id in the context, e.g. from code).
SHOW_PRESETS = [
    ("everywhere", "Everywhere"),
    ("views", "Only on the list of all of them"),
    ("forms", "Only inside the things that have them"),
    ("subject", "Only inside one of them"),
    ("custom", "Custom rule (administrators)"),
]

# How many names the "inside" label spells out before "...".
SUBJECT_NAMES_IN_LABEL = 5

PRESET_EXPRESSIONS = {
    "everywhere": "",
    "views": "not subject",
    "forms": "view == 'form'",
}

# `subject == 'hr.employee'`, with either quote style and any spacing.
SUBJECT_EXPRESSION = re.compile(r"^subject\s*==\s*['\"]([\w.]+)['\"]$")


def expression_for_preset(preset, subject_model=None):
    """The Show When expression a preset stands for."""
    if preset == "subject":
        return f"subject == '{subject_model}'" if subject_model else ""
    return PRESET_EXPRESSIONS.get(preset, "")


def plural(name):
    """A plain English plural for a model name: Service -> Services,
    Log Entry -> Log Entries, Address -> Addresses. Odoo stores no plural.
    """
    if not name:
        return name
    lower = name.lower()
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return name + "es"
    if lower.endswith("y") and not lower.endswith(("ay", "ey", "oy", "uy")):
        return name[:-1] + "ies"
    return name + "s"


def with_article(name):
    """"an Employee", "a Ship"."""
    return ("an " if name[:1].lower() in "aeiou" else "a ") + name


def preset_for_expression(expression):
    """(preset, subject model) for a stored expression: the reverse mapping,
    so the wizard opens on the choice the filter already holds. Anything the
    presets do not cover is "custom".
    """
    expression = (expression or "").strip()
    for preset, preset_expression in PRESET_EXPRESSIONS.items():
        if expression == preset_expression:
            return preset, None
    match = SUBJECT_EXPRESSION.match(expression)
    if match:
        return "subject", match.group(1)
    return "custom", None


class ShortcutSetupWizard(models.TransientModel):
    """Set up one favorite as a shortcut button without the technical filter
    form: whether it is a button, its order, where it shows (a preset that
    writes the Show When expression), its icon and its default flag.

    Opened by the gear that appears when a filter is selected: in the banner
    of a multi-record view when exactly one favorite is active, and in the
    row above an in-form list when a button is active (see
    static/src/components/view_shortcuts_banner and
    static/src/views/x2many_field_patch.js). The record rule of ir.filters
    decides what the user may change: their own favorites and the favorites
    shared with all users; a Settings administrator, every filter.
    """

    _name = "shortcut.setup.wizard"
    _description = "Set Up Shortcut"

    filter_id = fields.Many2one(
        "ir.filters",
        string="Favorite",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    res_model = fields.Char(string="Model", compute="_compute_res_model")
    is_shortcut = fields.Boolean(
        string="Show as a button",
        compute="_compute_from_filter",
        readonly=False,
        store=True,
        help="Off: the favorite stays in the Favorites menu only.",
    )
    # Not shown in the wizard: a new button goes last (_next_sequence); an
    # administrator reorders on the filter form.
    shortcut_sequence = fields.Integer(
        string="Position",
        compute="_compute_from_filter",
        readonly=False,
        store=True,
    )
    # Not required at the database level: a stored computed field is written
    # after the insert, so NOT NULL would refuse the row. The form requires it.
    show_preset = fields.Selection(
        selection="_show_preset_selection",
        string="Where",
        compute="_compute_from_filter",
        readonly=False,
        store=True,
        help="Everywhere: on the list of all of them and inside everything "
        "that has them. The next two choices keep one of those places. "
        "Only inside one of them: pick which one below. Custom rule: an "
        "expression of your own, for administrators.",
    )
    # Its own compute method, apart from _compute_from_filter: the gear inside
    # a form passes this field as a default, and a default for one field of a
    # compute method makes Odoo skip that whole method on create.
    subject_model_id = fields.Many2one(
        "ir.model",
        string="Which one",
        compute="_compute_subject_model_id",
        readonly=False,
        store=True,
        ondelete="cascade",
        help="Employee, for the services of an employee.",
    )
    # The models that hold a list of this model inside their form: found
    # through the relation fields that point at it. Cheap and generic; it may
    # offer a model whose form has no such list.
    subject_model_ids = fields.Many2many(
        "ir.model",
        compute="_compute_subject_model_ids",
    )
    shortcut_show_when = fields.Text(
        string="Rule",
        compute="_compute_shortcut_show_when",
        readonly=False,
        store=True,
        help="The expression the choice above stands for. Editable for a custom "
        "rule: see the Show When group on the filter form for the names.",
    )
    shortcut_icon = fields.Char(
        string="Icon",
        compute="_compute_from_filter",
        readonly=False,
        store=True,
        help="The icon shown on the button, chosen from the list.",
    )
    is_default = fields.Boolean(
        string="Default filter",
        compute="_compute_from_filter",
        readonly=False,
        store=True,
        help="Switched on when the screen or the tab opens, where the button shows.",
    )

    @api.model
    def _filter_from_context(self):
        """The favorite the wizard is opened for, from the action context."""
        filter_id = self.env.context.get("default_filter_id")
        return self.env["ir.filters"].browse(filter_id) if filter_id else self.env["ir.filters"]

    @api.model
    def _subject_models(self, res_model):
        """The models whose form shows a list of ``res_model``: the relation
        fields that point at it, kept when a form view of their model places
        that field. Without the form check the list names every model that
        merely relates to these records (for services: plan items, plan
        slots, a wizard base), which is noise to a user. Among those, the
        models a user opens from a menu are preferred (for services:
        Employee, Logbook Entry, Service, Ship, not the plan item that is
        only reached from the planning); the others are kept only when no
        model has a menu.
        """
        View = self.env["ir.ui.view"]
        relation_fields = self.env["ir.model.fields"].search(
            [("relation", "=", res_model), ("ttype", "in", ("one2many", "many2many"))]
        )
        models_with_list = self.env["ir.model"]
        for field in relation_fields:
            model = field.model_id
            if model.transient or model in models_with_list:
                continue
            in_a_form = View.search_count(
                [
                    ("model", "=", model.model),
                    ("type", "=", "form"),
                    ("arch_db", "ilike", f'name="{field.name}"'),
                ]
            )
            if in_a_form:
                models_with_list |= model
        return self._prefer_models_with_a_menu(models_with_list).sorted("name")

    @api.model
    def _prefer_models_with_a_menu(self, models):
        """The models among ``models`` that a menu item opens, or all of them
        when none has a menu."""
        if not models:
            return models
        actions = self.env["ir.actions.act_window"].search(
            [("res_model", "in", models.mapped("model"))]
        )
        menus = self.env["ir.ui.menu"].search(
            [("action", "in", [f"ir.actions.act_window,{action.id}" for action in actions])]
        )
        models_with_menu = {
            action.res_model for action in actions if any(m.action == action for m in menus)
        }
        preferred = models.filtered(lambda m: m.model in models_with_menu)
        return preferred or models

    @api.model
    def _show_preset_selection(self):
        """The five choices, worded with the names of the things themselves
        when the wizard is opened for a favorite: "Only on the Services list",
        "Only inside an Employee, Ship, Log Entry or Service".
        """
        filter_record = self._filter_from_context()
        if not filter_record.exists():
            return SHOW_PRESETS
        model = self.env["ir.model"]._get(filter_record.model_id)
        names = self._subject_models(filter_record.model_id).mapped("name")
        if len(names) > SUBJECT_NAMES_IN_LABEL:
            inside = ", ".join(names[: SUBJECT_NAMES_IN_LABEL - 1]) + ", ..."
        elif len(names) > 1:
            inside = ", ".join(names[:-1]) + " or " + names[-1]
        else:
            inside = names[0] if names else ""
        if inside:
            inside = with_article(inside)
        return [
            ("everywhere", _("Everywhere")),
            ("views", _("Only on the %s list", plural(model.name))),
            ("forms", _("Only inside %s", inside) if inside else SHOW_PRESETS[2][1]),
            ("subject", _("Only inside one of them")),
            ("custom", _("Custom rule (administrators)")),
        ]

    @api.model
    def default_get(self, fields_list):
        """The gear inside a form passes the form's model, so "Only in the
        form of ..." is one click away with that form already chosen.
        """
        values = super().default_get(fields_list)
        subject_model = self.env.context.get("shortcut_subject_model")
        if subject_model and "subject_model_id" in fields_list:
            model = self.env["ir.model"].search([("model", "=", subject_model)], limit=1)
            if model:
                values["subject_model_id"] = model.id
        return values

    @api.depends("filter_id")
    def _compute_res_model(self):
        for wizard in self:
            wizard.res_model = wizard.filter_id.model_id

    @api.depends("filter_id")
    def _compute_from_filter(self):
        """Open on what the favorite holds today."""
        for wizard in self:
            filter_record = wizard.filter_id
            preset, subject_model = preset_for_expression(filter_record.shortcut_show_when)
            wizard.is_shortcut = filter_record.shortcut_sequence > 0
            wizard.shortcut_sequence = filter_record.shortcut_sequence
            wizard.show_preset = preset
            wizard.shortcut_icon = filter_record.shortcut_icon
            wizard.is_default = filter_record.is_default

    @api.depends("filter_id")
    def _compute_subject_model_id(self):
        """The form named by a "subject == '...'" expression; otherwise the
        value stays as it is (a default from the gear inside a form, or empty).
        """
        for wizard in self:
            _preset, subject_model = preset_for_expression(wizard.filter_id.shortcut_show_when)
            if subject_model:
                wizard.subject_model_id = self.env["ir.model"].search(
                    [("model", "=", subject_model)], limit=1
                )
            else:
                wizard.subject_model_id = wizard.subject_model_id

    @api.depends("res_model")
    def _compute_subject_model_ids(self):
        for wizard in self:
            wizard.subject_model_ids = self._subject_models(wizard.res_model)

    @api.depends("filter_id", "show_preset", "subject_model_id")
    def _compute_shortcut_show_when(self):
        """A preset writes its expression; "custom" starts from the filter's
        own expression and is then the user's to edit.
        """
        for wizard in self:
            if wizard.show_preset == "custom":
                wizard.shortcut_show_when = wizard.filter_id.shortcut_show_when
            else:
                wizard.shortcut_show_when = expression_for_preset(
                    wizard.show_preset, wizard.subject_model_id.model
                )

    def _next_sequence(self):
        """A new button goes last: after the highest position among the
        model's buttons. The number is not shown in the wizard (Thijs,
        2026-09-15: it means nothing to users); an administrator reorders on
        the filter form.
        """
        last = self.env["ir.filters"].search(
            [("model_id", "=", self.res_model), ("shortcut_sequence", ">", 0)],
            order="shortcut_sequence desc",
            limit=1,
        )
        return (last.shortcut_sequence or 0) + 10

    def action_confirm(self):
        """Write the choices to the favorite. The page reloads so the banner
        and the Favorites menu read the change; the gear inside a form asks
        for a plain close instead and refreshes its row itself.
        """
        self.ensure_one()
        sequence = 0
        if self.is_shortcut:
            sequence = self.shortcut_sequence if self.shortcut_sequence > 0 else self._next_sequence()
        self.filter_id.write(
            {
                "shortcut_sequence": sequence,
                "shortcut_show_when": (self.shortcut_show_when or "").strip(),
                "shortcut_icon": self.shortcut_icon,
                "is_default": self.is_default,
            }
        )
        if self.env.context.get("shortcut_wizard_no_reload"):
            return {"type": "ir.actions.act_window_close"}
        return {"type": "ir.actions.client", "tag": "reload"}
