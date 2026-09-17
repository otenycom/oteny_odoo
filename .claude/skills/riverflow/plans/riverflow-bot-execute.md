# Riverflow bot execute

> **Status:** Server Part 2 BUILT, merged to radar `dev` in `affb8b90` (2026-09-03).
> Offline proof: `riverflow/tests/test_bot_execute.py` on `cr-test`.
> Live proof: Betty on `hh00520` and again on the lab — throwaway workflow, Advance via
> `prepare_transition_action` + form session (Hermes **2264**) —
> [betty-live-proof.md](../../oteny-bot/plans/betty-live-proof.md) §5.
> Host Talent bundle:
> `riverflow/talents/riverflow-execute-talent/`. Manifest **19.0.1.1238**
> (public `prepare_transition_action`; defaults loop uses `sudo()` for
> `ir.model` reads).
> **Part:** 2 of 3. Sits on part 1.
> **Needs:** [Oteny Odoo access](../../oteny-bot/plans/oteny-odoo-access.md).
> **Delivery:** [Host module Talents](../../oteny-bot/plans/host-module-talents.md).
> **Then:** [MFNL client reminder](../../../../cuneus_barney/plans/mfnl-client-reminder.md)
> — last pass, Barney adopts these host Talents restricted.
> **Owner:** radar `riverflow`. No Cuneus / MFNL xmlids in this file.
> **Path:** B. No hermeshost `src/`.
> **Branch:** radar `dev`. The feature branch is merged and deleted.

**In one sentence:** a bot lists the same transition buttons a
person sees, opens the same wizard through `oteny.form.session`,
and saves with the same footer.

---

## 1. Why

`bot_claim` today writes `state_id` and the team. It never
opens the transition wizard. `action_context` defaults never
run. `set_deadline_to_today` is dead on a bot File path.
Deferred children never fire. Neither do
`create_related_records` (the wizard note), auto-progress, and
the done-cascade — `bot_claim` skips the whole `action_save`
pipeline.

This layer is also the OXP story beside part 1’s Contacts demo.
The strip and the door are generic riverflow surface. So any
app that runs riverflow gets a bot that executes its
transitions, with no per-app code.

A second strip method would drift from the form. The form
would gain a button. The bot list would not.

Part 1 already holds the tab. This part only prepares the
`ir.actions.act_window` and fences the token. It does not
re-implement `onchange`.

**Pit of failure.** Copy deadline keys into `bot_claim`. Or
require `bot_role` before a bot may list a button. Or teach
the Talent to `search_read` `riverflow.transition` by name.

**Pit of success.** One compute paints `transition_buttons_json`.
Open is `_prepare_transition_action` then part 1 `open`. Act
is part 1 `save` plus `action_save`. Dispatch flags stay
optional.

---

## 2. Classification

| Change | Module | Why |
| --- | --- | --- |
| Strip JSON extras, prepare door, `set_deadline_relative`, `bot_claim` runs the wizard | `riverflow` | Every workflow. Bump the manifest — **19.0.1.1236** on 2026-09-03; take the next free number at build time. |
| Form session | `oteny_bot` | Part 1. Do not put CAS or `bot_role` there. |

Do not make `oteny_bot` depend on `riverflow`. The client
helper (or a later glue that already depends on both) does:
prepare the action, then `oteny.form.session` `open`.

---

## 3. Two layers

**Execute (always).** Strip → open wizard → footer. Person,
tester, and bot share this layer. No `bot_role` required.

**Dispatch (optional).** `bot_role`, `is_owned_by_bot`, the
claim token, the isolated turn. A mailbox bot on a plain
service can skip this and still execute.

Do not make execute depend on dispatch. Today’s hide (“HR
never sees `claim` / `work`”) is a filter on the **same**
compute. It fires only when a transition **has** those
roles. Leave `bot_role` empty and nothing is hidden.

---

## 4. What a person already does

**Strip.** `transition_buttons_json` on
`riverflow.state.mixin` (`_compute_transition_buttons_json`,
not stored). Each button is `index`, `caption`, `help`,
`primary`, `action` (`action_button_click`),
`context.transition_id`. A live claim blanks the strip for
non-bot viewers only; the bot user still sees it.

**Open.** `action_button_click` →
`_prepare_transition_action`. From-state check. The human
fence runs here too (see §5). `action_context`. An
`ir.actions.act_window` with `target: new` and **no**
`res_id`. The OWL dialog then uses part 1’s first `onchange`.

Default action: OK / Cancel. Email sender: recipients,
subject, body, then **Send** (`action_save`). Confirm paste
is the same shape with extra visible fields.

**Act.** The strip widget (`transition_buttons.js`
`executeTransition`) saves the card, then fires
`action_button_click`. The dialog footer saves the wizard row,
then runs the footer method. `riverflow.transition.wizard`
`action_save` writes the new state, deadline flags, team,
notes, deferred children.

A tester who skips the look still uses `_fire_transition`
(`default_get`, `create`, `action_save`). That stays. The
bot that must fill uses part 1 `set` before `save`.

---

## 5. Locked contract

**List = `transition_buttons_json`.** Fold it into the DTO
`search_read` the Talent already does. Do not add
`bot_list_transitions`. Do not `search_read`
`riverflow.transition` by name. Extra keys
(`has_visible_fields`, `action_context` key names) go on
**this** JSON. The form widget ignores unknown keys.

**Open.** `_prepare_transition_action`, then part 1 `open`.
Refuse when the from-state does not match. No token consume.
Return the part 1 photo plus `effects` (those key names, so
OK can freeze deadline to today without teaching a date).

**Set.** Part 1 `set` on that handle. The email sender is
the proof: a raw `write` of `mail_template_id` leaves
recipients stale.

**Act.** When a claim token exists: row lock, CAS, token
fence, `_bot_claim_guard`, then part 1 `save` and
`action_save`. When none exists, skip that belt. Cancel is
part 1 `discard`.

**One new deadline key.** Part 3 needs a send that restores a
parent-relative deadline. No existing key can
(`set_deadline_to_today`, `followup_in_days`, and
`snooze_deadline_days` all write absolute dates in `self`
mode). Add one bare key to the base wizard’s deadline `elif`
chain in `action_save`: **`set_deadline_relative`** =
`{'from': <use_project_deadline_from value>, 'days': <int>}`.
It writes those two fields and drops the email sender’s
`project_deadline` write. It touches nothing else — not
`weekend_deadline_rule`. The key is generic; the values stay
client XML.

**`bot_claim` stays.** It is open-and-save with no pause.
The harness and the reaper keep one call. Today’s
search-by-name recipe is retired in author docs after the
strip JSON is on the DTO read (file list: part 3 §8).

**Human fence.** `_bot_assert_human_transition_allowed` runs
at both choke points — `_prepare_transition_action` and
`action_save`. It refuses a person who clicks while a **live
claim** is on the card. Pass a caller flag from act /
`bot_claim`, so the claiming bot’s own open and OK pass both
fences. Update both texts that still say the bot never
reaches them: the `action_save` call-site comment and the
fence docstring.

| Caller | Calls |
| --- | --- |
| Person | 0 extra — the form already has the JSON |
| Harness / reaper | 1 — `bot_claim` |
| Agent, no fields | 1 after the DTO read — open-and-act |
| Agent that must fill | 1 open, N `set`, 1 `save` |
| Forbidden | A second strip method. Talent-built `fields_spec`. |

---

## 6. Proof

Unit tests first, on a neutral test workflow:
`riverflow/tests/test_bot_execute.py`. The
`set_deadline_relative` case sits beside the snooze tests in
`riverflow/tests/test_transition_email_template.py`.

Then on `cr-test`, after part 1 is green:

- A **neutral** card (no `bot_role`) lists the same buttons
  for a person and a bot.
- Open uses `_prepare_transition_action` then
  `oteny.form.session` `open`.
- A default-action transition with `set_deadline_to_today`
  lands today when act or `bot_claim` runs. A second act
  without that flag does not invent a date. A human click
  of the same transition writes the same deadline.
- An email-sender transition with `set_deadline_relative`
  writes the two relative fields. The `today + 1` default
  does not survive.
- The fence refuses a human click while a claim is live. It
  admits the flagged bot caller at open and at OK.

No MFNL display names in those files.

---

## 7. Docs when this part lands

The bot-facing recipe lives in the module Talent
[`riverflow/talents/riverflow-execute-talent/`](../../../../riverflow/talents/riverflow-execute-talent/SKILL.md).
It loads
[`oteny-odoo-access-talent`](../../../../oteny_bot/talents/oteny-odoo-access-talent/SKILL.md)
for form verbs. Delivery is a talent git path. See
[host-module-talents.md](../../oteny-bot/plans/host-module-talents.md).
No postedworkers names.

Operator present tense stays in
[`.claude/skills/riverflow/SKILL.md`](../SKILL.md).
`set_deadline_relative` stays in that SKILL’s Transition Action
Context table. The old author pages are pointers:
[`talent-author-workflow.md`](../references/talent-author-workflow.md)
and
[`talent-author-odoo-library.md`](../../oteny-bot/references/talent-author-odoo-library.md).

A later pointer in the public authoring standard waits until
Ries says go.

Cross-repo doc: hermeshost `skills/transition-harness/SKILL.md`
must name the riverflow module Talent as the recipe the bot
reads (doc only — no hermeshost `src/` change).

---

## 8. Do not

- Do not implement until Ries says build, and not before
  part 1’s partner tests are green.
- Do not commit on radar `dev` while this is in flight.
- Do not add a second strip method.
- Do not copy deadline keys into `bot_claim`.
- Do not leave `bot_claim` as a raw `state_id` write.
- Do not require `bot_role` for execute.
- Do not put `_prepare_transition_action` inside `oteny_bot`.
- Do not write `project_deadline` from `set_deadline_relative`.
  The two relative fields only.
- Do not write Cuneus / MFNL / 9-digit facts here
  or into the host Talent. Betty is the *pilot bot* for this
  proof (see
  [host-module-talents.md](../../oteny-bot/plans/host-module-talents.md)
  §7); her name stays off the generic bundle.
- Do not add an Odoo download API for the Talent.
- Do not require `terminal` or `execute_code`.

## A transition wizard must carry the record's model (19.0.1.1238)

A wizard resolves its records through `_workflow_model`. A service wizard opened
on a `crewradar.log.entry` saw no record, built an empty in-memory service, and
failed with "Another user just updated this record". `_prepare_transition_action`
now refuses that pairing at the button and names both models. Give a second
carrier's transitions an action whose wizard applies to it, such as
`crewradar.log_entry_transition_action`. The generic-carrier test in
`crewradar_cuneus_sign` runs that way, and a second test pins the refusal.
