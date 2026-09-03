"""List and form adapter a bot uses on a standard Odoo app.

The session row holds the tab: ``view_state`` and ``fields_spec`` stay
on this transient record. The photo a bot sees lists only visible
amendable fields. ``set`` refuses a field that photo does not offer.

This module does not import ``odoo.tests.form.Form``. It calls the live
``onchange`` / ``web_read`` / ``web_save`` on ``web``. It does not call
``env.clear()``.
"""

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval


_MODIFIER_ALIASES = {"1": "True", "0": "False"}
_LIST_SKIP_TYPES = frozenset({
    "binary", "image", "json", "html", "properties", "monetary",
})
_X2MANY_TYPES = frozenset({"one2many", "many2many"})


class OtenyFormSession(models.TransientModel):
    _name = "oteny.form.session"
    _description = "Oteny form session"

    model_name = fields.Char(required=True)
    res_id = fields.Integer()
    view_id = fields.Many2one("ir.ui.view")
    action_id = fields.Many2one("ir.actions.act_window")
    view_type = fields.Char()
    description = fields.Text()
    view_state = fields.Json()
    fields_spec = fields.Json()

    @api.model
    def views(self, model):
        """Return act_windows and list/form xmlids the user may open."""
        Model = self._model(model)
        Model.check_access("read")
        actions = []
        for action in self.env["ir.actions.act_window"].search([
            ("res_model", "=", model),
        ]):
            if action.group_ids and not (action.group_ids & self.env.user.all_group_ids):
                continue
            xmlid = action.xml_id or action.get_external_id().get(action.id) or ""
            actions.append({
                "xmlid": xmlid,
                "name": action.name,
                "view_mode": action.view_mode,
            })
        views = []
        for view in self.env["ir.ui.view"].search([
            ("model", "=", model),
            ("type", "in", ("list", "form", "tree")),
        ]):
            xmlid = view.xml_id or view.get_external_id().get(view.id) or ""
            views.append({
                "xmlid": xmlid,
                "name": view.name,
                "view_mode": view.type,
            })
        return {"actions": actions, "views": views}

    @api.model
    def list(self, action=None, model=None, view=None, domain=None, limit=80):
        """Open a list view. Visible scalar columns only."""
        resolved = self._resolve(
            action=action, model=model, view=view, view_type="list",
        )
        Model = self.env[resolved["model"]].with_context(resolved["context"])
        Model.check_access("read")
        spec = self._list_fields_spec(Model, resolved["view_id"])
        search_domain = list(resolved["domain"])
        if domain:
            search_domain = search_domain + list(domain)
        result = Model.web_search_read(
            search_domain, spec, limit=limit or 80,
        )
        columns = set(spec)
        records = []
        for row in result.get("records") or []:
            records.append({
                key: row[key] for key in row if key == "id" or key in columns
            })
        return {
            "model": resolved["model"],
            "length": result.get("length") or 0,
            "records": records,
        }

    @api.model
    def open(self, action=None, model=None, view=None, res_id=None):
        """Open a form. No ``res_id`` runs the first ``onchange``."""
        resolved = self._resolve(
            action=action, model=model, view=view, view_type="form",
        )
        Model = self.env[resolved["model"]].with_context(resolved["context"])
        processed = self._process_form_view(Model, resolved["view_id"])
        record = Model.browse(res_id) if res_id else Model.browse()
        if res_id:
            record.check_access("read")
            [values] = record.web_read(processed["fields_spec"])
            values = self._storeable_values(values, processed["fields"])
            changed = []
        else:
            Model.check_access("create")
            values = {"id": False}
            result = record.onchange(values, [], processed["fields_spec"])
            values.update(self._storeable_values(
                result.get("value") or {}, processed["fields"],
            ))
            changed = []
            warning = result.get("warning")
        if res_id:
            warning = None
        session = self.create({
            "model_name": resolved["model"],
            "res_id": res_id or 0,
            "view_id": resolved["view_id"],
            "action_id": resolved["action_id"],
            "view_type": "form",
            "description": resolved["description"],
            "fields_spec": processed["fields_spec"],
            "view_state": {
                "values": values,
                "changed": changed,
                "modifiers": processed["modifiers"],
                "fields": processed["fields"],
                "contexts": processed["contexts"],
                "buttons": processed["buttons"],
                "context": resolved["context"],
            },
        })
        return session._photo(warning=warning)

    @api.model
    def set(self, handle, values):
        """Overlay visible amendable fields and run ``onchange``."""
        session = self._from_handle(handle)
        if not isinstance(values, dict) or not values:
            raise UserError(_("set needs a dict of field values."))
        for fname in values:
            session._assert_amendable(fname)
        state = session._state()
        snapshot = dict(state["values"])
        changed = list(state["changed"])
        warning = None
        Model = session._target()
        for fname, raw in values.items():
            snapshot[fname] = session._coerce(fname, raw)
            if fname not in changed:
                changed.append(fname)
            onchange_vals = session._onchange_values(snapshot)
            record = Model.browse(session.res_id) if session.res_id else Model
            context = session._field_context(fname, snapshot)
            if context:
                record = record.with_context(**context)
            result = record.onchange(
                onchange_vals, [fname], session.fields_spec,
            )
            applied = session._storeable_values(
                result.get("value") or {}, state["fields"],
            )
            snapshot.update(applied)
            for key in applied:
                if key not in changed:
                    changed.append(key)
            if result.get("warning"):
                warning = result["warning"]
        state["values"] = snapshot
        state["changed"] = changed
        session.view_state = state
        return session._photo(warning=warning)

    @api.model
    def save(self, handle):
        """``web_save`` the business row. Create or write."""
        session = self._from_handle(handle)
        state = session._state()
        vals = session._save_values()
        Model = session._target()
        record = Model.browse(session.res_id) if session.res_id else Model.browse()
        [row] = record.web_save(vals, session.fields_spec)
        res_id = row.get("id")
        session.res_id = res_id
        [fresh] = Model.browse(res_id).web_read(session.fields_spec)
        state["values"] = session._storeable_values(fresh, state["fields"])
        state["changed"] = []
        session.view_state = state
        return session._photo()

    @api.model
    def discard(self, handle):
        """Drop the handle. No write on the business row."""
        session = self._from_handle(handle)
        session.unlink()
        return {"ok": True}

    @api.model
    def unlink_record(self, handle):
        """Delete the business row when the person could delete it.

        Named ``unlink_record`` so ORM vacuum of this transient row still
        calls the normal ``unlink``. The wire job is the plan's ``unlink``.
        """
        session = self._from_handle(handle)
        if not session.res_id:
            raise UserError(_("This form has no saved row to delete."))
        if session._view_forbids_delete():
            raise UserError(_(
                "This view does not allow delete."
            ))
        record = session._target().browse(session.res_id)
        record.check_access("unlink")
        record.unlink()
        session.unlink()
        return {"ok": True}

    # --- handle / photo -------------------------------------------------

    @api.model
    def _from_handle(self, handle):
        try:
            session_id = int(handle)
        except (TypeError, ValueError):
            raise UserError(_(
                "handle-expired: this form session is gone. Open the form again."
            ))
        session = self.browse(session_id)
        if not session.exists():
            raise UserError(_(
                "handle-expired: this form session is gone. Open the form again."
            ))
        return session

    def _state(self):
        self.ensure_one()
        return dict(self.view_state or {})

    def _target(self):
        self.ensure_one()
        context = (self.view_state or {}).get("context") or {}
        return self.env[self.model_name].with_context(context)

    def _photo(self, warning=None):
        self.ensure_one()
        state = self._state()
        values = state.get("values") or {}
        fields_info = state.get("fields") or {}
        modifiers = state.get("modifiers") or {}
        photo_fields = []
        for fname, info in fields_info.items():
            if fname == "id":
                continue
            if info.get("type") in _X2MANY_TYPES:
                continue
            if self._eval_modifier(modifiers.get(fname, {}).get("invisible"), values):
                continue
            if self._eval_modifier(modifiers.get(fname, {}).get("readonly"), values):
                continue
            row = {
                "name": fname,
                "type": info.get("type"),
                "required": bool(self._eval_modifier(
                    modifiers.get(fname, {}).get("required"), values,
                )),
                "readonly": False,
                "value": values.get(fname, False),
                "help": info.get("help") or "",
            }
            if info.get("selection"):
                row["selection"] = info["selection"]
            photo_fields.append(row)
        actions = ["save", "discard"]
        for button in state.get("buttons") or []:
            if button not in actions:
                actions.append(button)
        photo = {
            "handle": self.id,
            "model": self.model_name,
            "res_id": self.res_id or False,
            "description": self.description or "",
            "fields": photo_fields,
            "actions": actions,
        }
        if warning:
            photo["warning"] = warning
        return photo

    def _assert_amendable(self, fname):
        names = {field["name"] for field in self._photo()["fields"]}
        if fname not in names:
            raise UserError(_(
                "Field %s is not amendable on this form."
            ) % fname)

    def _coerce(self, fname, raw):
        info = (self._state().get("fields") or {}).get(fname) or {}
        ftype = info.get("type")
        if ftype == "many2one":
            if isinstance(raw, dict):
                return raw.get("id") or False
            return raw or False
        if ftype == "boolean":
            return bool(raw)
        return raw

    def _onchange_values(self, snapshot):
        fields_info = self._state().get("fields") or {}
        values = {}
        for fname, value in snapshot.items():
            if fname == "id":
                continue
            if (fields_info.get(fname) or {}).get("type") in _X2MANY_TYPES:
                continue
            values[fname] = value
        return values

    def _save_values(self):
        state = self._state()
        values = state.get("values") or {}
        fields_info = state.get("fields") or {}
        modifiers = state.get("modifiers") or {}
        changed = set(state.get("changed") or [])
        vals = {}
        for fname in changed:
            info = fields_info.get(fname) or {}
            if fname == "id":
                continue
            if info.get("type") in _X2MANY_TYPES:
                continue
            if self._eval_modifier(modifiers.get(fname, {}).get("readonly"), values):
                continue
            vals[fname] = values.get(fname)
        return vals

    def _field_context(self, fname, snapshot):
        raw = (self._state().get("contexts") or {}).get(fname)
        if not raw:
            return {}
        try:
            ctx = safe_eval(raw, self._eval_context(snapshot))
        except Exception:
            return {}
        return ctx if isinstance(ctx, dict) else {}

    def _view_forbids_delete(self):
        if not self.view_id:
            return False
        Model = self._target()
        views = Model.get_views([(self.view_id.id, "form")])
        arch = views["views"]["form"]["arch"]
        tree = etree.fromstring(arch)
        return tree.get("delete") in ("false", "0", "False")

    def _eval_modifier(self, expr, values):
        if expr in (True, False, None):
            return bool(expr)
        expr = _MODIFIER_ALIASES.get(str(expr), expr)
        if expr in ("True", "False"):
            return expr == "True"
        try:
            return bool(safe_eval(expr, self._eval_context(values)))
        except Exception:
            return True

    def _eval_context(self, values):
        context = dict(self.env.context)
        context.update({
            "id": self.res_id or False,
            "active_id": self.res_id or False,
            "active_ids": [self.res_id] if self.res_id else [],
            "active_model": self.model_name,
        })
        return {
            **context,
            "context": context,
            **(values or {}),
        }

    @api.model
    def _storeable_values(self, values, fields_info):
        stored = {}
        for fname, value in values.items():
            info = {"type": "id"} if fname == "id" else (fields_info.get(fname) or {})
            ftype = info.get("type")
            if ftype in _X2MANY_TYPES:
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    stored[fname] = [item.get("id") for item in value]
                elif isinstance(value, list):
                    stored[fname] = value
                else:
                    stored[fname] = []
                continue
            if ftype == "many2one" and isinstance(value, dict):
                stored[fname] = value.get("id") or False
                continue
            if ftype in ("date", "datetime") and hasattr(value, "isoformat"):
                stored[fname] = fields.Date.to_string(value) if ftype == "date" else fields.Datetime.to_string(value)
                continue
            stored[fname] = value
        return stored

    # --- view resolution ------------------------------------------------

    @api.model
    def _model(self, model):
        if not model or model not in self.env:
            raise UserError(_("Unknown model %s.") % model)
        return self.env[model]

    @api.model
    def _resolve(self, action=None, model=None, view=None, view_type="form"):
        action_rec = False
        context = {}
        domain = []
        description = ""
        view_id = False
        if action:
            action_rec = self._browse_xmlid(action, "ir.actions.act_window")
            model = action_rec.res_model
            context = self._eval_action_context(action_rec.context)
            domain = self._eval_action_domain(action_rec.domain, context)
            description = html2plaintext(action_rec.help or "") or (action_rec.name or "")
            view_id = self._action_view_id(action_rec, view_type)
        if view:
            view_rec = self._browse_xmlid(view, "ir.ui.view")
            model = model or view_rec.model
            view_id = view_rec.id
        if not model:
            raise UserError(_("Open needs a model, a view, or an action."))
        Model = self._model(model)
        if not view_id:
            got = Model.get_views([(False, view_type)])
            view_id = got["views"][view_type].get("id") or False
        return {
            "model": model,
            "view_id": view_id,
            "action_id": action_rec.id if action_rec else False,
            "context": context,
            "domain": domain,
            "description": description,
        }

    @api.model
    def _browse_xmlid(self, ref, expected_model):
        if isinstance(ref, str):
            record = self.env.ref(ref)
        else:
            record = self.env[expected_model].browse(int(ref))
        if not record.exists() or record._name != expected_model:
            raise UserError(_("Unknown %s %s.") % (expected_model, ref))
        return record

    @api.model
    def _action_view_id(self, action, view_type):
        for line in action.view_ids:
            if line.view_mode == view_type and line.view_id:
                return line.view_id.id
        if action.view_id and action.view_id.type == view_type:
            return action.view_id.id
        return False

    @api.model
    def _eval_action_context(self, raw):
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        try:
            value = safe_eval(raw, {"uid": self.env.uid, "context": dict(self.env.context)})
        except Exception:
            return {}
        return dict(value) if isinstance(value, dict) else {}

    @api.model
    def _eval_action_domain(self, raw, context):
        if not raw:
            return []
        if isinstance(raw, list):
            return list(raw)
        try:
            value = safe_eval(raw, {
                "uid": self.env.uid,
                "context": context,
                "allowed_company_ids": self.env.companies.ids,
            })
        except Exception:
            return []
        return list(value) if isinstance(value, list) else []

    @api.model
    def _list_fields_spec(self, Model, view_id):
        views = Model.get_views([(view_id, "list")])
        arch = views["views"]["list"]["arch"]
        field_infos = views["models"].get(Model._name, {}).get("fields") or {}
        tree = etree.fromstring(arch)
        spec = {}
        for node in tree.xpath(".//field"):
            fname = node.get("name")
            if not fname or fname not in Model._fields:
                continue
            if node.get("column_invisible") in ("1", "True", "true"):
                continue
            if node.get("invisible") in ("1", "True", "true"):
                continue
            field = Model._fields[fname]
            if field.type in _LIST_SKIP_TYPES:
                continue
            widget = node.get("widget") or ""
            if widget in ("image", "contact_statistics"):
                continue
            info = field_infos.get(fname) or {}
            if info.get("type") in _LIST_SKIP_TYPES:
                continue
            spec[fname] = {}
        if "display_name" in Model._fields and "display_name" not in spec:
            spec["display_name"] = {}
        return spec

    @api.model
    def _process_form_view(self, Model, view_id):
        views = Model.get_views([(view_id or False, "form")])
        arch = views["views"]["form"]["arch"]
        field_infos = views["models"].get(Model._name, {}).get("fields") or {}
        tree = etree.fromstring(arch)
        fields_meta = {}
        fields_spec = {}
        modifiers = {}
        contexts = {}
        flevel = tree.xpath("count(ancestor::field)")
        for node in tree.xpath(f".//field[count(ancestor::field) = {flevel}]"):
            fname = node.get("name")
            if not fname:
                continue
            info = dict(field_infos.get(fname) or {})
            if "type" not in info and fname in Model._fields:
                info["type"] = Model._fields[fname].type
            if "help" not in info and fname in Model._fields:
                info["help"] = Model._fields[fname].help or ""
            fields_meta[fname] = {
                "type": info.get("type"),
                "help": info.get("help") or "",
                "selection": info.get("selection") or False,
            }
            fields_spec[fname] = {}
            field_modifiers = {}
            for attr in ("required", "readonly", "invisible", "column_invisible"):
                default = attr in ("required", "readonly") and info.get(attr, False)
                expr = node.get(attr) or str(default)
                field_modifiers[attr] = _MODIFIER_ALIASES.get(expr, expr)
            for ancestor in node.xpath(
                f"ancestor::*[@invisible][count(ancestor::field) = {flevel}]"
            ):
                expr = ancestor.get("invisible")
                current = field_modifiers["invisible"]
                if expr == "True" or current == "True":
                    field_modifiers["invisible"] = "True"
                elif current == "False":
                    field_modifiers["invisible"] = expr
                elif expr == "False":
                    pass
                else:
                    field_modifiers["invisible"] = f"({expr}) or ({current})"
            if fname in modifiers:
                merged = {}
                for modifier, expr in modifiers[fname].items():
                    other = field_modifiers[modifier]
                    if expr == "False" or other == "False":
                        merged[modifier] = "False"
                    elif expr == "True":
                        merged[modifier] = other
                    elif other == "True":
                        merged[modifier] = expr
                    else:
                        merged[modifier] = f"({expr}) and ({other})"
                field_modifiers = merged
            modifiers[fname] = field_modifiers
            ctx = node.get("context")
            if ctx:
                contexts[fname] = ctx
        buttons = []
        for button in tree.xpath(".//header/button[@type='object'][@name]"):
            if button.get("invisible") in ("1", "True", "true"):
                continue
            name = button.get("name")
            if name and name not in buttons:
                buttons.append(name)
        return {
            "fields": fields_meta,
            "fields_spec": fields_spec,
            "modifiers": modifiers,
            "contexts": contexts,
            "buttons": buttons,
        }
