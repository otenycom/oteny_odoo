---
name: oteny-bot
sync_to_knowledge: false
description: >
  Generic Odoo host for a company's Oteny bot. Covers oteny.bot, Bot Activity
  sessions, the login-dance latch, and the derived one-live-slot operator UI
  on /odoo/oteny-bots. Use when a staff operator debugs a stuck Hand, a stuck
  sign-in dance, or silent Discuss. Agent-only (not published to Knowledge).
---

# Oteny Bot host (`oteny_bot`)

The generic Odoo host for a company's Oteny bot. The bot runs on its own
machine. It talks to this Odoo over a scoped `/json/2/` uplink. Staff review
exchanges on **Oteny Bots** without leaving Odoo.

This skill is the operator surface. The one-live-slot **gate** stays in
[riverflow](../riverflow/SKILL.md). Barney's MFNL workflow stays in
[cuneus-barney](../cuneus-barney/SKILL.md). Do not fork occupancy here.

## When to Use This Skill

- A Hand-to-Barney sticks in *With Barney* and the operator needs the occupant
- A sign-in dance latch looks stuck after a cancelled login
- Discuss is silent and staff must open the bot row, not the website login
- A second bot for a company needs dance chrome without postedworkers names
- A bot must browse a standard Odoo list or form through the views a person already has. The recipe the bot reads is the module Talent [`talents/oteny-odoo-access-talent/`](../../../talents/oteny-odoo-access-talent/SKILL.md)

## Why the operator UI lives here

The MFNL service form already tells HR that Barney is queued (`bot_queue_note`).
The Oteny Bots list is the staff map of the **bot**. A leftover *Register Login*
or a live claim is otherwise invisible until someone hunts MFNL cards.

Dequeue means **the slot is free after a fill ends**. It does not mean a
browser is available. A SLA-less *Needs Login* leftover must not paint as the
occupant. The note may still name leftover parks. The badge must not.

## Operator walk

Audience: `oteny_bot.group_oteny_bot_manager`. Not HR on the MFNL header.

1. Open `/odoo/oteny-bots`. Do not create a New bot.
2. Read the **Slot** badge on Barney.
3. Open the Barney form. The group **One live slot** repeats the badge, the
   note, the occupant service, the occupant state name, since-when, and the
   queued count.
4. **Open holding service** lands on that `riverflow.service` form. Use the
   service header to Hand back or Cancel. This screen does not fire a
   transition.
5. **Open waiting services** lists same-workflow `bot_stage == queue` rows.
   The occupant is excluded. Invisible when the count is 0.
6. **Clear login dance** is visible only while `login_dance_is_active`. It
   empties the latch. It does not call `login_dance_stop` without a token.
7. **Open Discuss** and **Exchanges** stay as they were. Watch live stays on
   the session form. Do not mint a Steel watch from this list.
8. On a Bot Activity form, **Open related record** opens the origin form
   (a `riverflow.service` in the MFNL case). Summary shows the model's
   friendly name and the record's display name. The stored pair stays
   `origin_model` + `origin_res_id`.

Reload the list after a change. There is no ticker. There is no chatter on
`oteny.bot`. `oteny_audit` already logs a force-clear write.

### Slot badge

| Key | Label | Meaning |
|---|---|---|
| `unknown` | Unknown | Compute could not read truth. Danger badge. Never Idle. |
| `idle` | Idle | No dance, no occupying login-hold, no `in_progress` claim. |
| `dance` | Signing in | `login_dance_until` is still in the future. Wins over leftover parks. |
| `live` | Live | Occupant `bot_stage == in_progress`, including *Relogin*. |
| `login_hold` | Login hold | Occupant is *Register Login* (queue + SLA). |

Compute priority: `unknown` → `dance` → live occupant → login-hold occupant →
`idle`. *Relogin* paints `live`. A SLA-less *Needs Login* never wins.

Layer 3 fills these fields only when the row is
`crewradar_cuneus_sign.oteny_bot_barney`. A non-Barney `oteny.bot` leaves
occupant fields empty. That is honest. The code does not guess another
workflow.

### Fail-closed

The list must not say Idle when the compute cannot see the truth.

- Missing workflow or a helper raise → `unknown` and “Slot status could not be read.”
- Broker / Steel must **not** be called from the compute. A 401 must not flip
  the badge to Idle.
- Prefer `login_dance_active()` for the badge. A list read must not wait on
  `login_dance_hold`.
- Session `outcome` is write-back. Paint the **service** occupant.

### What this screen must not do

No Start MFNL. No Refresh login. No Ask Barney Confirm. No `bot_role` claim
token. No Watch live. No Stop-the-run. No Release-slot that writes a fake
free state. The only honest release is the occupant's existing exit.

## Module map

| Piece | Owns |
|---|---|
| `oteny.bot` | Bot row, Discuss home channel, dance latch |
| `oteny.bot.session` | One exchange + outcome. `origin_ref` is the clickable origin. `browser_status` is not the slot. |
| `oteny.bot.turn` | Per-LLM-call detail |
| `login_dance_until` / `login_dance_user_id` / `login_dance_token` | TTL latch. Never show the token. |
| `login_dance_is_active` | Computed from wall clock |
| `login_dance_start` / `login_dance_stop` | Mint / compare-and-clear |
| `login_dance_force_clear` | Manager override. Take `login_dance_hold`, then empty the three fields. |
| `live_slot_*` | Layer 3 compute on the Barney xmlid |
| `oteny.form.session` | Transient list/form adapter. Holds `view_state` and `fields_spec`. The photo lists only visible amendable fields. |

`LOGIN_DANCE_MINUTES` is 15. An abandoned dance unlatches on wall clock.

## Bot Activity rows: one row per claim epoch, signed by OdooBot

An `oteny.bot.session` row with outcome `dispatched` paints the **Working** pill.
The dispatch opens it, and the exit of the bot in-progress state closes it
(`crewradar_cuneus_sign/models/riverflow_service_bot_activity.py`). Two rules
keep that honest.

- **One row per claim epoch.** The work token names the epoch. A re-dispatch of
  the standing token (the 3-min belt re-posting a never-consumed dispatch) reuses
  the open row. The exit closes every open row of the token. Before
  `crewradar_cuneus_sign` 19.0.6.100 the re-post opened a second row, and the
  close hook closed only the newest one. The older row then stayed **Working**
  for ever. `migrations/19.0.6.100` closed those leftovers on every tier.
- **OdooBot signs every dispatch.** `oteny.bot.dispatch_isolated_turn` posts as
  the superuser, whichever user's transaction fires it. A drain fires inside the
  bot's own uplink call (the escalate that freed the slot), and `sudo()` keeps
  that user as the author. The bot's gateway drops a message its own partner
  authored (the echo guard in hh-discuss `select_inbound`), so a dispatch signed
  by the bot is never consumed. Before `oteny_bot` 19.0.1.56 such a dispatch sat
  until the belt re-posted it as OdooBot three minutes later.

**Diagnosis of a stale Working row.** Read the row's `work_token` and search the
sibling rows with the same token. A closed sibling means the duplicate-row
fault above; the migration closes it, or close it by hand with the sibling's
outcome. No sibling and an empty `bot_run_started_at` on the origin record means
the dispatch was never consumed: read `mail.message.author_id` on the flagged
message. It must be OdooBot, never the bot's partner. Then check the bot's
`uplink_ref` and the dispatch cron (a restored database severs both). Live case:
test1 session 51, 2026-09-05. Production had the same shape once, session 11 on
2026-09-04.

Proven live on test1 on 2026-09-06 (Path B, the stub meldloket): Barney handed
33357 back through its own call, the belt dispatched 33007 as OdooBot, Barney
consumed it in the same second, and 33007 closed as one OK row (session 55)
after a 741 s draft. The inline drain itself lost a serialization race to
Barney's narration in that run; the radar ledger holds that finding.

## Layer split

```
oteny_bot                 no riverflow depend. Dance fields, dance chrome, form session. Depends on `web`.
riverflow                 no oteny_bot depend. Gate + occupant helpers.
crewradar_cuneus_sign     depends on both. Fills the Slot on the Barney xmlid.
```

Current manifests: `oteny_bot` **19.0.1.62**, `riverflow` **19.0.1.1242**,
`crewradar_cuneus_sign` **19.0.6.108**.

Riverflow helpers: `_bot_one_live_slot_occupant_of_workflow`,
`_bot_one_live_slot_queued_of_workflow`, `_bot_login_hold_occupies_slot`,
`_bot_drain_peers`, `_bot_resume_login_park`. Occupy and drain rules live
in [riverflow — One live slot](../riverflow/SKILL.md). Do not copy them into
`oteny_bot`. Ask consults `_bot_one_live_slot_defers` before a persist-true
preflight mint. A held slot paints `slot_queued`. Confirm queues. Do not
mint. The MFNL override of `_bot_resume_login_park` skips the login
wizard and skips when a dance is live. Why: the sibling fill already signed
the Steel jar in, and a live Open must not be stolen.

A second bot for a company inherits the gate by flagging its login-park states.
It inherits this UI when a later bridge maps that bot to its workflow.

## Form session

`oteny.form.session` is the list and form adapter. A bot opens the same
act_window a person opens. It reads a list, opens a form, sets visible
fields, and saves. `set` refuses a field the photo does not list as
amendable. The session row holds `view_state` and `fields_spec`. Those
values never go back to the model. The host does not import
`odoo.tests.form.Form`. `open` also accepts a prepared
`ir.actions.act_window` dict, so a wizard door can keep its context.
Create-save keeps invisible defaults and x2many ids.

The recipe the bot reads is the module Talent
[`talents/oteny-odoo-access-talent/`](../../../talents/oteny-odoo-access-talent/SKILL.md).
Delivery is a talent git path. See
[host-module-talents.md](plans/host-module-talents.md).
This skill is the operator surface. It is not the runtime copy.

**Commissioning a pilot bot.** Fast checklist:
[`pilot-bot-commissioning.md`](references/pilot-bot-commissioning.md).
Worked example: [`betty-live-proof.md`](plans/betty-live-proof.md).

**Path B author footguns (Betty live proof, 2026-09-03).**

- A pilot bot needs its **own** seam login before the first live turn.
  `ensure_bot` rehomes the oldest `oteny.bot` for the calling user
  ([host-module-talents.md](plans/host-module-talents.md) §7).
- On a locked database, `group_service_reader` alone may not create or
  unlink `res.partner`. Betty also needs `base.group_partner_manager`
  for the Contacts probe.
- `views()` reads the action/view catalog as **sudo**, then filters to
  what the user may open. Without that, a seam login hits 403 on
  `ir.actions.act_window`.
- Isolated Discuss posts do **not** create `oteny.bot.session` rows.
  Grade with `oteny traces --ref <box>` on channel traffic.
- `odoo_client` passes the host as its first positional arg
  (`oteny.form.session`). Business model names belong in **kwargs** as
  `model` or `res_model`. A name collision raises `TypeError` on the
  box until `hh-odoo-client` renames that arg to `odoo_model`.

Operator pointers:
[talent-author-host.md](references/talent-author-host.md),
[talent-author-odoo-library.md](references/talent-author-odoo-library.md).
The riverflow door is
[`talents/riverflow-execute-talent/`](../../../talents/riverflow-execute-talent/SKILL.md).

## Tests

| Tag | File |
|---|---|
| `oteny_bot` | `oteny_bot/tests/test_oteny_bot.py` — dance active, force-clear, stale `login_dance_stop` no-op, manager-only, `test_oteny_bots_app_uses_brand_icon` |
| `test_form_session` | `oteny_bot/tests/test_form_session_partner.py` — Contacts list/form/set/save/refuse/edit/delete. Does not import `Form`. |
| `test_bot_one_live_slot` | `riverflow/tests/test_bot_one_live_slot.py` — occupant-of-workflow, SLA-less park is not occupant |
| `test_oteny_bot_live_slot_ui` | `crewradar_cuneus_sign/tests/test_oteny_bot_live_slot_ui.py` — idle / live / Relogin / Register Login / leftover park / dance / unknown / non-Barney |

Do not start Happypath. Do not use service `19319`.

## crmain walk (neutralized)

Leave the local Barney provisioner holding. Do not restore. Do not cancel
`24836`. Do not start Happypath.

Current dump (ids and state names only):

| Item | State |
|---|---|
| Barney Slot | `idle`. Note names leftover *Needs Login*. Occupant empty. Queued count 0. Dance latch off. |
| `29664` | *Draft ready for review* (fill ended; no longer occupant) |
| Thinpath `33928` | *Not Started* |
| Thinpeer `33945` | *Draft ready for review* |
| Leftover `24836` | *Needs Login*. Does **not** occupy. |
| `19319` | *Done*. Do not open. |

Open holding service and Open waiting services stay hidden while idle and
while the queued count is 0.

## Key files

- `oteny_bot/models/oteny_form_session.py` — list/form adapter. Verbs `views` / `list` / `open` / `set` / `save` / `discard` / `unlink_record`. `open` accepts an xmlid or a prepared act_window dict. Bot recipe: [`talents/oteny-odoo-access-talent/`](../../../talents/oteny-odoo-access-talent/SKILL.md)
- `talents/oteny-odoo-access-talent/` — host Talent. Git path delivery. Not Odoo data.
- `oteny_bot/models/oteny_bot.py` — dance latch, force-clear, Discuss actions
- `oteny_bot/views/oteny_bot_views.xml` — list, form, manager menu. Root `oteny_bot_menu_root` uses `web_icon="oteny_bot,static/description/icon.png"`
- `oteny_bot/static/description/icon.png` — Oteny Bots home-menu tile. Render from the official flat-top cell (`oteny-cell.svg` in the hermeshost brand mark). Points are left and right. Do not scale a PNG that already clipped those points. Do not add a large PNG margin — the home menu already pads 10 px. `test_oteny_bots_app_uses_brand_icon` checks `web_icon` / `web_icon_data`, that the mark fills most of the canvas, and that the left and right vertices stay sharp
- `crewradar_cuneus_sign/models/oteny_bot.py` — derived `live_slot_*`
- `crewradar_cuneus_sign/views/oteny_bot_live_slot_views.xml` — Slot badge + form group
- `riverflow/models/riverflow_state_bot_mixin.py` — occupy, drain, occupant-of-workflow, wizard `bot_claim`
- Gate SoR: `cuneus_barney/plans/barney-one-live-run-queue.md`
- UI history: `cuneus_barney/plans/barney-one-live-slot-ui.md`
- Part 1 plan (built): [`plans/oteny-odoo-access.md`](plans/oteny-odoo-access.md) — the `oteny.form.session` form/list adapter; parts 2–3 are linked in its header
- Host Talent delivery: [`plans/host-module-talents.md`](plans/host-module-talents.md)
- Part 2 door: [`talents/riverflow-execute-talent/`](../../../talents/riverflow-execute-talent/SKILL.md)
