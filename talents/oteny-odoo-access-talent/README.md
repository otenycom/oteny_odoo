<!-- Humans and addon authors. The bot loads SKILL.md, not this file. -->

# Odoo list and form — host Talent

This folder is the Talent for `oteny_bot`. A bot reads it so it can
work a standard Odoo list and form.

Delivery is a talent git path at this directory. Oteny pulls the
commit. The bot never clones.

Point an `hh.talent.source` row at:

- repo: the git that contains this `oteny_bot` module
- `repo_subpath`: `talents/oteny-odoo-access-talent`
- ref: the same branch or tag the addon is deployed from

The recipe is `SKILL.md`. Operator pages under `.claude/skills`
point here. They are not the runtime copy.

A riverflow bot also needs
`talents/riverflow-execute-talent/`. A client Talent is a
third path. That client Talent composes these skills. It does not
copy them.

## The bridge's work contract

The Oteny platform never calls a workflow engine. It calls three
`@api.model` methods on `oteny.bot`, each keyed by the work token the
bridge posted with the dispatch:

| Verb | When the box calls it | Answer |
| --- | --- | --- |
| `work_consume(work_token)` | Once, at the start of the isolated turn, before any model call | `{ok, reason, state}`; a not-ok answer drops the turn |
| `work_probe(work_token)` | About once a minute while the turn runs | `{ok, mine, released, reason, state, next_token}` |
| `work_release(work_token, reason, run)` | On a model-stream timeout, with the run's values | `{ok, released, reason, state}` |

An engine module answers by inheriting `oteny.bot` and implementing
`_work_consume`, `_work_probe` and `_work_release`. Each hook receives the
session's origin model, origin record id and the token. A missing engine
answers `ok: False`, so a box never runs work no engine owns. riverflow's
implementation is `riverflow/models/riverflow_oteny_bot.py`.
