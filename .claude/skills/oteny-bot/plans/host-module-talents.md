# Host module Talents

> **Status:** BUILT, merged to radar `dev` in `affb8b90` (2026-09-03).
> Server Parts 1 and 2 **BUILT**. Betty live proof **green** on the prod pool
> and on the lab — [betty-live-proof.md](betty-live-proof.md); both pilot
> boxes retired, login `hr.betty` and channel `5959` remain on `crmain`. **Next:** part 3 — Barney adopts the same two
> host sources, restricted — [mfnl-client-reminder.md](../../../../cuneus_barney/plans/mfnl-client-reminder.md)
> §10. Do not start part 3 until Ries says go.
> **Needs:** [Oteny Odoo access](oteny-odoo-access.md) (server).
> [Riverflow bot execute](../../riverflow/plans/riverflow-bot-execute.md)
> (server).
> **Owner:** the host modules. `oteny_bot` and `riverflow` each
> carry their own Talent. A client Talent is a third git path.
> **Pilot bot:** Betty. A dedicated test tenant for this proof,
> holding only the two host Talents. Needs her own seam login —
> see §7.
> **Later:** Barney adopts the same two host Talents in
> [MFNL client reminder](../../../../cuneus_barney/plans/mfnl-client-reminder.md)
> (part 3), restricted to his own scope. See §7.
> **Path:** B. No Odoo download controller. No hermeshost `src/`.
> **Branch:** radar `dev`. The feature branch is merged and deleted.

**In one sentence:** the running addon and the Talent the bot
reads are the same git ref.

---

## 1. Why

Treat `oteny_bot` and `riverflow` as standalone modules. Any
Odoo project that installs either module should be usable by a
bot.

The tooling the bot needs is a Talent. That Talent lives
**inside the module**. Delivery is a talent git path. Oteny
pulls the folder onto the box. The bot does not clone. The bot
does not need `terminal` or `execute_code`.

`odoo_client` stays the RPC tool. It does not download the
Talent from an Odoo HTTP API.

**Pit of failure.** The bot-facing recipe sits only in
`.claude/skills`. An operator reads it. The running bot never
sees it. Or a client Talent copies the host recipe, and the
copy drifts from the addon.

**Pit of success.** Configure a talent git path at the module
folder. Oteny pulls that ref. The addon and the skill the bot
reads move together.

---

## 2. Bundle paths

| Module | Bundle | What the bot reads |
| --- | --- | --- |
| `oteny_bot` | `oteny_bot/talents/oteny-odoo-access-talent/` | `views` / `list` / `open` / `set` / `save` / `discard` / `unlink_record` |
| `riverflow` | `riverflow/talents/riverflow-execute-talent/` | Strip JSON, wizard door, `set` / `save` / `bot_claim`, fence |

A bot that must fill a standard form needs the first path. A
bot that must press a riverflow button needs both. A client
app adds its own Talent as a third path. That client Talent
**composes** the host skills. It does not copy the host
recipe.

These folders are git content. They are not Odoo data. Do not
add them to `__manifest__.py`.

---

## 3. How a bot gets the path

Each path is one `hh.talent.source` row. The shape matches the
client Talent already in this repo.

Same git. A subdirectory. The ref is the branch or tag the
addon is deployed from.

Example on this radar repo, follow mode:

```
repo:          git@github.com:otenycom/radar.git
repo_subpath:  oteny_bot/talents/oteny-odoo-access-talent
ref:           <same branch the addon runs>
pin_mode:      follow
slug:          oteny-odoo-access-talent
```

```
repo:          git@github.com:otenycom/radar.git
repo_subpath:  riverflow/talents/riverflow-execute-talent
ref:           <same branch the addon runs>
pin_mode:      follow
slug:          riverflow-execute-talent
```

A second Odoo project that vendors the module uses **that**
project's git URL. The `repo_subpath` stays the path inside
that repo (`oteny_bot/talents/oteny-odoo-access-talent`, or
`riverflow/talents/riverflow-execute-talent`). The ref is the
branch that project's addon is deployed from.

Three rows on one bot is normal. One row per slug. The
platform pulls each folder. The bot never runs `git clone`.

Do not add an Odoo controller that serves the bundle.

---

## 4. What lives where

**The Talent (runtime).** Numbered checklists. Verb tables.
The Contacts worked example. The strip and wizard door. Fail-
closed `set`. `odoo_client` only. No `terminal`. No
`execute_code`. No client-app facts.

**`.claude/skills` (operators).** How to change the addon.
Dance chrome. One live slot. Workflow XML. Tests. Those pages
point at the bundle. They do not teach the bot the verbs as if
the operator skill were the runtime copy.

A later pointer in the public authoring standard waits until
Ries says go.

---

## 5. What this session moved

The session author pages held the bot-facing recipe in the
wrong home. That recipe now lives in the two bundles. The
author pages are short pointers.

- [`talent-author-host.md`](../references/talent-author-host.md)
- [`talent-author-odoo-library.md`](../references/talent-author-odoo-library.md)
- [`talent-author-workflow.md`](../../riverflow/references/talent-author-workflow.md)

Server tests did not move. They stay
`oteny_bot/tests/test_form_session_partner.py` and
`riverflow/tests/test_bot_execute.py`.

---

## 6. Next steps

Steps 1–5 are **green** on Betty, on the prod pool and on the lab; both
boxes are retired. Record: [betty-live-proof.md](betty-live-proof.md).

**Last pass — part 3.** Barney adopts the same two host Talent sources,
restricted to his own MFNL records. See
[mfnl-client-reminder.md](../../../../cuneus_barney/plans/mfnl-client-reminder.md)
§10. Do not start until Ries says go.

---

## 7. Betty and Barney — who holds these talents

**Betty is the pilot bot.** She is a dedicated test tenant that
proves Parts 1 and 2 generically, ahead of any client work. She
holds only the two host Talents — no client Talent, no MFNL
content. Her one job is to prove the recipe works on a live box:
`skill_view`, one Contacts save, one riverflow execute. Testing
Betty may reach outside Radar/Cuneus scope on purpose (a plain
Contacts save, any riverflow demo workflow) — that is fine for a
disposable pilot, and it is exactly why her name does not go
into the host bundles themselves (§4).

**Commissioning the next pilot bot.** Use
[`pilot-bot-commissioning.md`](../references/pilot-bot-commissioning.md) —
the fast checklist, distilled from Betty's live proof. Read on for why the
seam-login rule exists.

**Betty needs her own seam login.** This is a real blocker, found
while wiring her up, not a style choice. `oteny_bot`'s
`ensure_bot` calls `_canonical_same_user_bot()`, which assumes
**one bot per seam user**. It finds the oldest active
`oteny.bot` row whose `bot_user_id` matches the *calling* login.
hermeshost's harness calls `ensure_bot(uplink_ref=ref, name=ref)`
on every run (`src/hermeshost/transition_harness.py`), not just on
first contact.

If Betty's box authenticates on the same login as Barney's
(`hr.otenybot`), her very first live run rehomes **Barney's**
`uplink_ref` onto her box and deactivates hers.
`oteny_bot/tests/test_oteny_bot.py`
`test_ensure_bot_rehomes_stale_same_user_uplink_ref` proves the
exact mechanism. So Betty needs a separate `res.users` seam login
and her own API key before her first live turn, not a second key
on `hr.otenybot`. Minting that login is a small build step. Do
not skip it to save a step.

**Barney adopts the same two host Talents later, restricted.** In
the last pass of this project
([MFNL client reminder](../../../../cuneus_barney/plans/mfnl-client-reminder.md),
part 3), Barney's box also gets the `oteny-odoo-access-talent`
and `riverflow-execute-talent` sources delivered — the same git
paths Betty uses. Barney's own client Talent then composes them,
replacing the search-by-name recipe his `postedworkers-filing`
and `postedworkers-login` pages teach today. Barney's talent set
becomes a **superset** of Betty's: the two host Talents plus his
own `cuneus-hr-talent`. His **use** of the host Talents stays
restricted to his own MFNL service records — his existing
harness and scope-lock gate what he may touch, not the host
Talents. The host Talents change *how* Barney acts on a
transition he was already allowed to open; they do not widen
*what* he is allowed to open.

---

## 8. Do not

- Do not add an Odoo download API for the Talent.
- Do not require `terminal` or `execute_code`.
- Do not put host Talent files in `__manifest__.py`.
- Do not write client-app facts into the host bundles.
- Do not copy the host recipe into a client Talent.
- Do not commit on radar `dev` while this is in flight.
- Do not give Betty the same seam login as Barney, or any other
  live bot. `ensure_bot` rehomes the older row onto the newer
  `uplink_ref` the first time they share one.
- Do not run Betty's first live turn (`skill_view`, Contacts,
  execute) before her own seam login exists.
