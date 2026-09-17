# Betty live proof — agent playbook (steps 1–5)

> **Status:** DONE — steps 1–5 green 2026-09-03, merged to radar `dev` in
> `affb8b90`. Kept as the worked example. Proven twice: on the prod-pool box
> `hh00520` (Hermes sessions **2259** skills, **2262** Contacts, **2264**
> riverflow) and again on the lab box `lab00006` on `lab-ref1`, through the fixed
> `hh-odoo-client` plugin and the Discuss adapter's own-author filter, with zero
> "Redirected current run" notices. Both boxes are destroyed; the lab stays.
> Login `hr.betty` (33) and channel `5959` remain on `crmain`. Probe workflow
> **43** stays on `crmain` (a prod restore, re-restored at will). Part 3 not
> started.
> Why the lab: a prod-pool dev bot takes its plugins from the prod router's
> commit on every converge, so a fix the router does not run never reaches it.
> The in-lab commission is hermeshost
> [`ephemeral-lab.md`](../../../../../hermeshost/skills/testing-simulator/references/ephemeral-lab.md)
> **Commission a Path B dev bot in the lab**.
> **Owner:** radar `oteny_bot` + Path B author loop.
> **Box:** `hh00520`. Slot: `host-talents-crmain-ries`.
> **Discuss channel:** `5959` (Betty's room, not Barney's).
> **Uplink host:** `barney-dev-ries-host-talents.oteny.bot`
> (named tunnel on `vmac1` to `127.0.0.1:8069`). Database:
> `crmain`.
> **Parent:** [host-module-talents.md](host-module-talents.md).
> **Path:** B. Account key + `oteny` / `dev_bot.ensure`. No
> `python -m hermeshost commission --internal`. No
> `provision_barney.py --tier local`.
> **Fast path for the next pilot bot:**
> [`pilot-bot-commissioning.md`](../references/pilot-bot-commissioning.md)
> strips this file's narrative down to a checklist. This file stays the
> worked example and the exact Betty values.

**In one sentence:** give Betty her own login, name her in
Discuss, then prove she can read the two host skills, save a
Contact, and press one riverflow button.

An AI agent runs this file top to bottom. Do not ask Ries for
commands that are already here. Stop and report if a **Stop**
row fires.

---

## 0. Fixed facts and files

| Token | Value |
| --- | --- |
| Box id | `hh00520` |
| Dev slot | `host-talents-crmain-ries` |
| Betty login | `hr.betty` |
| Betty display name | `Betty` |
| Betty key name | `betty-uplink` |
| Betty key file | `~/oteny/radar/secrets/betty-uplink-key` (0600) |
| State file | `~/oteny/radar/secrets/host-talents-local-bot-state.json` (0600) |
| Account key file | name only: `barney-otenybot-accountkey` under `~/oteny/radar/secrets/` |
| Barney box | `hh00517` |
| Barney login | `hr.otenybot` |
| Barney channel | do not use. Today Barney's crmain channel is `5957` |
| Betty channel | `5959` |
| Talent ref | `dev` (the branch the addon runs; the feature branch is merged and deleted) |
| Host slugs | `oteny-odoo-access-talent`, `riverflow-execute-talent` |

Odoo shell (local `crmain`). Pipe a heredoc. Commit only when
the playbook says `env.cr.commit()`.

```
cd ~/oteny/radar && ../../odoo/venv/bin/python3 \
  ../../odoo/odoo19/odoo-bin shell \
  --addons-path=../../odoo/odoo19/addons,/Users/ries/odoo/enterprise19,/Users/ries/oteny/radar \
  -d crmain --no-http --max-cron-threads 0 --log-level=warn
```

**Secrets.** Never print a key, a token, or a file body. Write
plaintext to a 0600 file. Probe with `$(cat file)` in a header.
Confirm existence with length, not value.

**Stop now if any of these is true.**

- `oteny.bot` with `uplink_ref='hh00517'` is missing or is not
  named Barney.
- You are about to call `ensure_bot` or `bind_discuss_channel`
  while the Odoo session user is `hr.otenybot`.
- You are about to rotate or revoke a key named `barney-uplink`
  on `hr.otenybot`.
- `crmain` is not serving on `127.0.0.1:8069`, or cron is off
  (`--max-cron-threads 0` on the *served* process).
- The named tunnel host does not return HTTP 200 on `/web/login`.
- You are about to run `provision_barney.py` or
  `force_create=True` on slot `host-talents-crmain-ries`.
- You are about to open an MFNL / postedworkers card, or Hand
  to Barney.

---

## 1. Mint Betty's seam login and put the key on the box

**Why.** `ensure_bot` finds the oldest `oteny.bot` whose
`bot_user_id` is the *calling* login. The harness calls
`ensure_bot` on every run. If Betty authenticates as
`hr.otenybot`, that first run rehomes Barney onto `hh00520`.
See [host-module-talents.md](host-module-talents.md) §7.

**Pit of failure.** A second API key on `hr.otenybot` named
`host-talents-uplink`. That is what the first commission used.
The login is still Barney's.

**Pit of success.** A new `res.users` with `login='hr.betty'`.
A global `/json/2/` key owned by that user. That key delivered
to `hh00520` by Path B reuse. Barney's row and Barney's keys
unchanged.

### 1a. Create the user (crmain shell, commit)

Search first. Reuse `hr.betty` if it already exists. Do not
create a second user.

Partner name `Betty`. Login `hr.betty`. Company =
`base.main_company`. Groups, only these:

- `riverflow.group_service_reader`
- `riverflow.group_service_writer`

`group_service_reader` implies `base.group_user`. That is
enough for `oteny.form.session` and Contacts. Service writer
is enough to execute a riverflow footer.

Do **not** add `hr.group_hr_user`. Betty is not an MFNL bot.
Do **not** add `oteny_bot.group_oteny_bot_operator`. A seam
login that is also an operator can create a room and pass
its own admission gate.
Do **not** add `base.group_system`.

`env.cr.commit()`. Print only `user.id` and `login`.

### 1b. Mint the key (crmain shell, commit)

Copy the Odoo-19 mint shape from
`crewradar_cuneus_sign/tools/mint_otenybot_key.py`. Do not
run that file as-is. It targets `user_hr_otenybot` and key
name `barney-uplink`.

Call `res.users.apikeys` as
`Key.with_user(betty).sudo()._generate(None, 'betty-uplink', None)`.
`sudo()` last. Scope `None` (global). No expiry. Revoke only
prior keys on **Betty** with name `betty-uplink`. Never search
`user_id` = Barney.

Redirect the sentinel to the 0600 file. `chmod 0600`. Do not
echo the file. `env.cr.commit()`.

### 1c. Probe the key against crmain

POST `/json/2/res.users/search_read` to
`https://barney-dev-ries-host-talents.oteny.bot` with
`Authorization: Bearer` from the 0600 file, body
`{"domain":[["login","=","hr.betty"]],"fields":["login"],"limit":1}`
and header `X-Odoo-Database: crmain` if the host needs it
(local tunnel usually does not; if 404/db, add it).

Expect HTTP 200 and login `hr.betty`. A 401 means the mint
failed or you hit the wrong database. Fix 1b. Do not continue.

### 1d. Deliver the key to `hh00520` (Path B reuse)

Do not call `hh.tenant.set_uplink_key`. That method is
system-only. The author path is `request_dev_bot` reuse with
the same `dev_slot` and a new `uplink_key`.

Use `talents/skills/_shared/scripts/dev_bot.py` `ensure(...)`
with:

- `dev_slot='host-talents-crmain-ries'`
- `force_create=False`
- `uplink_key` read from the 0600 file (in memory, not argv)
- `uplink_url` = `https://barney-dev-ries-host-talents.oteny.bot`
- `uplink_db` = `crmain`
- `uplink_env` = `dev`
- `discuss_channel` = `'5959'`
- talent repo / subpath / `source_ref='dev'` as already on the
  box (both host slugs). Do not drop the sources.

Wait until the request is `active` and both
`hh.talent.source.last_status` values are `delivered`.
`active` alone is not enough.

`force_create=True` destroys the slot holder. Do not pass it.

If reuse refuses the key, stop. Name the error. Do not fall
back to minting on `hr.otenybot`.

### 1e. Prove the box is Betty, not Barney

From the laptop, probe `/json/2/res.users/search_read` with
Betty's key (already done). Then
`oteny traces --ref hh00520` or `oteny inspect --ref hh00520`.
`uplink_status` must not stay `auth_failed` after the
converge.

On crmain, as a **read-only** shell (no commit):

- `oteny.bot` `hh00517` still `name='Barney'`,
  `bot_user_id.login='hr.otenybot'`.
- No `oteny.bot` row for `hh00520` yet (step 2 creates it).
- `hr.otenybot` still exists. `hr.betty` exists.

---

## 2. Name the Discuss friend Betty

**Why.** People talk to a friend, not to `hh00520`. The row
is also the dispatch target (`discuss_channel_id`).

**Pit of failure.** Calling `oteny.bot.ensure_bot` or
`bind_discuss_channel` while authenticated as `hr.otenybot`.
`_canonical_same_user_bot()` returns Barney. `bind_discuss_channel`
always calls `ensure_bot` first.

**Pit of success.** Admin shell creates the row. Betty's
`bot_user_id` is `hr.betty`. Channel `5959` is hers. Barney's
channel stays `5957`.

### 2a. Create the row (crmain shell, commit)

Search `oteny.bot` for `uplink_ref='hh00520'`. If a row
exists with `bot_user_id` = Barney, **stop**. Do not write it.
Report. That row is a collision, not a rename candidate.

If no row exists, create:

- `name='Betty'`
- `uplink_ref='hh00520'`
- `bot_user_id` = `hr.betty`
- `discuss_channel_id` = channel `5959`

Do not call `ensure_bot`. Do not call `bind_discuss_channel`.

### 2b. Channel membership

Add Betty's partner as a `discuss.channel.member` on `5959`
if she is not already a member. Add Ries's internal user
partner if he is not a member, so a human can talk in the
room. Do not add Betty to channel `5957`. Do not add Barney's
partner to `5959`.

Channel `5959` must keep a human operator as `create_uid`.
Do not recreate the channel as `hr.betty`.

### 2c. Prove the split (read-only)

| Row | `uplink_ref` | `name` | `bot_user_id.login` | channel |
| --- | --- | --- | --- | --- |
| Barney | `hh00517` | `Barney` | `hr.otenybot` | `5957` |
| Betty | `hh00520` | `Betty` | `hr.betty` | `5959` |

If any cell differs, stop. Do not post a turn.

---

## 3. `skill_view` both host skills

**Why.** Inspect already saw the files on the box. This step
proves the **model** can open them.

### 3a. Preconditions

Both sources on the box are `last_status=delivered` at
`dev`. `oteny inspect --ref hh00520` still lists
both names in `talents_tree`. Gateway heartbeat is alive
(see cuneus-barney `dev-loop.md` — `agent.log` mtime).

### 3b. Post one isolated turn

From crmain shell as **admin** (Ries), not as `hr.otenybot`
and not as `hr.betty`:

```
[oteny:isolated] Call skill_view with name='oteny-odoo-access-talent'.
Then call skill_view with name='riverflow-execute-talent'.
Reply with the first heading of each skill.
Do not open Contacts. Do not press a riverflow button.
Do not call odoo_client except skill_view.
```

`message_post` that exact text on channel `5959`.
`message_type='comment'`. Use the same isolated sentinel the
adapter already knows: `[oteny:isolated]`
(`oteny_bot` `ISOLATED_TURN_SENTINEL`). Commit.

### 3c. Grade

Wait up to three minutes. Read the next bot message in
`5959`. Read `oteny.bot.session` for Betty. Run
`oteny traces --ref hh00520`.

Green: both skill names appear, and a heading from each
`SKILL.md` is quoted. Red: “skill not found”, a rehome of
Barney, or `uplink_status: auth_failed`.

If red, stop. Do not start step 4.

---

## 4. One Contacts save

**Why.** Part 1 live proof. Contacts is the neutral stage.
Betty may do this even though it is outside Cuneus.

### 4a. Post one isolated turn

Same room, same sentinel, admin poster. Tell her:

1. Load `oteny-odoo-access-talent`.
2. Call `oteny.form.session` `views` / `open` / `set` /
   `save` on `res.partner`.
3. Use the Odoo connection already bound on this box. Pass
   `connection=<that name>` on every `odoo_client` call.
   Discover the name from `oteny inspect --ref hh00520`
   (connections). If there is exactly one Odoo connection,
   use it. Do not invent `crewradar` unless inspect shows it.
4. Create a partner whose `name` is
   `Betty probe YYYY-MM-DD HH:MM` (use the real clock).
5. Reply with the new `res_id`.
6. Then `open` that id and `unlink_record`, so the probe
   does not stay in Contacts.
7. Do not touch other partners. Do not open riverflow.

### 4b. Grade

Green: traces show `oteny.form.session` `open` / `set` /
`save` / `unlink_record`. A read-only shell finds no leftover
partner with that name after unlink. Red: she wrote
`res.partner` with `write` / `create` instead of the form
session, or she set a field the photo did not list.

Do not import `odoo.tests.form.Form` anywhere.

---

## 5. One riverflow execute

**Why.** Part 2 live proof. A demo card is enough. Barney's
MFNL cards are out of scope.

### 5a. Make a throwaway card (crmain shell, commit)

Do not use any workflow whose xmlid or name contains `mfnl`,
`posted`, or `Barney`.

Search `riverflow.workflow` for an active workflow that has
a start-state transition with a default action and no
`bot_role`. If you find one, create one `riverflow.service`
on it. Name the service `Betty probe YYYY-MM-DD HH:MM`.

If no such workflow exists, create a **minimal** one in the
same shell and commit it:

- workflow name `Betty probe`
- state A (start) and state B (end)
- one transition A→B, default action, no `bot_role`, no
  email sender
- one service on that workflow, same name

Do not add this workflow to a data XML file. It is a probe
row, not a product record.

Read `transition_buttons_json` on the new service as
`hr.betty` (`env` with that user). Confirm at least one
button. Note `index`, `caption`, and
`context.transition_id`.

### 5b. Post one isolated turn

Tell Betty:

1. Load `riverflow-execute-talent` and
   `oteny-odoo-access-talent`.
2. On `riverflow.service` id `<the probe id>`, read
   `transition_buttons_json`.
3. Open the first default-action button through
   `_prepare_transition_action`, then `oteny.form.session`
   `open` on the returned act_window dict.
4. `save`, then wizard `action_save`. No extra `set` unless
   the photo requires a field.
5. Do not `search_read` `riverflow.transition` by name.
6. Do not touch any other service.

### 5c. Grade

Green: the probe service is in state B. Traces show
`_prepare_transition_action` and `oteny.form.session` `open`
/ `save`, then `action_save`. Red: `bot_claim` on an MFNL
card, a `search_read` of `riverflow.transition` by name, or
Barney's `uplink_ref` changed.

After green, archive or cancel the probe service. Leave the
minimal workflow if you created one; say so in the report
so a human can delete it.

---

## 6. Report back

Write four facts, then stop.

1. `hr.betty` id, and that `hr.otenybot` was not touched.
2. `oteny.bot` split table from §2c.
3. Step 3–5 green or red, with the `oteny.bot.session` ids.
4. Whether a probe workflow was created.

Do not merge to `dev`. Do not start part 3. Do not write
Betty's name into the host Talent bundles.

---

## 7. Do not

- Do not run this file until Ries says build.
- Do not use `provision_barney.py`.
- Do not pass `force_create=True` on this slot.
- Do not call `ensure_bot` / `bind_discuss_channel` as
  `hr.otenybot`.
- Do not mint or revoke `barney-uplink`.
- Do not put Betty's key on `hr.otenybot`.
- Do not Hand an MFNL service.
- Do not add scenario YAML in this pass.
- Do not print secrets.
- Do not commit radar `dev`.
