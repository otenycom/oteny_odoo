---
name: oteny-odoo-access-talent
description: "Work an Odoo list and form the way a person does."
version: 0.1.0
---

# Odoo list and form

A business bot works a middle-of-the-road Odoo app through the views a
person already has. The host is `oteny.form.session` in `oteny_bot`.
The bot sees `views` / `list` / `open` / `set` / `save` / `discard`
and visible fields. It does not invent a second write path.

Contacts is the worked example. The same verbs work on any model the
bot user may open.

This Talent is the copy the bot reads. A client Talent loads it. It
does not copy this recipe.

## When to use

Load this skill before you browse a list or fill a form. Call
`odoo_client` with the Odoo connection the project already bound.
Pass `connection=<name>` on every call. Do not request `terminal` or
`execute_code`.

## Why the host holds the tab

The OWL JS client and the Python `onchange` / `web_save` in `web`
ship in the same Odoo release. A client-side Form that calls those
methods over `/json/2/` clones `odoo.tests.form.Form`. An upgrade
then breaks the bot while the human dialog still works.

`oteny_bot` holds the tab. An Odoo upgrade changes one host file.

Do not import `odoo.tests.form.Form`. That Form calls `env.clear()`
and wipes a live request cache.

## Master triage

| The job is… | Do |
| --- | --- |
| Find which views a model already has | Call `views`. Use the xmlid. Do not read `ir.ui.view`. |
| Read a list | Call `list` on that action. Search with domain and limit. |
| Open a new or existing form | Call `open`. No `res_id` = new. With `res_id` = that row. |
| Open a wizard someone already prepared | Call `open` with the `ir.actions.act_window` dict. Keep the context. |
| Change a visible field | Call `set` with that field only. Read the photo. |
| Keep the row | Call `save`. |
| Drop the handle | Call `discard`. No `write`. |
| Delete the row the person could delete | Call `unlink_record`. |
| The handle is dead | The verb returned `handle-expired`. Open the form again. |
| A field is not in the photo | Do not `set` it. Ask or stop. |

## Checklist — every form turn

1. Call `views` for the model if you do not already have the xmlid.
2. Call `open` (xmlid or a prepared act_window dict).
3. Read `fields`. Only those names are amendable.
4. For each change, call `set`. Read `warning`.
5. Call `save`. Read `res_id`.
6. If you must stop without a write, call `discard`.

## Verbs

Call these on `oteny.form.session` through `odoo_client`. Pass
`model='oteny.form.session'` on the tool. Put the business model in
`kwargs` as `res_model` or `model` (`kwargs={'res_model':
'res.partner'}`). Do not put `res.partner` in the tool's own
`model` argument. That argument is the host.

The handle is the transient row id. A verb on a dead handle returns
`handle-expired`. Open the form again.

| Verb | Job |
| --- | --- |
| `views` | Given a model, return the act_windows and list/form xmlids the bot user may open. Name, `view_mode`, xmlid. No arch. |
| `list` | Open a list view. Visible scalar columns only. Domain and limit. |
| `open` | Open a form. Pass `action`, `view`, or `xmlid` (the same token), or a prepared `ir.actions.act_window` dict. The dict keeps wizard context. No `res_id` = first `onchange` (new). With `res_id` = `web_read` then a handle. |
| `set` | Overlay visible amendable fields. Run `onchange`. Return the photo. Surface `warning`. |
| `save` | `web_save`. Create or write the business row. |
| `discard` | Drop the handle. No `write`. |
| `unlink_record` | Delete when the person could delete from that view. The wire job is unlink. The method name leaves ORM vacuum of the transient row alone. |

`open` / `set` / `save` return:

- `handle` (opaque)
- `model`
- `res_id`
- `description` (plain help text when the action has it)
- `fields`: visible amendable fields. Each field: `name`, `type`,
  `required`, `readonly`, `value`, `help`, and `selection` when it
  has one
- `actions`: footer methods (`save`, `discard`, object buttons the
  view already shows)

`actions` is a photo, not a verb. This host ships no button-invoke
call.

Do not return the view arch. Do not return `view_state` or
`fields_spec`. Do not call `fields_get` or read `ir.ui.view`.

`odoo_client` also stays the raw pipe for a DTO `search_read` the
project already does.

## Fail-closed `set`

`set` refuses a field the photo does not list as amendable. That
covers invisible, readonly, and absent fields. It never writes one
silently.

## Contacts example

`views('res.partner')` names `base.action_partner_form`,
`base.view_partner_tree`, and `base.view_partner_form`.

List that action. Search by name. The photo has `display_name`,
`email`, and `phone`. It does not return `avatar_128` or
`application_statistics`.

Open the form with no `res_id`. Set `name`. Save. A `res.partner`
row exists.

Set `company_type` to `company`. Save. `is_company` is True on the
row. `is_company` is not in the photo. `_add_missing_fields`
injects it invisible and readonly. `set` of `is_company` errors.
So does `set` of a field the photo does not list.

Open that id. Change `email`. Save. `read` matches. `unlink_record`
removes the row. A later list search does not return it.

`child_ids` x2many is not in this first set.

Create-save sends every non-readonly snapshot field in the view
spec. Invisible defaults such as a wizard id then survive.
Edit-save still sends changed fields only.

## Hard rules

- Use `odoo_client` only. Do not request `terminal` or
  `execute_code`.
- Do not invent a second write path.
- Do not `set` a field the photo does not list as amendable.
- Do not read view arch or `view_state`.
- A client Talent loads this skill. It does not copy this recipe.
