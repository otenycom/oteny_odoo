# Oteny standard Odoo access for bots

> **Status:** Server Part 1 BUILT, merged to radar `dev` in `affb8b90` (2026-09-03).
> Offline proof: `oteny_bot/tests/test_form_session_partner.py` on `cr-test`.
> Live proof: Betty on `hh00520` and again on the lab — Contacts save/unlink via form session
> (Hermes **2262**) — [betty-live-proof.md](betty-live-proof.md) §4.
> Host Talent bundle:
> `oteny_bot/talents/oteny-odoo-access-talent/`. Manifest **19.0.1.52**
> (catalog ACL sudo + `res_model`/`xmlid` aliases).
> **Part:** 1 of 3. Ground layer.
> **Demo:** Odoo Experience 2026, 24–26 September, Brussels. Parts 1
> and 2 are the demo path.
> **Delivery:** [Host module Talents](host-module-talents.md).
> **Next:** [riverflow bot execute](../../riverflow/plans/riverflow-bot-execute.md).
> **Then:** [MFNL client reminder](../../../../cuneus_barney/plans/mfnl-client-reminder.md)
> — last pass, Barney adopts these host Talents restricted.
> **Owner:** radar `oteny_bot`. No riverflow import. No Cuneus facts.
> **Path:** B. No hermeshost `src/` in this part. The thin
> `hh-odoo-client` helper is Path A and waits.
> **Branch:** radar `dev`. The feature branch is merged and deleted.

**In one sentence:** a bot browses the views a person already has
on a model, then uses list and form the way that person does.

---

## 1. Why

A business bot must work in a middle-of-the-road Odoo app. It
opens Contacts, reads a list, opens a form, fills a field, saves,
edits, and deletes. It does not invent a second write path.

Odoo Experience 2026 (24–26 September, Brussels) is the demo
target. The demo is exactly this layer: an Oteny bot works a
standard Odoo app through the views a person already has.
Contacts is the neutral stage for it. Part 2 then puts riverflow
on the same adapter, so a bot executes workflow transitions in
radar and in every other app that runs riverflow.

Riverflow transitions later reuse this adapter. They are not the
first proof. If we prove only on a workflow wizard, a bot still
cannot fill a normal form.

**Pit of failure.** A client-side Form in `hh-odoo-client` that
calls `onchange` / `web_save` / `get_view` over `/json/2/`. That
clones `odoo.tests.form.Form`. The OWL JS client and the Python
in `web/models/models.py` ship in the same Odoo release. A bump
then breaks the bot while the human dialog still works.

**Pit of success.** `oteny_bot` holds the tab. The bot sees
`views` / `list` / `open` / `set` / `save` / `discard` and
visible fields. An Odoo upgrade changes one host file.

---

## 2. Classification

| Change | Module | Why |
| --- | --- | --- |
| `oteny.form.session` + partner test set | `oteny_bot` | Generic host. Manifest stays free of riverflow. |
| Thin helper that only calls these verbs | `hh-odoo-client` | Path A. Do not ship in this part. |

`oteny_bot` depends on `base` and `mail` today. This part adds
**`web`** to `depends`, because the live `onchange` and
`web_save` live there. `web` already arrives transitively via
`mail`; the explicit depend names the contract. `oteny_bot` does
not depend on `riverflow`.

---

## 3. Locked contract

`BaseModel.onchange` (`odoo/orm/models.py`) raises
`NotImplementedError`. The live method lives in
`web/models/models.py`. `web_save` sits next to it.
`odoo.tests.form.Form` calls itself a “Server-side form view
implementation (partial)” for server-side tests. A 16→17 cut
already replaced the old string `field_onchange` spec with
today’s `fields_spec` dict.

Do not import `Form` in `oteny_bot`. `Form._perform_onchange`
calls `self._env.clear()`. That wipes a live request cache.

The adapter opens an `ir.actions.act_window`, or a model + view
+ optional `res_id`. It holds `view_state` and `fields_spec` on
`oteny.form.session` (a transient row we own). It is not a copy
of the business form. The business row is born on `save`.

The session row is transient, so Odoo’s vacuum can remove an old
handle. A verb on a dead handle returns a clear handle-expired
error, and the bot re-opens. Fail closed on fields: `set`
refuses a field the photo does not list as amendable (invisible,
readonly, or absent). It never writes one silently.

The `/json/2/` wire the bot sees:

| Verb | Job |
| --- | --- |
| `views` | Given a model, return the act_windows and list/form xmlids the bot user may open. Name, `view_mode`, xmlid. No arch. |
| `list` | Open a list view. `web_search_read` with that view’s `fields_spec`. Visible columns only. Domain and limit. |
| `open` | Open a form. No `res_id` = first `onchange` (new). With `res_id` = `web_read` then a handle. |
| `set` | Overlay visible fields. Run `onchange` on the stored snapshot. Return the visible photo. Surface `warning`. |
| `save` | `web_save`. Create or write the business row. |
| `discard` | Drop the handle. No `write`. |
| `unlink` | Delete when the person could delete from that view. |

`open` / `set` return:

- `handle` (opaque)
- `model`
- `description` (plain help text when the action has it)
- `fields`: visible amendable fields after `*_invisible`. Each
  field: `name`, `type`, `required`, `readonly`, `value`,
  `help`, and `selection` when it has one
- `actions`: footer methods (`save`, `discard`, object buttons
  the view already shows)

`actions` is a photo, not a verb. This part ships no
button-invoke call. Part 2’s act runs the wizard footer
(`action_save`) through its own glue, and a generic `click` verb
waits until a demo or a Talent needs one.

Do not return the view arch. Do not return `view_state` or
`fields_spec`. Do not make the agent call `fields_get` or read
`ir.ui.view`.

`odoo_client` stays the raw pipe for a DTO `search_read`. The
later Path A helper only stores the handle id and calls these
verbs.

---

## 4. Proof — Contacts

Tests: `oteny_bot/tests/test_form_session_partner.py`.
Tags: `oteny_bot`, `post_install`, `-at_install`. Call the
adapter. Do not import `Form`. Do not import riverflow.

Odoo’s own twin is `test_form_create.py`
`test_create_res_partner` and `TestPartnerForm` in
`test_res_partner.py` (`base.view_partner_form`,
`company_type` → `is_company`).

- **Views.** `views('res.partner')` names
  `base.action_partner_form`, `base.view_partner_tree`, and
  `base.view_partner_form`.
- **List.** Open that action in list mode. Search by name.
  The photo has `display_name`, `email`, `phone`. It does not
  return `avatar_128` or `application_statistics`.
- **Create.** Open the form with no `res_id`. Set `name`.
  Save. A `res.partner` row exists. Do not touch
  `property_account_payable_id`.
- **Onchange.** Set `company_type` to `company`. Save.
  `is_company` is True on the row. Prove the effect after save.
  `is_company` is not in the source arch — `_add_missing_fields`
  injects it invisible and readonly. So the photo must not offer
  it.
- **Refuse.** `set` of `is_company` (injected, readonly) errors.
  So does `set` of a field the photo does not list. Nothing is
  written.
- **Edit.** Open that id. Change `email`. Save. `read`
  matches.
- **Delete.** `unlink`. A later list search does not return
  the row.

`child_ids` x2many is not in this first set.

---

## 5. Docs when this part lands

The bot-facing recipe lives in the module Talent
[`oteny_bot/talents/oteny-odoo-access-talent/`](../../../../oteny_bot/talents/oteny-odoo-access-talent/SKILL.md).
Delivery is a talent git path. See
[host-module-talents.md](host-module-talents.md). Worked example:
Contacts. No postedworkers names. No
`_prepare_transition_action`.

Operator present tense stays in
[`.claude/skills/oteny-bot/SKILL.md`](../SKILL.md). The old
author page is a pointer:
[`talent-author-host.md`](../references/talent-author-host.md).

A later pointer in the public authoring standard waits until
Ries says go.

---

## 6. Do not

- Do not implement until Ries says build.
- Do not commit on radar `dev` while this is in flight.
- Do not make `oteny_bot` depend on `riverflow`.
- Do not import `odoo.tests.form.Form`.
- Do not clone that Form in `hh-odoo-client` against
  `onchange`.
- Do not prove this adapter only on a riverflow wizard.
- Do not return view arch or `view_state` to the model.
- Do not let `set` write a field the photo does not list as
  amendable.
- Do not write Cuneus / MFNL / Barney facts into this file
  or into the host Talent. Betty is the *pilot bot* for this
  proof (see [host-module-talents.md](host-module-talents.md)
  §7); her name stays off the generic bundle.
- Do not add an Odoo download API for the Talent.
- Do not require `terminal` or `execute_code`.
