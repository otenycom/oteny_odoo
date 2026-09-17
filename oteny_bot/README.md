# oteny_bot — the bridge between an Oteny bot and this Odoo

`oteny_bot` is the generic Odoo side of an Oteny business bot. It hosts the
bot record, its Discuss rooms, its activity log (`oteny.bot.session`) and the
form session a bot works a list or form through. It depends on no workflow
engine and knows no domain.

## The work contract

The Oteny platform speaks to this Odoo only through this module. When an
engine hands a record to a bot, the bridge posts one isolated-turn message
into the bot's Discuss room and opens a `dispatched` session that carries the
work token and the origin record (`origin_model`, `origin_res_id`). The box
then calls three `@api.model` methods on `oteny.bot`, each keyed by that token:

| Verb | When the box calls it | Answer |
| --- | --- | --- |
| `work_consume(work_token)` | Once, at the start of the isolated turn, before any model call | `{ok, reason, state}`; a not-ok answer drops the turn |
| `work_probe(work_token)` | About once a minute while the turn runs | `{ok, mine, released, reason, state, next_token}` |
| `work_release(work_token, reason, run)` | On a model-stream timeout, with the run's values | `{ok, released, reason, state}` |

## What an engine implements

An engine module inherits `oteny.bot` and implements three hooks:

- `_work_consume(origin_model, res_id, work_token)`
- `_work_probe(origin_model, res_id, work_token)`
- `_work_release(origin_model, res_id, work_token, reason, run)`

Each hook returns the answer dict above, or `None` when the origin model is
not its own. The bridge finds the session by token, calls the hooks in turn,
and answers `ok: False` with a reason when no engine claims the record. That
fail-closed answer is what keeps a box from running work no engine owns.
riverflow's implementation is `riverflow/models/riverflow_oteny_bot.py`.

## Talents

The bot reads `talents/oteny-odoo-access-talent/` in this repository to work
a list or form. An engine ships its own Talent beside it
(`talents/riverflow-execute-talent/` for riverflow).
